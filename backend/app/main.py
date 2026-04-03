from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import cast

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response

from .admin_auth import require_admin_bearer
from .db import Database, utc_now_iso
from .entitlements_db import (
    consume_credits,
    ensure_device,
    device_row,
    expires_at_after_days,
    generate_gift_codes_batch,
    gift_code_effective_status,
    grant_oa_follow_bonus,
    list_all_gift_codes,
    redeem_gift_code,
    refund_credits,
    resolve_scene_to_device,
    revoke_gift_codes,
    try_insert_gift_code,
    upsert_scene_token,
)
from .llm_client import create_llm_client, default_reasoner_model
from .models import (
    AdminGiftCodeBatchCreate,
    AdminGiftCodeBatchCreateResult,
    AdminGiftCodeRevokeBody,
    AdminGiftCodeRevokeResult,
    AdminGiftCodeRow,
    AnalyzeFeaturesResponse,
    AnalyzePlanResponse,
    AnalyzeRequest,
    AnalyzeResult,
    CreateArchiveRequest,
    EntitlementsMeResponse,
    PasteImportRequest,
    RedeemRequest,
    TraceStepModel,
    UsageStepModel,
    WechatSceneResponse,
)
from .parser import normalize_wx_txt
from .pdf_export import report_markdown_to_pdf_bytes
from .pipeline import run_report_pipeline
from .pipeline.schemas import SupportsLLMComplete
from .ocr import ocr_image_bytes
from .wechat_mp import parse_subscribe_event, strip_qrscene, verify_signature


def get_data_dir() -> Path:
    # default: does-she-like-me-web/backend/data
    return Path(os.getenv("DATA_DIR") or (Path(__file__).resolve().parents[2] / "data"))


data_dir = get_data_dir()
uploads_dir = data_dir / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)

db = Database(data_dir / "does-she-like-me.sqlite3")
llm_client = create_llm_client()


def _entitlements_enforce() -> bool:
    return os.getenv("ENTITLEMENTS_ENFORCE", "").strip().lower() in ("1", "true", "yes")


def _initial_device_credits() -> int:
    try:
        return max(0, int(os.getenv("INITIAL_DEVICE_CREDITS", "0")))
    except ValueError:
        return 0


def _oa_follow_bonus() -> int:
    try:
        return max(1, int(os.getenv("OA_FOLLOW_BONUS_CREDITS", "1")))
    except ValueError:
        return 1


def _deep_reason_extra_credits() -> int:
    try:
        return max(0, int(os.getenv("DEEP_REASON_EXTRA_CREDITS", "1")))
    except ValueError:
        return 1


def _wechat_token() -> str:
    return os.getenv("WECHAT_MP_TOKEN", "").strip()


def _normalize_temperature(raw: float) -> float:
    v = float(raw)
    if v < 0:
        return 0.0
    if v > 1.5:
        return 1.5
    return v


def _analyze_charge(*, deep_reasoning: bool) -> tuple[int, int]:
    extra_dr = _deep_reason_extra_credits() if deep_reasoning else 0
    return (1 + extra_dr if deep_reasoning else 1), extra_dr


def _refund_credits_if_needed(device_id: str, amount: int) -> None:
    if amount <= 0:
        return
    with db._connect() as conn:
        refund_credits(conn, device_id, amount)
        conn.commit()


def _require_x_device_id(x_device_id: str | None) -> str:
    did = (x_device_id or "").strip()
    if not did:
        raise HTTPException(status_code=400, detail="缺少请求头 X-Device-Id，请刷新页面")
    return did


def _archive_belonging_to_device(db: Database, archive_id: str, device_id: str):
    a = db.get_archive(archive_id)
    if not a:
        raise HTTPException(status_code=404, detail="档案不存在或无权访问")
    if (a.device_id or "") != device_id:
        raise HTTPException(status_code=404, detail="档案不存在或无权访问")
    return a


def _require_credits_for_mutation_sqlite(conn, device_id: str) -> None:
    """开启扣次时：新建档案、导入材料须至少剩余 1 次（与生成报告共用额度）。"""
    if not _entitlements_enforce():
        return
    ensure_device(conn, device_id, initial_credits=_initial_device_credits())
    row = device_row(conn, device_id)
    if not row or int(row["credits"]) < 1:
        raise HTTPException(
            status_code=402,
            detail="分析次数不足，无法新建档案或导入聊天材料；请先兑换卡密或关注公众号领取次数。",
        )


