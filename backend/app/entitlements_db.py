from __future__ import annotations

import secrets
import sqlite3
from pathlib import Path

from .db import utc_now_iso


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_entitlements_schema(db_path: Path) -> None:
    """在用户主库同路径扩展表（与 Database 共用 sqlite 文件时由 Database 调用）。"""
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                credits INTEGER NOT NULL DEFAULT 0,
                oa_follow_bonus_claimed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gift_codes (
                code TEXT PRIMARY KEY,
                credits INTEGER NOT NULL,
                used_by_device TEXT,
                used_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS wechat_scene_tokens (
                short_code TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_wechat_scene_device
            ON wechat_scene_tokens(device_id)
            """
        )


def device_row(conn: sqlite3.Connection, device_id: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT device_id, credits, oa_follow_bonus_claimed FROM devices WHERE device_id = ?",
        (device_id,),
    ).fetchone()


def ensure_device(conn: sqlite3.Connection, device_id: str, *, initial_credits: int = 0) -> sqlite3.Row:
    now = utc_now_iso()
    row = device_row(conn, device_id)
    if row:
        return row
    ic = max(0, int(initial_credits))
    conn.execute(
        """
        INSERT INTO devices (device_id, credits, oa_follow_bonus_claimed, created_at, updated_at)
        VALUES (?, ?, 0, ?, ?)
        """,
        (device_id, ic, now, now),
    )
    return conn.execute(
        "SELECT device_id, credits, oa_follow_bonus_claimed FROM devices WHERE device_id = ?",
        (device_id,),
    ).fetchone()


def set_device_credits(conn: sqlite3.Connection, device_id: str, credits: int) -> None:
    now = utc_now_iso()
    conn.execute(
        "UPDATE devices SET credits = ?, updated_at = ? WHERE device_id = ?",
        (credits, now, device_id),
    )


def grant_oa_follow_bonus(
    conn: sqlite3.Connection,
    device_id: str,
    bonus_credits: int = 1,
    *,
    initial_credits: int = 0,
) -> tuple[bool, str]:
    ensure_device(conn, device_id, initial_credits=initial_credits)
    row = device_row(conn, device_id)
    if row["oa_follow_bonus_claimed"]:
        return False, "already_claimed"
    c = int(row["credits"]) + int(bonus_credits)
    now = utc_now_iso()
    cur = conn.execute(
        """
        UPDATE devices SET credits = ?, oa_follow_bonus_claimed = 1, updated_at = ?
        WHERE device_id = ? AND oa_follow_bonus_claimed = 0
        """,
        (c, now, device_id),
    )
    if cur.rowcount != 1:
        return False, "race"
    return True, "ok"


def redeem_gift_code(
    conn: sqlite3.Connection,
    device_id: str,
    code: str,
    *,
    initial_credits: int = 0,
) -> tuple[bool, str, int]:
    code = (code or "").strip()
    if len(code) < 4:
        return False, "invalid_code", 0
    ensure_device(conn, device_id, initial_credits=initial_credits)
    row = conn.execute(
        "SELECT code, credits, used_by_device FROM gift_codes WHERE code = ?",
        (code,),
    ).fetchone()
    if not row:
        return False, "not_found", 0
    if row["used_by_device"]:
        return False, "already_used", 0
    add = int(row["credits"])
    now = utc_now_iso()
    cur = conn.execute(
        """
        UPDATE gift_codes SET used_by_device = ?, used_at = ? WHERE code = ? AND used_by_device IS NULL
        """,
        (device_id, now, code),
    )
    if cur.rowcount != 1:
        return False, "race", 0
    d = device_row(conn, device_id)
    new_c = int(d["credits"]) + add
    set_device_credits(conn, device_id, new_c)
    return True, "ok", add


def consume_credit_for_analyze(
    conn: sqlite3.Connection,
    device_id: str,
    *,
    initial_credits: int = 0,
) -> tuple[bool, str]:
    ensure_device(conn, device_id, initial_credits=initial_credits)
    row = device_row(conn, device_id)
    if int(row["credits"]) < 1:
        return False, "insufficient_credits"
    now = utc_now_iso()
    cur = conn.execute(
        """
        UPDATE devices SET credits = credits - 1, updated_at = ?
        WHERE device_id = ? AND credits >= 1
        """,
        (now, device_id),
    )
    if cur.rowcount != 1:
        return False, "insufficient_credits"
    return True, "ok"


def upsert_scene_token(conn: sqlite3.Connection, device_id: str, *, initial_credits: int = 0) -> str:
    """返回 short_code（用于公众号带参二维码 scene）。"""
    ensure_device(conn, device_id, initial_credits=initial_credits)
    existing = conn.execute(
        "SELECT short_code FROM wechat_scene_tokens WHERE device_id = ? ORDER BY created_at DESC LIMIT 1",
        (device_id,),
    ).fetchone()
    if existing:
        return str(existing["short_code"])
    short = secrets.token_hex(4)  # 8 chars
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO wechat_scene_tokens (short_code, device_id, created_at)
        VALUES (?, ?, ?)
        """,
        (short, device_id, now),
    )
    return short


def resolve_scene_to_device(conn: sqlite3.Connection, short_code: str) -> Optional[str]:
    row = conn.execute(
        "SELECT device_id FROM wechat_scene_tokens WHERE short_code = ?",
        (short_code,),
    ).fetchone()
    return str(row["device_id"]) if row else None


def insert_gift_code(conn: sqlite3.Connection, code: str, credits: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO gift_codes (code, credits, used_by_device, used_at) VALUES (?, ?, NULL, NULL)",
        (code.strip(), credits),
    )
