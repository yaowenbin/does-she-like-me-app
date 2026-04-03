from __future__ import annotations

import re
from pathlib import Path

from app.domain_core import score_from_signal
from app.signal_extractor import extract_input_signal


ROOT = Path(__file__).resolve().parents[1]
CASE_FILE = ROOT / "测试用例.md"


def _load_cases() -> list[dict]:
    text = CASE_FILE.read_text(encoding="utf-8", errors="replace")
    blocks = []
    for title, expected in (("第一组", 15), ("第二组", 52), ("第三组", 88)):
        m = re.search(rf"{title}：[\s\S]*?测试对话文本[\s\S]*?\n\n([\s\S]*?)\n\n预估评价", text)
        if not m:
            raise RuntimeError(f"missing case block: {title}")
        dialog = m.group(1).strip()
        blocks.append({"title": title, "expected": expected, "dialog": dialog})
    return blocks


def _score(dialog: str, *, stage: str = "暧昧", scene: str = "线上主导") -> int:
    signal = extract_input_signal(
        normalized_chat_text=dialog,
        stage=stage,
        scenario=scene,
        tags={},
    )
    out = score_from_signal(signal)
    return int(out.scoring["total_score"])


def main() -> int:
    cases = _load_cases()
    results = []
    for c in cases:
        got = _score(c["dialog"])
        results.append((c["title"], c["expected"], got))
    print("回归评分结果：")
    for title, exp, got in results:
        print(f"- {title}: expected≈{exp}, got={got}")
    low, mid, high = results[0][2], results[1][2], results[2][2]
    if not (low <= 30 and 35 <= mid <= 70 and high >= 70):
        raise SystemExit("❌ 回归阈值未通过，请检查 signal_extractor/domain_core")
    print("✅ 回归阈值通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
