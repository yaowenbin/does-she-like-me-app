from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response

from .db import Database
from .entitlements_db import (
    consume_credit_for_analyze,
    grant_oa_follow_bonus,
    redeem_gift_code,
    resolve_scene_to_device,
    upsert_scene_token,
    ensure_device,
    device_row,
)
from .llm_client import create_llm_client
from .models import (
    AnalyzeRequest,
    AnalyzeResult,
    CreateArchiveRequest,
    EntitlementsMeResponse,
    PasteImportRequest,
    RedeemRequest,
    WechatSceneResponse,
)
from .parser import normalize_wx_txt
from .pdf_export import report_markdown_to_pdf_bytes
from .prompt_builder import build_system_and_user_prompts
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


def _wechat_token() -> str:
    return os.getenv("WECHAT_MP_TOKEN", "").strip()


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
        raise HTTPException(status_code=400, detail=f"兑换失败：{reason}")
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
    if _entitlements_enforce() and not (x_device_id or "").strip():
        raise HTTPException(status_code=400, detail="缺少 X-Device-Id")
    a = db.get_archive(archive_id)
    if not a:
        raise HTTPException(status_code=404, detail="archive not found")
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
def list_archives() -> list[dict]:
    return db.list_archives()


@app.post("/api/archives")
def create_archive(req: CreateArchiveRequest) -> dict:
    archive_id = str(uuid.uuid4())
    db.create_archive(
        archive_id,
        name=req.name or "",
        stage=req.stage or "",
        scenario=req.scenario or "",
        tags=req.tags or {},
    )
    return {"id": archive_id}


@app.get("/api/archives/{archive_id}")
def get_archive(archive_id: str) -> dict:
    a = db.get_archive(archive_id)
    if not a:
        raise HTTPException(status_code=404, detail="archive not found")
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
) -> dict:
    a = db.get_archive(archive_id)
    if not a:
        raise HTTPException(status_code=404, detail="archive not found")

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
) -> dict:
    """
    Tencent 平台若无法导出聊天，用户可把聊天内容直接粘贴到这里。
    后端做归一化（尽量整理为：time | sender | content），再进入同一分析链路。
    """
    a = db.get_archive(archive_id)
    if not a:
        raise HTTPException(status_code=404, detail="archive not found")

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
) -> dict:
    """
    上传你自己本地的聊天截图（合规用途：自用验证/备份），对图片内文字做 OCR 提取，
    再走同一条 normalize_wx_txt -> 分析链路。
    """
    a = db.get_archive(archive_id)
    if not a:
        raise HTTPException(status_code=404, detail="archive not found")

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
    a = db.get_archive(archive_id)
    if not a:
        raise HTTPException(status_code=404, detail="archive not found")
    upload_path = db.get_upload_path(archive_id)
    if not upload_path or not upload_path.is_file():
        raise HTTPException(status_code=400, detail="missing imported content (wx-txt / paste / ocr)")

    did = (x_device_id or "").strip()
    if _entitlements_enforce():
        if not did:
            raise HTTPException(
                status_code=400,
                detail="缺少 X-Device-Id，无法扣次。请刷新页面或更新客户端。",
            )
        with db._connect() as conn:
            ok, reason = consume_credit_for_analyze(
                conn, did, initial_credits=_initial_device_credits()
            )
            conn.commit()
        if not ok:
            raise HTTPException(
                status_code=402,
                detail=f"分析次数不足（{reason}）。请关注公众号领取或兑换卡密。",
            )

    normalized_chat_text = upload_path.read_text(encoding="utf-8", errors="replace")
    try:
        system_prompt, user_prompt = build_system_and_user_prompts(
            stage=a.stage,
            scenario=a.scenario,
            tags=a.tags,
            normalized_chat_text=normalized_chat_text,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    report_text = llm_client.chat(
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        temperature=float(req.temperature),
    )

    model_name = getattr(llm_client, "model", "unknown")
    db.save_report(archive_id, model=model_name, report_markdown=report_text)
    return AnalyzeResult(archive_id=archive_id, model=model_name, report_markdown=report_text)