app = FastAPI(title="does-she-like-me-web API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "entitlements_enforce": _entitlements_enforce()}


@app.get("/api/admin/gift-codes", response_model=list[AdminGiftCodeRow])
def admin_list_gift_codes(_: None = Depends(require_admin_bearer)) -> list[AdminGiftCodeRow]:
    now = utc_now_iso()
    with db._connect() as conn:
        rows = list_all_gift_codes(conn)
    return [
        AdminGiftCodeRow(
            code=str(r["code"]),
            credits=int(r["credits"]),
            status=gift_code_effective_status(r, now_iso=now),
            created_at=r["created_at"],
            expires_at=r["expires_at"],
            revoked_at=r["revoked_at"],
            used_by_device=r["used_by_device"],
            used_at=r["used_at"],
        )
        for r in rows
    ]


@app.post("/api/admin/gift-codes", response_model=AdminGiftCodeBatchCreateResult)
def admin_create_gift_codes(
    body: AdminGiftCodeBatchCreate,
    _: None = Depends(require_admin_bearer),
) -> AdminGiftCodeBatchCreateResult:
    if not body.items and not body.generate:
        raise HTTPException(status_code=400, detail="请至少在 items 或 generate 中提供一种创建方式")
    created = 0
    skipped = 0
    generated_plaintext: str | None = None
    with db._connect() as conn:
        if body.generate:
            _, codes = generate_gift_codes_batch(
                conn,
                body.generate.count,
                body.generate.credits,
                body.generate.expires_in_days,
                body.generate.prefix,
            )
            created += len(codes)
            generated_plaintext = "\n".join(codes)
        if body.items:
            exp = expires_at_after_days(body.manual_expires_in_days)
            for it in body.items:
                code = (it.code or "").strip()
                if len(code) < 4 or int(it.credits) < 1:
                    skipped += 1
                    continue
                if try_insert_gift_code(conn, code, int(it.credits), expires_at=exp):
                    created += 1
                else:
                    skipped += 1
        conn.commit()
    return AdminGiftCodeBatchCreateResult(
        created=created,
        skipped_invalid=skipped,
        generated_plaintext=generated_plaintext,
    )


@app.post("/api/admin/gift-codes/revoke", response_model=AdminGiftCodeRevokeResult)
def admin_revoke_gift_codes(
    body: AdminGiftCodeRevokeBody,
    _: None = Depends(require_admin_bearer),
) -> AdminGiftCodeRevokeResult:
    with db._connect() as conn:
        n = revoke_gift_codes(conn, body.codes)
        conn.commit()
    return AdminGiftCodeRevokeResult(revoked=n)


@app.get("/api/config/analyze", response_model=AnalyzeFeaturesResponse)
def analyze_features() -> AnalyzeFeaturesResponse:
    return AnalyzeFeaturesResponse(
        pipeline_version="graph-v1",
        deep_reason_extra_credits=_deep_reason_extra_credits(),
        reasoner_model=default_reasoner_model(),
        entitlements_enforced=_entitlements_enforce(),
    )


@app.get("/api/archives/{archive_id}/analyze/plan", response_model=AnalyzePlanResponse)
def analyze_plan(
    archive_id: str,
    deep_reasoning: bool = False,
    x_device_id: str | None = Header(None, alias="X-Device-Id"),
) -> AnalyzePlanResponse:
    did = _require_x_device_id(x_device_id)
    a = _archive_belonging_to_device(db, archive_id, did)
    upload_path = db.get_upload_path(archive_id)
    required, extra = _analyze_charge(deep_reasoning=bool(deep_reasoning))
    blockers: list[str] = []
    if not upload_path or not upload_path.is_file():
        blockers.append("请先导入聊天材料（txt / 粘贴 / OCR）")
    if _entitlements_enforce():
        with db._connect() as conn:
            row = ensure_device(conn, did, initial_credits=_initial_device_credits())
            conn.commit()
        if int(row["credits"]) < required:
            blockers.append(f"分析次数不足：当前 {int(row['credits'])}，需要 {required}")
    if not (a.stage or "").strip():
        blockers.append("建议补充关系阶段，以提升判断稳定性")
    if not (a.scenario or "").strip():
        blockers.append("建议补充聊天场景，以提升判断稳定性")
    return AnalyzePlanResponse(
        archive_id=archive_id,
        can_analyze=not any(b.startswith("请先导入") or b.startswith("分析次数不足") for b in blockers),
        blockers=blockers,
        required_credits=required,
        deep_reason_extra_credits=extra,
        deep_reasoning_enabled=bool(deep_reasoning),
        has_upload=bool(upload_path and upload_path.is_file()),
        has_report=db.get_report(archive_id) is not None,
        pipeline_steps=["build", "base", "reasoner" if deep_reasoning else "finalize", "persist"],
    )


@app.get("/api/entitlements/me", response_model=EntitlementsMeResponse)
def entitlements_me(x_device_id: str | None = Header(None, alias="X-Device-Id")) -> EntitlementsMeResponse:
    did = (x_device_id or "").strip()
    if not did:
        raise HTTPException(status_code=400, detail="缺少请求头 X-Device-Id（请更新前端）")
    with db._connect() as conn:
        row = ensure_device(conn, did, initial_credits=_initial_device_credits())
        conn.commit()
    return EntitlementsMeResponse(
        device_id=did,
        credits=int(row["credits"]),
        oa_follow_bonus_claimed=bool(row["oa_follow_bonus_claimed"]),
        entitlements_enforced=_entitlements_enforce(),
    )


@app.post("/api/entitlements/redeem")
def entitlements_redeem(
    body: RedeemRequest,
    x_device_id: str | None = Header(None, alias="X-Device-Id"),
) -> dict:
    did = (x_device_id or "").strip()
    if not did:
        raise HTTPException(status_code=400, detail="缺少 X-Device-Id")
    with db._connect() as conn:
        ok, reason, added = redeem_gift_code(
            conn,
            did,
            body.code,
            initial_credits=_initial_device_credits(),
        )
        conn.commit()
    if not ok:
        _gift_reasons = {
            "invalid_code": "卡密格式无效",
            "not_found": "卡密不存在",
            "already_used": "该卡密已兑换过",
            "revoked": "该卡密已作废",
            "expired": "该卡密已超过有效期",
            "race": "系统繁忙，请重试",
        }
        msg = _gift_reasons.get(str(reason), str(reason))
        raise HTTPException(status_code=400, detail=f"兑换失败：{msg}")
    row = None
    with db._connect() as conn:
        row = device_row(conn, did)
    return {"ok": True, "added": added, "credits": int(row["credits"]) if row else 0}


@app.get("/api/entitlements/wechat-scene", response_model=WechatSceneResponse)
def entitlements_wechat_scene(x_device_id: str | None = Header(None, alias="X-Device-Id")) -> WechatSceneResponse:
    did = (x_device_id or "").strip()
    if not did:
        raise HTTPException(status_code=400, detail="缺少 X-Device-Id")
    with db._connect() as conn:
        short = upsert_scene_token(conn, did, initial_credits=_initial_device_credits())
        conn.commit()
    return WechatSceneResponse(
        short_code=short,
        hint="在公众号后台创建「临时/永久带参二维码」，scene 填写此 short_code；用户扫码关注后，系统将为其设备赠送一次分析次数（仅首关有效）。",
    )


@app.api_route(
    "/api/wechat/callback",
    methods=["GET", "POST"],
    response_model=None,
)
async def wechat_callback(request: Request) -> Response | PlainTextResponse:
    token = _wechat_token()
    if not token:
        raise HTTPException(status_code=503, detail="未配置 WECHAT_MP_TOKEN")

    qp = request.query_params
    signature = qp.get("signature", "") or ""
    timestamp = qp.get("timestamp", "") or ""
    nonce = qp.get("nonce", "") or ""
    if not verify_signature(token=token, timestamp=timestamp, nonce=nonce, signature=signature):
        raise HTTPException(status_code=403, detail="signature")

    if request.method == "GET":
        return PlainTextResponse(qp.get("echostr", "") or "")

    body = await request.body()
    msg_type, event, event_key = parse_subscribe_event(body)
    if event in ("subscribe", "SCAN") and event_key:
        short = strip_qrscene(event_key)
        if short:
            with db._connect() as conn:
                device_id = resolve_scene_to_device(conn, short)
                if device_id:
                    grant_oa_follow_bonus(
                        conn,
                        device_id,
                        bonus_credits=_oa_follow_bonus(),
                        initial_credits=_initial_device_credits(),
                    )
                conn.commit()
    return Response(status_code=200)


@app.get("/api/archives/{archive_id}/export/pdf", response_model=None)
def export_report_pdf(
    archive_id: str,
    x_device_id: str | None = Header(None, alias="X-Device-Id"),
) -> Response:
    did = _require_x_device_id(x_device_id)
    a = _archive_belonging_to_device(db, archive_id, did)
    rep = db.get_report(archive_id)
    if not rep:
        raise HTTPException(status_code=400, detail="暂无报告，请先生成")
    title = (a.name or "治愈报告").strip() or "治愈报告"
    try:
        pdf_bytes = report_markdown_to_pdf_bytes(
            report_markdown=rep["report_markdown"],
            title=title,
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"PDF 生成失败（若首次使用请在后端执行 playwright install chromium）：{e}",
        ) from e
    fn = f"report-{archive_id[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@app.get("/api/archives")
def list_archives(x_device_id: str | None = Header(None, alias="X-Device-Id")) -> list[dict]:
    did = _require_x_device_id(x_device_id)
    return db.list_archives(device_id=did)


@app.post("/api/archives")
def create_archive(
    req: CreateArchiveRequest,
    x_device_id: str | None = Header(None, alias="X-Device-Id"),
) -> dict:
    did = _require_x_device_id(x_device_id)
    with db._connect() as conn:
        _require_credits_for_mutation_sqlite(conn, did)
        conn.commit()
    archive_id = str(uuid.uuid4())
    db.create_archive(
        archive_id,
        device_id=did,
        name=req.name or "",
        stage=req.stage or "",
        scenario=req.scenario or "",
        tags=req.tags or {},
    )
    return {"id": archive_id}


@app.get("/api/archives/{archive_id}")
def get_archive(
    archive_id: str,
    x_device_id: str | None = Header(None, alias="X-Device-Id"),
) -> dict:
    did = _require_x_device_id(x_device_id)
    a = _archive_belonging_to_device(db, archive_id, did)
    report = db.get_report(archive_id)
    upload_path = db.get_upload_path(archive_id)
    return {
        "archive": {
            "id": a.id,
            "name": a.name,
            "stage": a.stage,
            "scenario": a.scenario,
            "tags": a.tags,
            "created_at": a.created_at,
            "updated_at": a.updated_at,
            "has_upload": upload_path is not None,
            "has_report": report is not None,
        },
        "report": report,
    }


@app.post("/api/archives/{archive_id}/import/wx-txt")
async def import_wx_txt(
    archive_id: str,
    file: UploadFile = File(...),
    x_device_id: str | None = Header(None, alias="X-Device-Id"),
) -> dict:
    did = _require_x_device_id(x_device_id)
    _archive_belonging_to_device(db, archive_id, did)
    with db._connect() as conn:
        _require_credits_for_mutation_sqlite(conn, did)
        conn.commit()

    if not file.filename.lower().endswith(".txt"):
        # allow even if filename lacks extension, but warn
        pass

    raw = (await file.read()).decode("utf-8", errors="replace")
    normalized = normalize_wx_txt(raw)

    dest = uploads_dir / f"{archive_id}.wx.txt"
    dest.write_text(normalized, encoding="utf-8", newline="\n")
    db.save_upload(archive_id, filename=file.filename, content_path=dest)

    return {
        "archive_id": archive_id,
        "filename": file.filename,
        "normalized_size": len(normalized),
    }


@app.post("/api/archives/{archive_id}/import/paste")
async def import_paste(
    archive_id: str,
    req: PasteImportRequest,
    x_device_id: str | None = Header(None, alias="X-Device-Id"),
) -> dict:
    """
    Tencent 平台若无法导出聊天，用户可把聊天内容直接粘贴到这里。
    后端做归一化（尽量整理为：time | sender | content），再进入同一分析链路。
    """
    did = _require_x_device_id(x_device_id)
    _archive_belonging_to_device(db, archive_id, did)
    with db._connect() as conn:
        _require_credits_for_mutation_sqlite(conn, did)
        conn.commit()

    normalized = normalize_wx_txt(req.text or "")
    dest = uploads_dir / f"{archive_id}.paste.txt"
    dest.write_text(normalized, encoding="utf-8", newline="\n")
    filename = req.filename.strip() if req.filename else "paste.txt"
    db.save_upload(archive_id, filename=filename, content_path=dest)

    return {
        "archive_id": archive_id,
        "filename": filename,
        "normalized_size": len(normalized),
    }


@app.post("/api/archives/{archive_id}/import/ocr")
async def import_ocr(
    archive_id: str,
    files: list[UploadFile] = File(...),
    lang: str = "chi_sim",
    x_device_id: str | None = Header(None, alias="X-Device-Id"),
) -> dict:
    """
    上传你自己本地的聊天截图（合规用途：自用验证/备份），对图片内文字做 OCR 提取，
    再走同一条 normalize_wx_txt -> 分析链路。
    """
    did = _require_x_device_id(x_device_id)
    _archive_belonging_to_device(db, archive_id, did)
    with db._connect() as conn:
        _require_credits_for_mutation_sqlite(conn, did)
        conn.commit()

    if not files:
        raise HTTPException(status_code=400, detail="no files uploaded")

    ocr_texts: list[str] = []
    used_langs: set[str] = set()

    for f in files:
        filename = (f.filename or "").lower()
        if not filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")):
            # allow but warn implicitly by skipping OCR for unknown types
            continue

        image_bytes = await f.read()
        if not image_bytes:
            continue

        try:
            text, used_lang = ocr_image_bytes(image_bytes, lang=lang)
        except RuntimeError as e:
            # OCR 环节常见失败（缺少 pytesseract / 缺少系统 tesseract.exe / lang pack 等）
            # 这里转成 400，让前端拿到可读错误，而不是返回 500。
            raise HTTPException(status_code=400, detail=str(e)) from e
        if text.strip():
            ocr_texts.append(text)
        used_langs.add(used_lang)

    if not ocr_texts:
        raise HTTPException(status_code=400, detail="OCR 结果为空：请确认图片清晰、无倾斜、文字可识别。")

    combined = "\n".join(ocr_texts)
    normalized = normalize_wx_txt(combined)

    dest = uploads_dir / f"{archive_id}.ocr.txt"
    dest.write_text(normalized, encoding="utf-8", newline="\n")

    filename = "ocr.txt"
    db.save_upload(archive_id, filename=filename, content_path=dest)

    preview = normalized[:3000]
    return {
        "archive_id": archive_id,
        "filename": filename,
        "ocr_chars": len(combined),
        "used_langs": sorted(list(used_langs)),
        "normalized_size": len(normalized),
        "ocr_preview": preview,
    }


@app.post("/api/archives/{archive_id}/analyze", response_model=AnalyzeResult)
def analyze_archive(
    archive_id: str,
    req: AnalyzeRequest,
    x_device_id: str | None = Header(None, alias="X-Device-Id"),
) -> AnalyzeResult:
    did = _require_x_device_id(x_device_id)
    a = _archive_belonging_to_device(db, archive_id, did)
    upload_path = db.get_upload_path(archive_id)
    if not upload_path or not upload_path.is_file():
        raise HTTPException(status_code=400, detail="missing imported content (wx-txt / paste / ocr)")
    charge, extra_dr = _analyze_charge(deep_reasoning=bool(req.deep_reasoning))
    charge_applied = 0

    if _entitlements_enforce():
        if not did:
            raise HTTPException(
                status_code=400,
                detail="缺少 X-Device-Id，无法扣次。请刷新页面或更新客户端。",
            )
        with db._connect() as conn:
            ok, reason = consume_credits(
                conn,
                did,
                charge,
                initial_credits=_initial_device_credits(),
            )
            conn.commit()
        if not ok:
            need = charge
            raise HTTPException(
                status_code=402,
                detail=(
                    f"分析次数不足（{reason}），本次需要 {need} 次"
                    + ("（含深度推理附加）。" if req.deep_reasoning else "。")
                    + "请关注公众号领取或兑换卡密。"
                ),
            )
        charge_applied = charge

    normalized_chat_text = upload_path.read_text(encoding="utf-8", errors="replace")
    run_id = uuid.uuid4().hex
    temperature = _normalize_temperature(req.temperature)

    try:
        out = run_report_pipeline(
            llm=cast(SupportsLLMComplete, llm_client),
            db=db,
            archive_id=archive_id,
            run_id=run_id,
            stage=a.stage,
            scenario=a.scenario,
            tags=a.tags,
            normalized_chat_text=normalized_chat_text,
            temperature=temperature,
            deep_reasoning=bool(req.deep_reasoning),
        )
    except RuntimeError as e:
        _refund_credits_if_needed(did, charge_applied)
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        _refund_credits_if_needed(did, charge_applied)
        raise HTTPException(status_code=500, detail=f"pipeline failed: {e}") from e

    if _entitlements_enforce() and req.deep_reasoning and out.reasoner_failed and extra_dr > 0:
        _refund_credits_if_needed(did, extra_dr)

    if not out.final_report.strip():
        _refund_credits_if_needed(did, charge_applied)
        raise HTTPException(status_code=500, detail="empty report from pipeline")

    db.save_report(archive_id, model=out.model_label, report_markdown=out.final_report)
    usage_models = [UsageStepModel(**s) for s in out.usage_steps]
    trace_models = [TraceStepModel(**s) for s in out.execution_trace]
    return AnalyzeResult(
        archive_id=archive_id,
        model=out.model_label,
        report_markdown=out.final_report,
        pipeline_version=out.pipeline_version,
        deep_reasoning_requested=out.deep_reasoning_requested,
        deep_reasoning_used=out.deep_reasoning_used,
        reasoner_failed=out.reasoner_failed,
        reasoner_error=out.reasoner_error,
        usage_steps=usage_models,
        execution_trace=trace_models,
    )
