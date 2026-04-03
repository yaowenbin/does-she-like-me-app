from __future__ import annotations

import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import cast


def main() -> int:
    here = Path(__file__).resolve()
    workspace_root = here.parents[2]
    backend_dir = here.parent

    sys.path.insert(0, str(backend_dir))

    test_data_dir = backend_dir / ".test_data_pipeline"
    shutil.rmtree(test_data_dir, ignore_errors=True)
    os.environ["DATA_DIR"] = str(test_data_dir)

    skill_root = (
        workspace_root / "code" / "Day7" / "does-she-like-me" / "skills" / "does-she-like-me"
    )
    os.environ["DOES_SHE_LIKE_ME_SKILL_ROOT"] = str(skill_root)
    # 避免烟测卡在首次 git clone 技能包
    os.environ["DOES_SHE_LIKE_ME_SKILLS_AUTO_INSTALL"] = "0"
    os.environ.pop("OPENAI_API_KEY", None)

    if not skill_root.is_dir():
        print("SKIP pipeline smoke: skill root not found:", skill_root)
        return 0

    from app.db import Database
    from app.llm_client import create_llm_client
    from app.parser import normalize_wx_txt
    from app.pipeline.runner import run_report_pipeline
    from app.pipeline.schemas import SupportsLLMComplete

    db = Database(test_data_dir / "does-she-like-me.sqlite3")
    llm = create_llm_client()
    normalized = normalize_wx_txt("小红：你好\n小蓝：在的\n")
    if not normalized.strip():
        print("normalize: FAIL")
        return 1

    run_id = uuid.uuid4().hex
    out = run_report_pipeline(
        llm=cast(SupportsLLMComplete, llm),
        db=db,
        archive_id="pipe-smoke",
        run_id=run_id,
        stage="na",
        scenario="na",
        tags={},
        normalized_chat_text=normalized,
        temperature=0.3,
        deep_reasoning=False,
    )
    if not out.final_report.strip():
        print("pipeline: FAIL empty final_report")
        return 2
    if len(out.usage_steps) < 1:
        print("pipeline: FAIL expected at least 1 usage step, got", out.usage_steps)
        return 3
    print(
        "PIPELINE SMOKE OK",
        {
            "model_label": out.model_label,
            "steps": len(out.usage_steps),
            "deep_used": out.deep_reasoning_used,
            "reasoner_failed": out.reasoner_failed,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
