from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


SKILL_IDS = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10")

DEFAULT_WEIGHTS: Dict[str, float] = {
    "S1": 0.15,
    "S2": 0.15,
    "S3": 0.10,
    "S4": 0.10,
    "S5": 0.10,
    "S6": 0.10,
    "S7": 0.05,
    "S8": 0.10,
    "S9": 0.10,
    "S10": 0.05,
}

SKILL_NAMES: Dict[str, str] = {
    "S1": "主动互动频次与质量",
    "S2": "情绪投入与共情能力",
    "S3": "边界感与排他性",
    "S4": "行为一致性与长期稳定性",
    "S5": "语言细节与潜意识信号",
    "S6": "投入成本与优先级",
    "S7": "社交背书与态度公开",
    "S8": "人格与性格校正",
    "S9": "场景与关系阶段校正",
    "S10": "反向排除（风险校正）",
}


@dataclass(frozen=True)
class DomainOutput:
    scoring: Dict[str, Any]
    friendly: Dict[str, Any]


def _clamp(v: float, low: float = 1.0, high: float = 5.0) -> float:
    return max(low, min(high, v))


def _band(score: float) -> str:
    if score < 2.1:
        return "偏低（更像礼貌/距离感）"
    if score < 2.9:
        return "信号混在一起（暧昧/边界不清）"
    if score < 3.6:
        return "中等（有在意但不稳定）"
    if score < 4.2:
        return "中等偏高（有好感试探）"
    return "偏高（接近确定但仍需验证）"


def _confidence(coverage_ratio: float) -> str:
    if coverage_ratio >= 0.75:
        return "high"
    if coverage_ratio >= 0.45:
        return "medium"
    return "low"


def _adjust_weights(
    base: Dict[str, float],
    signal: Dict[str, Any],
    weight_delta: Dict[str, float] | None = None,
) -> Dict[str, float]:
    weights = dict(base)
    profile = str((signal.get("profile") or "").strip())
    stage = str((signal.get("relation_stage") or "").strip())
    scene = str((signal.get("context_scene") or "").strip())
    if "内向" in profile:
        weights["S1"] = max(0.10, weights["S1"] - 0.03)
        weights["S4"] = weights["S4"] + 0.02
        weights["S5"] = weights["S5"] + 0.01
    if "外向" in profile:
        weights["S1"] = weights["S1"] + 0.02
        weights["S3"] = weights["S3"] + 0.02
        weights["S5"] = max(0.07, weights["S5"] - 0.01)
    if stage in ("初识", "暧昧"):
        weights["S1"] = weights["S1"] + 0.01
        weights["S2"] = weights["S2"] + 0.01
        weights["S4"] = max(0.08, weights["S4"] - 0.02)
    if stage in ("追求中", "稳定相处"):
        weights["S4"] = weights["S4"] + 0.02
        weights["S6"] = weights["S6"] + 0.01
    if "异地" in scene:
        weights["S2"] = weights["S2"] + 0.01
        weights["S6"] = max(0.08, weights["S6"] - 0.01)
    if weight_delta:
        for sid, dv in weight_delta.items():
            if sid in weights:
                weights[sid] = max(0.01, weights[sid] + float(dv))
    total = sum(weights.values())
    if total <= 0:
        return dict(base)
    return {k: v / total for k, v in weights.items()}


def _to_1_5(x: float, base: float = 1.0, span: float = 4.0) -> float:
    return _clamp(base + span * x)


