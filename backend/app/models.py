from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CreateArchiveRequest(BaseModel):
    name: str = ""
    stage: str = ""
    scenario: str = ""
    # 自愿标签：例如 zodiac / mbti / attachment 之类
    tags: Dict[str, Any] = {}


class ArchiveItem(BaseModel):
    id: str
    name: str
    stage: str
    scenario: str
    tags: Dict[str, Any]
    created_at: str
    updated_at: str
    has_upload: bool
    has_report: bool


class AnalyzeRequest(BaseModel):
    temperature: float = 0.7
    # 开启后走 deepseek-reasoner 审稿整稿；额度充足时由服务端额外扣次（见 DEEP_REASON_EXTRA_CREDITS）
    deep_reasoning: bool = False


class PasteImportRequest(BaseModel):
    # 直接粘贴的聊天文本（不依赖 wx txt 导出格式）
    text: str
    filename: str = ""


class UsageStepModel(BaseModel):
    """单次 LLM 调用的用量（含 DeepSeek 磁盘缓存命中字段，便于 POC 与对账）。"""

    step: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_cache_hit_tokens: Optional[int] = None
    prompt_cache_miss_tokens: Optional[int] = None


class AnalyzeResult(BaseModel):
    archive_id: str
    model: str
    report_markdown: str
    pipeline_version: str = "graph-v1"
    deep_reasoning_requested: bool = False
    deep_reasoning_used: bool = False
    reasoner_failed: bool = False
    reasoner_error: Optional[str] = None
    usage_steps: List[UsageStepModel] = Field(default_factory=list)


class AnalyzeFeaturesResponse(BaseModel):
    """前端展示开关说明与扣次规则。"""

    pipeline_version: str
    deep_reason_extra_credits: int
    reasoner_model: str
    entitlements_enforced: bool


class RedeemRequest(BaseModel):
    code: str = ""


class EntitlementsMeResponse(BaseModel):
    device_id: str
    credits: int
    oa_follow_bonus_claimed: bool
    entitlements_enforced: bool


class WechatSceneResponse(BaseModel):
    short_code: str
    hint: str

