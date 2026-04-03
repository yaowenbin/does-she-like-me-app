from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class CompletionUsage:
    """对齐 OpenAI / DeepSeek Chat Completions 的 usage；缓存字段见官方 Context Caching 文档。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_cache_hit_tokens: Optional[int] = None
    prompt_cache_miss_tokens: Optional[int] = None

    @staticmethod
    def from_openai_usage(u: Any) -> "CompletionUsage":
        if u is None:
            return CompletionUsage()
        return CompletionUsage(
            prompt_tokens=int(getattr(u, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(u, "completion_tokens", 0) or 0),
            total_tokens=int(getattr(u, "total_tokens", 0) or 0),
            prompt_cache_hit_tokens=_maybe_int(getattr(u, "prompt_cache_hit_tokens", None)),
            prompt_cache_miss_tokens=_maybe_int(getattr(u, "prompt_cache_miss_tokens", None)),
        )


def _maybe_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class CompletionResult:
    content: str
    model: str
    usage: CompletionUsage