def score_from_signal(
    signal: Dict[str, Any],
    *,
    weight_delta: Dict[str, float] | None = None,
) -> DomainOutput:
    m = signal.get("metrics") or {}
    anomalies = list(signal.get("anomalies") or [])
    coverage = float(m.get("coverage_ratio") or 0.0)
    ask_ratio = float(m.get("other_ask_ratio") or 0.0)
    care_hits = float(m.get("care_hits") or 0.0)
    future_hits = float(m.get("future_hits") or 0.0)
    exclusive_hits = float(m.get("exclusive_hits") or 0.0)
    social_hits = float(m.get("social_hits") or 0.0)
    risk_hits = float(m.get("risk_hits") or 0.0)
    other_msg_ratio = float(m.get("other_message_ratio") or 0.0)
    dialog_turns = float(m.get("dialog_turns") or 0.0)
    proposal_hits = float(m.get("proposal_hits") or 0.0)
    cost_hits = float(m.get("cost_hits") or 0.0)
    boundary_hits = float(m.get("boundary_hits") or 0.0)
    public_hits = float(m.get("public_hits") or 0.0)
    first_counterparty = float(m.get("first_counterparty") or 0.0)
    nickname_hits = float(m.get("nickname_hits") or 0.0)
    we_hits = float(m.get("we_hits") or 0.0)

    s1 = _clamp(1.0 + proposal_hits * 0.6 + ask_ratio * 1.5 + first_counterparty * 0.5)
    s2 = _clamp(1.0 + care_hits * 0.8 + ask_ratio * 1.2 + (0.4 if risk_hits == 0 else 0.0))
    s3 = _clamp(1.0 + exclusive_hits * 0.5 + boundary_hits * 0.4 + public_hits * 0.5 - (0.6 if risk_hits > 0 else 0.0))
    s4 = _clamp(1.0 + coverage * 2.0 + min(dialog_turns / 20.0, 1.0) * 1.2 + (1.0 - min(risk_hits / 3.0, 1.0)) * 1.2)
    s5 = _clamp(1.0 + nickname_hits * 0.8 + we_hits * 0.4 + ask_ratio * 0.7)
    s6 = _clamp(1.0 + cost_hits * 0.35 + proposal_hits * 0.35 + future_hits * 0.2)
    s7 = _clamp(1.0 + social_hits * 0.9 + public_hits * 0.8)
    s8 = _to_1_5(0.55 if str((signal.get("profile") or "")).strip() else 0.35)
    s9 = _to_1_5(0.6 if str((signal.get("relation_stage") or "")).strip() and str((signal.get("context_scene") or "")).strip() else 0.35)
    s10 = _clamp(5.0 - min(4.2, risk_hits * 1.3 + len(anomalies) * 0.65))

    skill_scores: Dict[str, float] = {
        "S1": round(s1, 2),
        "S2": round(s2, 2),
        "S3": round(s3, 2),
        "S4": round(s4, 2),
        "S5": round(s5, 2),
        "S6": round(s6, 2),
        "S7": round(s7, 2),
        "S8": round(s8, 2),
        "S9": round(s9, 2),
        "S10": round(s10, 2),
    }

    weights = _adjust_weights(DEFAULT_WEIGHTS, signal, weight_delta)
    total_1_5 = sum(skill_scores[k] * weights[k] for k in SKILL_IDS)
    raw_score = (total_1_5 - 1.0) / 4.0 * 100
    if raw_score > 65:
        raw_score = raw_score + (raw_score - 65) * 0.5
    total_score = int(round(raw_score))
    total_score = max(0, min(100, total_score))
    level = _band(total_1_5)
    conf = _confidence(coverage)

    ranked = sorted(
        SKILL_IDS,
        key=lambda k: (skill_scores[k] - 3.0) * weights[k],
        reverse=True,
    )
    top_reasons = []
    for sid in ranked[:3]:
        top_reasons.append(
            {
                "skill_id": sid,
                "skill_name": SKILL_NAMES[sid],
                "score": skill_scores[sid],
                "weight": round(weights[sid], 4),
            }
        )

    deductions: List[Dict[str, Any]] = []
    if risk_hits > 0:
        deductions.append(
            {
                "skill_id": "S10",
                "reason": "命中风险对话模式，已进行风险校正",
                "risk_hits": int(risk_hits),
            }
        )
    for a in anomalies:
        deductions.append({"skill_id": "S10", "reason": str(a)})

    risk_flags: List[str] = []
    if risk_hits >= 2:
        risk_flags.append("利用风险")
    if skill_scores["S3"] <= 2.4:
        risk_flags.append("边界不清")
    if skill_scores["S4"] <= 2.5:
        risk_flags.append("关系不稳定")
    if not risk_flags:
        risk_flags.append("未见显著高风险")

    friendly = {
        "headline": level,
        "score": total_score,
        "confidence": conf,
        "easy_summary": (
            "你们之间有一定互动基础，建议先看“是否稳定、是否尊重边界”，"
            "再决定投入节奏。"
            if total_score >= 50
            else "当前更像“有互动但不够稳定”。先保护自己的节奏，不要重投入。"
        ),
        "top_reasons": top_reasons,
        "risk_flags": risk_flags,
        "next_step": "发一个低压力、可退出的小邀约，观察对方是否愿意给出具体时间或主动延续。",
        "stop_rule": "若连续 2-3 次关键互动被回避或长期只有你单向投入，建议暂停投入并拉开节奏。",
    }

    scoring = {
        "total_score": total_score,
        "level": level,
        "skill_scores": skill_scores,
        "weight_snapshot": {k: round(v, 4) for k, v in weights.items()},
        "deductions": deductions,
        "reasons": top_reasons,
        "confidence": conf,
        "trend_delta": "na",
    }
    return DomainOutput(scoring=scoring, friendly=friendly)


def tune_weight_delta(
    *,
    verdict: str,
    scoring_result: Dict[str, Any],
    current_delta: Dict[str, float] | None = None,
) -> Dict[str, float]:
    updated = dict(current_delta or {})
    reasons = list(scoring_result.get("reasons") or [])
    skill_scores = dict(scoring_result.get("skill_scores") or {})
    if verdict == "accurate":
        for r in reasons[:3]:
            sid = str(r.get("skill_id") or "")
            if sid in DEFAULT_WEIGHTS:
                updated[sid] = round(float(updated.get(sid) or 0.0) + 0.004, 4)
    else:
        for r in reasons[:3]:
            sid = str(r.get("skill_id") or "")
            if sid in DEFAULT_WEIGHTS:
                updated[sid] = round(float(updated.get(sid) or 0.0) - 0.005, 4)
        for sid in ("S3", "S4", "S10"):
            if sid in DEFAULT_WEIGHTS:
                base = float(updated.get(sid) or 0.0)
                if float(skill_scores.get(sid) or 3.0) < 3.0:
                    base += 0.003
                updated[sid] = round(base, 4)
    for sid in list(updated.keys()):
        updated[sid] = max(-0.06, min(0.06, float(updated[sid])))
    return updated
