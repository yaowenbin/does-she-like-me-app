from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from ..db import Database
from ..prompt_builder import build_system_and_user_prompts
from .schemas import SupportsLLMComplete, usage_to_step_dict


class ReportGraphState(TypedDict, total=False):
    archive_id: str
    run_id: str
    stage: str
    scenario: str
    tags: dict
    normalized_chat_text: str
    temperature: float
    deep_reasoning: bool
    system_prompt: str
    user_prompt: str
    base_report: str
    reasoner_report: str
    final_report: str
    reasoner_failed: bool
    reasoner_error: str
    usage_records: Annotated[list[dict], operator.add]
    models_used: Annotated[list[str], operator.add]
    execution_trace: Annotated[list[dict], operator.add]


REASONER_SYSTEM = """你是「她爱你嘛」报告的深度审稿与推理增强器。
用户将提供一份已由主模型生成的 Markdown 分析报告草稿。你的任务是输出**完整**修订版 Markdown：

约束：
- 保留与原稿相同的章节层级与必备结构（含「一眼看懂」「心动指数」等），不得删除整章规避任务。
- 加强：透镜之间的冲突调解、替代解释、不确定性；对证据薄弱处须显式写出「不能确定」。
- 禁止编造聊天中未出现的事实；不得引入原稿未提及的具体数字或伪精确百分比。
- 文风：专业段可适当收紧逻辑；「一眼看懂」保持口语与人话。"""


def make_report_graph(
    *,
    llm: SupportsLLMComplete,
    db: Database,
    reasoner_model: str,
    pipeline_version: str = "graph-v1",
) -> Any:
    _ = pipeline_version  # 预留：后续可写入日志或 metrics

    def node_build(state: ReportGraphState) -> dict:
        s, u = build_system_and_user_prompts(
            stage=state["stage"],
            scenario=state["scenario"],
            tags=state.get("tags") or {},
            normalized_chat_text=state["normalized_chat_text"],
        )
        return {
            "system_prompt": s,
            "user_prompt": u,
            "execution_trace": [{"step": "build", "status": "ok"}],
        }

    def node_base(state: ReportGraphState) -> dict:
        messages = [
            {"role": "system", "content": state["system_prompt"]},
            {"role": "user", "content": state["user_prompt"]},
        ]
        r = llm.complete(messages, temperature=float(state.get("temperature") or 0.3))
        rec = usage_to_step_dict(step="base", result=r)
        db.log_llm_usage(
            archive_id=state["archive_id"],
            run_id=state["run_id"],
            step=rec["step"],
            model=rec["model"],
            prompt_tokens=rec.get("prompt_tokens"),
            completion_tokens=rec.get("completion_tokens"),
            total_tokens=rec.get("total_tokens"),
            prompt_cache_hit_tokens=rec.get("prompt_cache_hit_tokens"),
            prompt_cache_miss_tokens=rec.get("prompt_cache_miss_tokens"),
        )
        return {
            "base_report": r.content,
            "usage_records": [rec],
            "models_used": [r.model],
            "execution_trace": [{"step": "base", "status": "ok", "model": r.model}],
        }

    def node_reasoner(state: ReportGraphState) -> dict:
        draft = state.get("base_report") or ""
        user_msg = (
            "以下为草稿全文。请输出修订后的**完整** Markdown（不要只输出补丁或评论）：\n\n"
            f"-----BEGIN DRAFT-----\n{draft}\n-----END DRAFT-----"
        )
        messages = [
            {"role": "system", "content": REASONER_SYSTEM},
            {"role": "user", "content": user_msg},
        ]
        try:
            r = llm.complete(
                messages,
                temperature=0.35,
                model=reasoner_model,
            )
            rec = usage_to_step_dict(step="reasoner", result=r)
            db.log_llm_usage(
                archive_id=state["archive_id"],
                run_id=state["run_id"],
                step=rec["step"],
                model=rec["model"],
                prompt_tokens=rec.get("prompt_tokens"),
                completion_tokens=rec.get("completion_tokens"),
                total_tokens=rec.get("total_tokens"),
                prompt_cache_hit_tokens=rec.get("prompt_cache_hit_tokens"),
                prompt_cache_miss_tokens=rec.get("prompt_cache_miss_tokens"),
            )
            return {
                "reasoner_report": r.content,
                "final_report": r.content,
                "usage_records": [rec],
                "models_used": [r.model],
                "reasoner_failed": False,
                "reasoner_error": "",
                "execution_trace": [{"step": "reasoner", "status": "ok", "model": r.model}],
            }
        except Exception as e:
            err = str(e)[:800]
            return {
                "final_report": draft,
                "reasoner_failed": True,
                "reasoner_error": err,
                "usage_records": [],
                "models_used": [],
                "execution_trace": [{"step": "reasoner", "status": "failed", "error": err}],
            }

    def node_finalize(state: ReportGraphState) -> dict:
        return {
            "final_report": state.get("base_report") or "",
            "execution_trace": [{"step": "finalize", "status": "ok"}],
        }

    def route_after_base(state: ReportGraphState) -> Literal["reasoner", "finalize"]:
        if state.get("deep_reasoning"):
            return "reasoner"
        return "finalize"

    g = StateGraph(ReportGraphState)
    g.add_node("build", node_build)
    g.add_node("base", node_base)
    g.add_node("reasoner", node_reasoner)
    g.add_node("finalize", node_finalize)
    g.add_edge(START, "build")
    g.add_edge("build", "base")
    g.add_conditional_edges(
        "base",
        route_after_base,
        {"reasoner": "reasoner", "finalize": "finalize"},
    )
    g.add_edge("reasoner", END)
    g.add_edge("finalize", END)

    return g.compile()
