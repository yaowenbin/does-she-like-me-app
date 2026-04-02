from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def main() -> int:
    here = Path(__file__).resolve()
    workspace_root = here.parents[2]
    backend_dir = here.parent

    sys.path.insert(0, str(backend_dir))

    # isolate IO
    test_data_dir = backend_dir / ".test_data_chain"
    os.environ["DATA_DIR"] = str(test_data_dir)

    skill_root = (
        workspace_root / "code" / "Day7" / "does-she-like-me" / "skills" / "does-she-like-me"
    )
    os.environ["DOES_SHE_LIKE_ME_SKILL_ROOT"] = str(skill_root)

    # force stub
    os.environ.pop("OPENAI_API_KEY", None)

    from app.db import Database
    from app.llm_client import create_llm_client

    # NOTE: In this codebase normalize_wx_txt lives in app.parser
    from app.parser import normalize_wx_txt
    from app.prompt_builder import build_system_and_user_prompts

    db = Database(test_data_dir / "does-she-like-me.sqlite3")
    llm_client = create_llm_client()

    # 1) OCR dependency check (no need to run OCR if tesseract missing)
    tesseract_path = shutil.which("tesseract")
    ocr_dep_ok = tesseract_path is not None

    # 2) normalize + build prompts + stub chat
    paste_text = "小红：你好\n小蓝：最近怎么样？\n"
    normalized = normalize_wx_txt(paste_text)
    if not normalized.strip():
        print("normalize_wx_txt: FAIL (empty)")
        return 1

    system_prompt, user_prompt = build_system_and_user_prompts(
        stage="na",
        scenario="na",
        tags={},
        normalized_chat_text=normalized,
    )
    if not system_prompt.strip() or not user_prompt.strip():
        print("build_system_and_user_prompts: FAIL (empty prompts)")
        return 2

    report_md = llm_client.chat(
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        temperature=0.3,
    )
    if not report_md.strip():
        print("llm_client.chat: FAIL (empty report)")
        return 3

    # 3) persist report
    archive_id = "chain-smoke"
    db.create_archive(
        archive_id,
        name="chain-smoke",
        stage="na",
        scenario="na",
        tags={},
    )
    db.save_report(archive_id, model=getattr(llm_client, "model", "unknown"), report_markdown=report_md)

    report = db.get_report(archive_id) or {}
    ok_stub = "Stub" in report.get("report_markdown", "") or "未检测到" in report.get("report_markdown", "")

    print(
        "CHAIN SMOKE RESULT:",
        {
            "ocr_dependency_ok": ocr_dep_ok,
            "normalize_ok": True,
            "prompts_ok": True,
            "stub_report_ok": ok_stub,
        },
    )

    if not ok_stub:
        return 4

    # We treat OCR dependency missing as expected failure, not a chain failure.
    print("SMOKE TEST: PASS (analysis chain OK; OCR dependency may require system tesseract.exe)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

