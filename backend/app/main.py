from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .db import Database
from .llm_client import create_llm_client
from .models import AnalyzeRequest, AnalyzeResult, CreateArchiveRequest, PasteImportRequest
from .parser import normalize_wx_txt
from .prompt_builder import build_system_and_user_prompts
from .ocr import ocr_image_bytes


def get_data_dir() -> Path:
    # default: does-she-like-me-web/backend/data
    return Path(os.getenv("DATA_DIR") or (Path(__file__).resolve().parents[2] / "data"))


data_dir = get_data_dir()
uploads_dir = data_dir / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)

db = Database(data_dir / "does-she-like-me.sqlite3")
llm_client = create_llm_client()

app = FastAPI(title="does-she-like-me-web API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


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
) -> AnalyzeResult:
    a = db.get_archive(archive_id)
    if not a:
        raise HTTPException(status_code=404, detail="archive not found")
    upload_path = db.get_upload_path(archive_id)
    if not upload_path or not upload_path.is_file():
        raise HTTPException(status_code=400, detail="missing imported content (wx-txt / paste / ocr)")

    normalized_chat_text = upload_path.read_text(encoding="utf-8", errors="replace")
    system_prompt, user_prompt = build_system_and_user_prompts(
        stage=a.stage,
        scenario=a.scenario,
        tags=a.tags,
        normalized_chat_text=normalized_chat_text,
    )

    report_text = llm_client.chat(
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        temperature=float(req.temperature),
    )

    model_name = getattr(llm_client, "model", "unknown")
    db.save_report(archive_id, model=model_name, report_markdown=report_text)
    return AnalyzeResult(archive_id=archive_id, model=model_name, report_markdown=report_text)

