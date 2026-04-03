from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Tuple


_QUESTION_RE = re.compile(r"[?？]")
_CARE_RE = re.compile(r"(辛苦|累吗|别难过|抱抱|抱抱你|早点休息|注意身体|开心|加油|想你|担心|别紧张|我听你|我就知道你可以|你放心|庆祝)")
_FUTURE_RE = re.compile(r"(周末|下次|以后|一起|见面|约|带你|我们)")
_EXCLUSIVE_RE = re.compile(r"(只对你|只和你|不想别人|边界|暧昧|专属|公开|介绍朋友|见家人)")
_SOCIAL_RE = re.compile(r"(朋友圈|见朋友|见家人|介绍朋友|公开|我跟他们说)")
_RISK_RE = re.compile(r"(借钱|借我|转账|转我|帮我做|深夜emo|别问|别管|别公开|别告诉别人|明天还你)")
_NICKNAME_RE = re.compile(r"(宝|宝宝|宝贝|亲爱的|小可爱|笨蛋|乖)")
_WE_RE = re.compile(r"(我们)")
_ROLE_RE = re.compile(r"^\s*(我|对方|Ta|TA|她|他|你|女方|男方|A|B)\s*[：:]\s*(.+)$")
_PROPOSAL_RE = re.compile(r"(要不要|我们.*(去|吃|见|约)|我订了|我在你家楼下|一起庆祝|下周末)")
_COST_RE = re.compile(r"(早起|送|订了|买了|陪你|提前走|查了|记着|记得|特意)")
_BOUNDARY_RE = re.compile(r"(我跟他们说|提前走了|拒绝|只陪你|你放心)")
_PUBLIC_RE = re.compile(r"(朋友圈|见朋友|见家人|我跟他们说)")


def _parse_line(line: str) -> Tuple[str, str, str]:
    m = _ROLE_RE.match(line.strip())
    if m:
        role = m.group(1).strip()
        content = m.group(2).strip()
        sender = "self" if role in ("我",) else "counterparty"
        return "na", sender, content
    parts = [p.strip() for p in line.split("|")]
    if len(parts) >= 3:
        sender_raw = parts[1]
        sender = sender_raw
        if sender_raw in ("我", "self", "me"):
            sender = "self"
        elif sender_raw in ("对方", "ta", "TA", "她", "他", "counterparty"):
            sender = "counterparty"
        return parts[0], sender, "|".join(parts[2:]).strip()
    return "na", "unknown", line.strip()


def _parse_time(ts: str) -> datetime | None:
    if not ts or ts == "na":
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    return None


def _guess_counterparty(senders: Counter[str]) -> str:
    if "counterparty" in senders:
        return "counterparty"
    if "self" in senders and len(senders) == 1:
        return "unknown"
    if not senders:
        return "unknown"
    common = [s for s, _ in senders.most_common(3)]
    for s in common:
        low = s.lower()
        if any(k in low for k in ("我", "me", "self", "本人")):
            continue
        return s
    return common[0]


def extract_input_signal(
    *,
    normalized_chat_text: str,
    stage: str,
    scenario: str,
    tags: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    lines = [l for l in (normalized_chat_text or "").splitlines() if l.strip()]
    parsed: List[Tuple[str, str, str]] = [_parse_line(l) for l in lines]
    senders = Counter(p[1] for p in parsed if p[1] and p[1] != "unknown")
    counterparty = _guess_counterparty(senders)
    total = len(parsed)
    if total == 0:
        return {
            "profile": "",
            "relation_stage": stage or "",
            "context_scene": scenario or "",
            "metrics": {"coverage_ratio": 0.0, "dialog_turns": 0},
            "anomalies": ["样本为空"],
        }

    other_msgs = [p for p in parsed if p[1] == counterparty]
    other_contents = [p[2] for p in other_msgs]
    other_text = "\n".join(p[2] for p in other_msgs)
    all_text = "\n".join(p[2] for p in parsed)
    ask_hits = sum(1 for _, _, c in other_msgs if _QUESTION_RE.search(c))
    care_hits = sum(1 for c in other_contents if _CARE_RE.search(c))
    future_hits = sum(1 for c in other_contents if _FUTURE_RE.search(c))
    exclusive_hits = sum(1 for c in other_contents if _EXCLUSIVE_RE.search(c))
    social_hits = sum(1 for c in other_contents if _SOCIAL_RE.search(c))
    risk_hits = sum(1 for c in other_contents if _RISK_RE.search(c))
    nickname_hits = sum(1 for c in other_contents if _NICKNAME_RE.search(c))
    we_hits = sum(1 for c in other_contents if _WE_RE.search(c))
    proposal_hits = sum(1 for c in other_contents if _PROPOSAL_RE.search(c))
    cost_hits = sum(1 for c in other_contents if _COST_RE.search(c))
    boundary_hits = sum(1 for c in other_contents if _BOUNDARY_RE.search(c))
    public_hits = sum(1 for c in other_contents if _PUBLIC_RE.search(c))
    first_sender = parsed[0][1] if parsed else "unknown"
    first_counterparty = 1 if first_sender == counterparty else 0

    known_time = 0
    reply_samples = 0
    prev_sender = ""
    prev_time: datetime | None = None
    reply_mins_total = 0.0
    turns = 0
    for ts, sender, _content in parsed:
        cur_time = _parse_time(ts)
        if cur_time:
            known_time += 1
        if sender != prev_sender and prev_sender:
            turns += 1
            if cur_time and prev_time:
                delta = (cur_time - prev_time).total_seconds() / 60.0
                if delta >= 0:
                    reply_mins_total += delta
                    reply_samples += 1
        prev_sender = sender
        prev_time = cur_time if cur_time else prev_time

    avg_reply_mins = (reply_mins_total / reply_samples) if reply_samples > 0 else 0.0
    coverage_ratio = min(1.0, (known_time / max(1, total)) * 0.6 + (min(total, 80) / 80.0) * 0.4)
    anomalies: List[str] = []
    if total < 12:
        anomalies.append("样本偏少")
    if risk_hits >= 1:
        anomalies.append("存在潜在利用或情绪索取信号")

    profile = ""
    if tags:
        profile = str(tags.get("profile") or tags.get("personality") or "").strip()

    metrics: Dict[str, Any] = {
        "dialog_turns": turns,
        "other_message_ratio": round(len(other_msgs) / max(1, total), 4),
        "other_ask_ratio": round(ask_hits / max(1, len(other_msgs)), 4),
        "care_hits": care_hits,
        "future_hits": future_hits,
        "exclusive_hits": exclusive_hits,
        "social_hits": social_hits,
        "risk_hits": risk_hits,
        "nickname_hits": nickname_hits,
        "we_hits": we_hits,
        "proposal_hits": proposal_hits,
        "cost_hits": cost_hits,
        "boundary_hits": boundary_hits,
        "public_hits": public_hits,
        "first_counterparty": first_counterparty,
        "avg_reply_mins": round(avg_reply_mins, 2),
        "coverage_ratio": round(coverage_ratio, 4),
        "counterparty_sender": counterparty,
    }
    return {
        "profile": profile,
        "relation_stage": stage or "",
        "context_scene": scenario or "",
        "metrics": metrics,
        "anomalies": anomalies,
    }
