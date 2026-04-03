from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass

from .ai_trace import ai_trace_audit, sanitize_ai_trace


@dataclass(frozen=True)
class HumanizeResult:
    text: str
    used_external: bool
    audit_score: float
    audit_reasons: list[str]
    error: str = ""


def _humanizer_mode() -> str:
    # off | heuristic | auto | external
    return (os.getenv("REPORT_HUMANIZER_MODE") or "auto").strip().lower()


def _audit_threshold() -> float:
    raw = (os.getenv("REPORT_AI_TRACE_THRESHOLD") or "0.35").strip()
    try:
        v = float(raw)
    except Exception:
        v = 0.35
    return max(0.0, min(1.0, v))


def _external_cmd() -> str:
    # Example:
    # REPORT_HUMANIZER_CMD=python c:/tools/humanizer_zh_cli.py
    return (os.getenv("REPORT_HUMANIZER_CMD") or "").strip()


def _external_timeout_sec() -> float:
    raw = (os.getenv("REPORT_HUMANIZER_TIMEOUT_SEC") or "12").strip()
    try:
        v = float(raw)
    except Exception:
        v = 12.0
    return max(1.0, min(60.0, v))


def _run_external_humanizer(cmd: str, text: str) -> str:
    proc = subprocess.run(
        shlex.split(cmd),
        input=text,
        capture_output=True,
        text=True,
        timeout=_external_timeout_sec(),
        check=False,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise RuntimeError(f"humanizer_cmd_failed({proc.returncode}): {stderr[:240]}")
    out = (proc.stdout or "").strip()
    if not out:
        raise RuntimeError("humanizer_cmd_empty_output")
    return out


def humanize_report_text(report_markdown: str) -> HumanizeResult:
    """
    工程化后处理链：
    1) 启发式审计（非来源鉴定，只做风格风险评分）
    2) 先做确定性清洗（去重复前缀/重复行/空行归一）
    3) 根据模式决定是否走外部 humanizer（可插拔开源 CLI）
    """
    raw = report_markdown or ""
    if not raw.strip():
        return HumanizeResult(text="", used_external=False, audit_score=0.0, audit_reasons=["empty"])

    audit = ai_trace_audit(raw)
    cleaned = sanitize_ai_trace(raw)
    mode = _humanizer_mode()
    cmd = _external_cmd()

    if mode in ("off", "heuristic"):
        return HumanizeResult(
            text=cleaned,
            used_external=False,
            audit_score=audit.score,
            audit_reasons=audit.reasons,
        )

    should_external = False
    if mode == "external":
        should_external = bool(cmd)
    else:
        # auto
        should_external = bool(cmd) and audit.score >= _audit_threshold()

    if not should_external:
        return HumanizeResult(
            text=cleaned,
            used_external=False,
            audit_score=audit.score,
            audit_reasons=audit.reasons,
        )

    try:
        out = _run_external_humanizer(cmd, cleaned)
        out = sanitize_ai_trace(out)
        return HumanizeResult(
            text=out,
            used_external=True,
            audit_score=audit.score,
            audit_reasons=audit.reasons,
        )
    except Exception as e:
        # 外部失败时回退确定性清洗结果，不让主流程失败
        return HumanizeResult(
            text=cleaned,
            used_external=False,
            audit_score=audit.score,
            audit_reasons=audit.reasons,
            error=str(e)[:280],
        )

