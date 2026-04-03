from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

from ..llm_types import CompletionResult


class SupportsLLMComplete(Protocol):
    def complete(
        self,
        messages: List[dict],
        *,
        temperature: float = 0.3,
        model: Optional[str] = None,
    ) -> CompletionResult: ...


def usage_to_step_dict(*, step: str, result: CompletionResult) -> Dict[str, Any]:
    u = result.usage
    return {
        "step": step,
        "model": result.model,
        "prompt_tokens": u.prompt_tokens,
        "completion_tokens": u.completion_tokens,
        "total_tokens": u.total_tokens,
        "prompt_cache_hit_tokens": u.prompt_cache_hit_tokens,
        "prompt_cache_miss_tokens": u.prompt_cache_miss_tokens,
    }
