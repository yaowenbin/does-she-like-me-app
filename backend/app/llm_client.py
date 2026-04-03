from __future__ import annotations

import os
from typing import List, Optional

from dotenv import load_dotenv
from openai import OpenAI

from .llm_types import CompletionResult, CompletionUsage

load_dotenv()


class StubLLMClient:
    """No API key mode: return a placeholder report for integration testing."""

    def __init__(self) -> None:
        self._model = os.getenv("OPENAI_MODEL", "deepseek-chat")
        self._reasoner_model = (
            os.getenv("DEEPSEEK_REASONER_MODEL") or os.getenv("OPENAI_REASONER_MODEL") or "deepseek-reasoner"
        ).strip()
        self._stub_body = (
            "（演习模式 / Stub）\n\n"
            "未检测到 `OPENAI_API_KEY`，因此无法真实调用 DeepSeek。\n\n"
            "你可以先验证后端-前端链路是否通畅；配置 Key 后即可生成真实多透镜报告。"
        )

    @property
    def model(self) -> str:
        return self._model

    def complete(
        self,
        messages: List[dict],
        *,
        temperature: float = 0.3,
        model: Optional[str] = None,
    ) -> CompletionResult:
        used = model or self._model
        body = self._stub_body
        if used == self._reasoner_model or "reasoner" in (used or "").lower():
            body += "\n\n（Stub：深度推理节点已执行占位）"
        return CompletionResult(
            content=body,
            model=used,
            usage=CompletionUsage(
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                prompt_cache_hit_tokens=0,
                prompt_cache_miss_tokens=0,
            ),
        )

    def chat(self, messages: List[dict], temperature: float = 0.3) -> str:
        return self.complete(messages, temperature=temperature).content


class DeepSeekClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
    ) -> None:
        self._model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=300.0, max_retries=1)

    @property
    def model(self) -> str:
        return self._model

    def complete(
        self,
        messages: List[dict],
        *,
        temperature: float = 0.3,
        model: Optional[str] = None,
    ) -> CompletionResult:
        m = model or self._model
        resp = self._client.chat.completions.create(
            model=m,
            messages=messages,
            temperature=temperature,
        )
        msg = resp.choices[0].message
        text = (msg.content or "").strip()
        if not text:
            # 部分兼容实现会把长思维链放在其它字段
            text = (getattr(msg, "reasoning_content", None) or "").strip()
        usage = CompletionUsage.from_openai_usage(getattr(resp, "usage", None))
        return CompletionResult(content=text, model=m, usage=usage)

    def chat(self, messages: List[dict], temperature: float = 0.3) -> str:
        return self.complete(messages, temperature=temperature).content


def default_reasoner_model() -> str:
    return (
        os.getenv("DEEPSEEK_REASONER_MODEL") or os.getenv("OPENAI_REASONER_MODEL") or "deepseek-reasoner"
    ).strip()


def create_llm_client() -> object:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    base_url = (os.getenv("OPENAI_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1").strip()
    model = (os.getenv("OPENAI_MODEL") or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat").strip()

    if not api_key:
        return StubLLMClient()

    return DeepSeekClient(api_key=api_key, base_url=base_url, model=model)

