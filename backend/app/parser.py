from __future__ import annotations

import re


_RE_TIME_SENDER_COLON = re.compile(
    r"^\s*(?P<date>\d{4}[./-]\d{1,2}[./-]\d{1,2})"
    r"\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?)"
    r"(?:\s+|[|：-])"
    r"(?P<sender>[^:：]+?)"
    r"[:：]\s*(?P<content>.*)\s*$"
)

_RE_DATE_TIME_SENDER = re.compile(
    r"^\s*(?P<datetime>\d{4}[./-]\d{1,2}[./-]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)"
    r"(?:\s+|[|：-])"
    r"(?P<sender>[^:：]+?)"
    r"[:：]\s*(?P<content>.*)\s*$"
)

_RE_SENDER_COLON_ONLY = re.compile(r"^\s*(?P<sender>[^:：]+?)[:：]\s*(?P<content>.*)\s*$")


def normalize_wx_txt(raw_text: str) -> str:
    """
    Best-effort normalization for common WeChat exported txt formats.
    Output lines are formatted as: `time | sender | content` (when possible),
    otherwise keep the original line.
    """

    lines = raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out_lines: list[str] = []

    for line in lines:
        s = line.strip()
        if not s:
            continue

        m = _RE_TIME_SENDER_COLON.match(s) or _RE_DATE_TIME_SENDER.match(s)
        if m:
            date = m.groupdict().get("date")
            time = m.groupdict().get("time")
            datetime_ = m.groupdict().get("datetime")
            sender = (m.groupdict().get("sender") or "").strip()
            content = (m.groupdict().get("content") or "").strip()
            stamp = f"{date} {time}".strip() if date and time else (datetime_ or "").strip()
            if sender and stamp:
                out_lines.append(f"{stamp} | {sender} | {content}")
                continue

        m2 = _RE_SENDER_COLON_ONLY.match(s)
        if m2:
            sender = (m2.groupdict().get("sender") or "").strip()
            content = (m2.groupdict().get("content") or "").strip()
            if sender:
                out_lines.append(f"na | {sender} | {content}")
                continue

        out_lines.append(s)

    return "\n".join(out_lines)

