from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException


def require_admin_bearer(authorization: str | None = Header(None)) -> None:
    """卡密管理等运营接口：Bearer Token 与 .env 中 ADMIN_API_TOKEN 一致。"""
    token = os.getenv("ADMIN_API_TOKEN", "").strip()
    if not token:
        raise HTTPException(
            status_code=503,
            detail="管理接口已禁用：请在服务端配置 ADMIN_API_TOKEN",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="未授权")
    got = authorization[7:].strip()
    if not secrets.compare_digest(got, token):
        raise HTTPException(status_code=401, detail="未授权")
