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


class TraceStepModel(BaseModel):
    step: str
    status: str
    model: Optional[str] = None
    error: Optional[str] = None


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
    execution_trace: List[TraceStepModel] = Field(default_factory=list)
    input_signal: Dict[str, Any] = Field(default_factory=dict)
    scoring_result: Dict[str, Any] = Field(default_factory=dict)
    friendly_summary: Dict[str, Any] = Field(default_factory=dict)


class AnalyzeFeaturesResponse(BaseModel):
    """前端展示开关说明与扣次规则。"""

    pipeline_version: str
    deep_reason_extra_credits: int
    reasoner_model: str
    entitlements_enforced: bool


class AnalyzePlanResponse(BaseModel):
    archive_id: str
    can_analyze: bool
    blockers: List[str] = Field(default_factory=list)
    required_credits: int = 1
    deep_reason_extra_credits: int = 1
    deep_reasoning_enabled: bool = False
    has_upload: bool = False
    has_report: bool = False
    pipeline_steps: List[str] = Field(default_factory=list)


class ReportFeedbackRequest(BaseModel):
    verdict: str
    note: str = ""


class ReportFeedbackResponse(BaseModel):
    ok: bool
    verdict: str
    message: str
    tuned_weights: Dict[str, float] = Field(default_factory=dict)


class ReportFeedbackItem(BaseModel):
    archive_id: str
    verdict: str
    note: str = ""
    created_at: str


class ReportFeedbackTimelineResponse(BaseModel):
    archive_id: str
    items: List[ReportFeedbackItem] = Field(default_factory=list)
    accurate_count: int = 0
    inaccurate_count: int = 0


class DeviceTuningSnapshotResponse(BaseModel):
    tuned_weights: Dict[str, float] = Field(default_factory=dict)
    updated_skills: int = 0


class DeviceTuningResetResponse(BaseModel):
    ok: bool
    cleared: int


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


class AdminGiftCodeRow(BaseModel):
    code: str
    credits: int
    # unused | used | expired | revoked
    status: str
    created_at: Optional[str] = None
    expires_at: Optional[str] = None
    revoked_at: Optional[str] = None
    used_by_device: Optional[str] = None
    used_at: Optional[str] = None


class AdminGiftCodeCreateItem(BaseModel):
    code: str
    credits: int = 1


class AdminGiftCodeGenerate(BaseModel):
    count: int = Field(ge=1, le=5000)
    credits: int = Field(ge=1, default=1)
    expires_in_days: int = Field(default=7, ge=1, le=365)
    prefix: str = Field(default="", max_length=16)


class AdminGiftCodeBatchCreate(BaseModel):
    """手工导入与随机批量可同时进行。手工条目使用 manual_expires_in_days 计算过期时间。"""

    items: Optional[List[AdminGiftCodeCreateItem]] = None
    generate: Optional[AdminGiftCodeGenerate] = None
    manual_expires_in_days: int = Field(default=7, ge=1, le=365)


class AdminGiftCodeBatchCreateResult(BaseModel):
    created: int
    skipped_invalid: int
    # 随机生成时返回明文（每行一条卡密，便于首次分发后从列表回收）
    generated_plaintext: Optional[str] = None


class AdminGiftCodeRevokeBody(BaseModel):
    codes: List[str]


class AdminGiftCodeRevokeResult(BaseModel):
    revoked: int
