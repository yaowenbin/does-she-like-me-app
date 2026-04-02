from __future__ import annotations

import os
from typing import List

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class StubLLMClient:
    """No API key mode: return a placeholder report for integration testing."""

    def __init__(self) -> None:
        self._model = os.getenv("OPENAI_MODEL", "deepseek-chat")

    def chat(self, messages: List[dict], temperature: float = 0.3) -> str:
        return (
            "（演习模式 / Stub）\n\n"
            "未检测到 `OPENAI_API_KEY`，因此无法真实调用 DeepSeek。\n\n"
            "你可以先验证后端-前端链路是否通畅；配置 Key 后即可生成真实多透镜报告。"
        )

    @property
    def model(self) -> str:
        return self._model


class DeepSeekClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
    ) -> None:
        self._model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    @property
    def model(self) -> str:
        return self._model

    def chat(self, messages: List[dict], temperature: float = 0.3) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""


def create_llm_client() -> object:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    base_url = (os.getenv("OPENAI_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1").strip()
    model = (os.getenv("OPENAI_MODEL") or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat").strip()

    if not api_key:
        return StubLLMClient()

    return DeepSeekClient(api_key=api_key, base_url=base_url, model=model)

