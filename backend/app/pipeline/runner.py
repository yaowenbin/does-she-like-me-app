from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..db import Database
from ..llm_client import default_reasoner_model
from .report_graph import make_report_graph
from .schemas import SupportsLLMComplete


@dataclass(frozen=True)
class PipelineOutput:
    final_report: str
    model_label: str
    usage_steps: List[Dict[str, Any]]
    execution_trace: List[Dict[str, Any]]
    pipeline_version: str
    deep_reasoning_requested: bool
    deep_reasoning_used: bool
    reasoner_failed: bool
    reasoner_error: Optional[str]


def run_report_pipeline(
    *,
    llm: SupportsLLMComplete,
    db: Database,
    archive_id: str,
    run_id: str,
    stage: str,
    scenario: str,
    tags: dict,
    normalized_chat_text: str,
    temperature: float,
    deep_reasoning: bool,
    reasoner_model: Optional[str] = None,
    pipeline_version: str = "graph-v1",
) -> PipelineOutput:
    """
    LangGraph：build → base →（可选）reasoner | finalize。
    计费与部分退款由 main 在图外处理（reasoner 失败退深度附加次数）。
    """
    rm = (reasoner_model or default_reasoner_model()).strip()
    graph = make_report_graph(llm=llm, db=db, reasoner_model=rm, pipeline_version=pipeline_version)
    init: dict = {
        "archive_id": archive_id,
        "run_id": run_id,
        "stage": stage,
        "scenario": scenario,
        "tags": tags or {},
        "normalized_chat_text": normalized_chat_text,
        "temperature": temperature,
        "deep_reasoning": deep_reasoning,
    }
    out = graph.invoke(init)
    usage_records = list(out.get("usage_records") or [])
    execution_trace = list(out.get("execution_trace") or [])
    models_used = list(out.get("models_used") or [])
    uniq: list[str] = []
    for m in models_used:
        if m and m not in uniq:
            uniq.append(m)
    model_label = "+".join(uniq) if uniq else "unknown"

    reasoner_failed = bool(out.get("reasoner_failed"))
    has_reasoner_body = bool((out.get("reasoner_report") or "").strip())
    deep_used = bool(deep_reasoning and has_reasoner_body and not reasoner_failed)

    return PipelineOutput(
        final_report=(out.get("final_report") or "").strip(),
        model_label=model_label,
        usage_steps=usage_records,
        execution_trace=execution_trace,
        pipeline_version=pipeline_version,
        deep_reasoning_requested=deep_reasoning,
        deep_reasoning_used=deep_used,
        reasoner_failed=reasoner_failed,
        reasoner_error=(out.get("reasoner_error") or "").strip() or None,
    )
