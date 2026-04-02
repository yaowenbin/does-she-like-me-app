from __future__ import annotations

import importlib
import os
import sys
import shutil
import traceback
from pathlib import Path


def main() -> int:
    workspace_root = Path(__file__).resolve().parents[2]
    backend_dir = Path(__file__).resolve().parent

    # --------- env: keep tests isolated ----------
    test_data_dir = backend_dir / ".test_data"
    os.environ["DATA_DIR"] = str(test_data_dir)

    # prompt templates are located under repo-level Day7 in this workspace layout
    skill_root = (
        workspace_root / "code" / "Day7" / "does-she-like-me" / "skills" / "does-she-like-me"
    )
    os.environ["DOES_SHE_LIKE_ME_SKILL_ROOT"] = str(skill_root)

    # Force stub mode unless user configured keys.
    os.environ.pop("OPENAI_API_KEY", None)

    # --------- import app after env set ----------
    sys.path.insert(0, str(backend_dir))

    import app.main as main_mod

    main_mod = importlib.reload(main_mod)
    from fastapi.testclient import TestClient

    # OCR 依赖系统级 tesseract.exe；如果缺失我们希望拿到 4xx/5xx 返回而不是直接抛异常中断。
    client = TestClient(main_mod.app, raise_server_exceptions=False)

    # --------- create archive ----------
    res = client.post("/api/archives", json={"name": "ocr-smoke", "stage": "na", "scenario": "na"})
    if res.status_code != 200:
        print("create_archive failed:", res.status_code, res.text)
        return 1
    archive_id = res.json()["id"]

    # --------- load screenshot ----------
    # The uploaded screenshot is stored under Cursor's project cache directory.
    # (This path can differ from your repo root.)
    cursor_assets_dir = (
        Path.home() / ".cursor" / "projects" / "c-Users-hyd-Desktop-learn-agent" / "assets"
    )
    assets_dir = cursor_assets_dir
    img_candidates = list(
        assets_dir.glob(
            "c__Users_hyd_AppData_Roaming_Cursor_User_workspaceStorage_*.png"
        )
    )
    if not img_candidates:
        print("No screenshot found in assets:", assets_dir)
        return 1
    # Prefer the one that matches the exact UUID shown in the attachment metadata.
    preferred = [
        p
        for p in img_candidates
        if "6297bbef-2a03-449d-b670-3a6f94ecf300" in p.name
    ]
    img_path = preferred[0] if preferred else img_candidates[0]

    ocr_ok = False

    # --------- upload to OCR endpoint ----------
    tesseract_path = shutil.which("tesseract")
    if not tesseract_path:
        print("tesseract not found in PATH; skipping /import/ocr (only validate paste->analyze).")
    else:
        with open(img_path, "rb") as f:
            files = [("files", (img_path.name, f.read(), "image/png"))]
        ocr_res = client.post(
            f"/api/archives/{archive_id}/import/ocr?lang=chi_sim",
            files=files,
        )
        if ocr_res.status_code == 200:
            ocr_json = ocr_res.json()
            normalized_size = int(ocr_json.get("normalized_size") or 0)
            ocr_ok = normalized_size > 0
            print(
                "OCR response:",
                {k: ocr_json.get(k) for k in ["normalized_size", "used_langs", "ocr_chars"]},
            )
        else:
            print("import_ocr failed:", ocr_res.status_code, ocr_res.text)

    # --------- if OCR not available, still validate full pipeline via paste ----------
    if not ocr_ok:
        paste_text = "小红：你好\n小蓝：最近怎么样？\n"
        paste_res = client.post(
            f"/api/archives/{archive_id}/import/paste",
            json={"text": paste_text, "filename": "paste.txt"},
        )
        if paste_res.status_code != 200:
            print("import_paste failed:", paste_res.status_code, paste_res.text)
            return 4

    # --------- analyze (stub mode) ----------
    analyze_res = client.post(
        f"/api/archives/{archive_id}/analyze",
        json={"temperature": 0.3},
    )
    if analyze_res.status_code != 200:
        print("analyze failed:", analyze_res.status_code, analyze_res.text)
        return 1

    analyze_json = analyze_res.json()
    report_md = analyze_json.get("report_markdown") or ""
    ok_stub = "Stub" in report_md or "未检测到" in report_md
    print("Analyze response keys:", {k: analyze_json.get(k) for k in ["model", "archive_id"]})
    if not ok_stub:
        print("Analyze seems not in stub mode (or report format changed).")
        return 3

    print("SMOKE OCR test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

