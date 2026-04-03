from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AiTraceAudit:
    score: float
    reasons: list[str]


def _count(pattern: str, text: str) -> int:
    return len(re.findall(pattern, text, flags=re.MULTILINE))


def ai_trace_audit(report_markdown: str) -> AiTraceAudit:
    """
    轻量启发式审计：用于“QA 质量控制/风格修复”的内部指标。
    不保证识别真实 AI 来源，只衡量“模板重复/符号堆叠/格式异常”等风险因子。
    """

    t = report_markdown or ""
    if not t.strip():
        return AiTraceAudit(score=0.0, reasons=["empty"])

    reasons: list[str] = []
    score = 0.0

    # 1) 过多粗体标记（可能对应“模板化加粗”）
    bold_cnt = _count(r"\*\*", t)
    if bold_cnt > 30:
        score += min(0.35, (bold_cnt - 30) / 200)
        reasons.append(f"bold_cnt={bold_cnt}")

    # 2) 已知重复前缀：综合区间被模型嵌套加粗后容易重复
    dup_interval = 1 if re.search(r"综合区间[:：]\s*\*+?\s*综合区间[:：]", t) else 0
    if dup_interval:
        score += 0.25
        reasons.append("dup_interval_prefix")

    # 3) 连续重复行（LLM 在段落模板拼接时偶发）
    lines = [ln.strip() for ln in t.splitlines()]
    consec_dup = 0
    for i in range(1, len(lines)):
        if lines[i] and lines[i] == lines[i - 1]:
            consec_dup += 1
    if consec_dup > 0:
        score += min(0.25, consec_dup * 0.05)
        reasons.append(f"consec_dup={consec_dup}")

    # 4) 多次出现“步骤/小节”固定模板句式（只做轻权重）
    tpl_cnt = _count(r"###|##\s+冲突调解|###\s+三种叙事|###\s+下一步", t)
    if tpl_cnt > 2:
        score += min(0.15, (tpl_cnt - 2) * 0.03)
        reasons.append(f"section_tpl_cnt={tpl_cnt}")

    # clamp
    score = float(max(0.0, min(1.0, score)))
    if not reasons:
        reasons = ["no_major_flags"]
    return AiTraceAudit(score=score, reasons=reasons)


def sanitize_ai_trace(report_markdown: str) -> str:
    """
    确定性修复：尽量不改结构，仅做“去重复/去嵌套/格式归一”。
    """

    t = report_markdown or ""
    if not t.strip():
        return ""

    # 1) 修复“综合区间：**综合区间：...**”类重复前缀
    t = re.sub(
        r"综合区间[:：]\s*\*+\s*综合区间[:：]\s*",
        "综合区间：",
        t,
        flags=re.MULTILINE,
    )
    # 2) 去掉“综合区间：**（多重加粗）综合区间：”的额外加粗嵌套（更保守）
    t = re.sub(r"\*\*(\s*)综合区间[:：]\s*", r"\1综合区间：", t)

    # 3) 连续重复行去重（保留第一条）
    lines = t.splitlines()
    out: list[str] = []
    last = None
    for ln in lines:
        s = ln.strip()
        if s and s == last:
            continue
        out.append(ln)
        last = s
    t = "\n".join(out)

    # 4) 空行归一：最多两连空行
    t = re.sub(r"\n{3,}", "\n\n", t)

    # 5) 去掉尾部多余空白
    t = t.strip()
    return t

