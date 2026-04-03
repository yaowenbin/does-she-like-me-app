from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from typing import Optional, Tuple

# 微信公众平台：服务器验证与关注事件（带参二维码 scene）解析。
# 配置：WECHAT_MP_TOKEN（接口配置里的 Token），可选 AES（本 MVP 仅用明文模式）。


def verify_signature(*, token: str, timestamp: str, nonce: str, signature: str) -> bool:
    if not token or not signature:
        return False
    arr = sorted([token, timestamp or "", nonce or ""])
    s = "".join(arr).encode("utf-8")
    digest = hashlib.sha1(s).hexdigest()
    return digest == signature


def parse_subscribe_event(xml_bytes: bytes) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    返回 (msg_type, event, event_key)。
    关注带参二维码时 event_key 形如 qrscene_xxxx ，xxxx 即 wechat_scene_tokens.short_code
    """
    try:
        root = ET.fromstring(xml_bytes.decode("utf-8", errors="replace"))
    except ET.ParseError:
        return None, None, None

    def text(tag: str) -> Optional[str]:
        el = root.find(tag)
        if el is None or el.text is None:
            return None
        return el.text.strip()

    return text("MsgType"), text("Event"), text("EventKey")


def strip_qrscene(event_key: str | None) -> Optional[str]:
    if not event_key:
        return None
    if event_key.startswith("qrscene_"):
        return event_key[len("qrscene_") :].strip() or None
    return event_key.strip() or None
