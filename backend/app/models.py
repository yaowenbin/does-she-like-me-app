from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel


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


class PasteImportRequest(BaseModel):
    # 直接粘贴的聊天文本（不依赖 wx txt 导出格式）
    text: str
    filename: str = ""


class AnalyzeResult(BaseModel):
    archive_id: str
    model: str
    report_markdown: str


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

