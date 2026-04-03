from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

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
        _migrate_gift_codes(conn)
        conn.commit()


def _migrate_gift_codes(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(gift_codes)").fetchall()}
    if "created_at" not in cols:
        conn.execute("ALTER TABLE gift_codes ADD COLUMN created_at TEXT")
    if "expires_at" not in cols:
        conn.execute("ALTER TABLE gift_codes ADD COLUMN expires_at TEXT")
    if "revoked_at" not in cols:
        conn.execute("ALTER TABLE gift_codes ADD COLUMN revoked_at TEXT")
    # 历史行：补 created_at；过期时间留空表示「不自动过期」（仅新入库卡密写 expires_at）
    now = utc_now_iso()
    conn.execute(
        "UPDATE gift_codes SET created_at = ? WHERE created_at IS NULL OR TRIM(created_at) = ''",
        (now,),
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
        """
        SELECT code, credits, used_by_device, revoked_at, expires_at
        FROM gift_codes WHERE code = ?
        """,
        (code,),
    ).fetchone()
    if not row:
        return False, "not_found", 0
    if row["revoked_at"]:
        return False, "revoked", 0
    exp = row["expires_at"]
    if exp and str(exp).strip() and str(exp) < utc_now_iso():
        return False, "expired", 0
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


def consume_credits(
    conn: sqlite3.Connection,
    device_id: str,
    amount: int,
    *,
    initial_credits: int = 0,
) -> tuple[bool, str]:
    """原子扣减多次分析额度（amount>=1）。amount<=0 视为成功且不操作。"""
    ensure_device(conn, device_id, initial_credits=initial_credits)
    if amount <= 0:
        return True, "ok"
    row = device_row(conn, device_id)
    if int(row["credits"]) < amount:
        return False, "insufficient_credits"
    now = utc_now_iso()
    cur = conn.execute(
        """
        UPDATE devices SET credits = credits - ?, updated_at = ?
        WHERE device_id = ? AND credits >= ?
        """,
        (amount, now, device_id, amount),
    )
    if cur.rowcount != 1:
        return False, "insufficient_credits"
    return True, "ok"


def refund_credits(conn: sqlite3.Connection, device_id: str, amount: int) -> None:
    """失败回滚用：将额度加回设备。"""
    if amount <= 0:
        return
    ensure_device(conn, device_id, initial_credits=0)
    row = device_row(conn, device_id)
    new_c = int(row["credits"]) + int(amount)
    set_device_credits(conn, device_id, new_c)


def consume_credit_for_analyze(
    conn: sqlite3.Connection,
    device_id: str,
    *,
    initial_credits: int = 0,
) -> tuple[bool, str]:
    return consume_credits(conn, device_id, 1, initial_credits=initial_credits)


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


def expires_at_after_days(days: int) -> str:
    d = max(1, min(3650, int(days)))
    return (datetime.now(timezone.utc) + timedelta(days=d)).isoformat()


def try_insert_gift_code(
    conn: sqlite3.Connection,
    code: str,
    credits: int,
    *,
    expires_at: Optional[str],
) -> bool:
    """新卡密入库。code 重复返回 False（不覆盖已存在记录）。"""
    code = (code or "").strip()
    if len(code) < 4 or int(credits) < 1:
        return False
    now = utc_now_iso()
    try:
        conn.execute(
            """
            INSERT INTO gift_codes (
                code, credits, used_by_device, used_at,
                created_at, expires_at, revoked_at
            ) VALUES (?, ?, NULL, NULL, ?, ?, NULL)
            """,
            (code, int(credits), now, expires_at),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def random_gift_code(prefix: str = "") -> str:
    """高熵随机卡密，可选业务前缀（如 DSL-）。"""
    core = secrets.token_hex(8).upper()
    p = (prefix or "").strip().upper()
    if not p:
        return core
    if p.endswith("-"):
        return f"{p}{core}"
    return f"{p}-{core}"


def generate_gift_codes_batch(
    conn: sqlite3.Connection,
    count: int,
    credits: int,
    expires_in_days: int,
    prefix: str,
) -> tuple[int, list[str]]:
    exp = expires_at_after_days(expires_in_days)
    created: list[str] = []
    n = max(1, min(5000, int(count)))
    for _ in range(n):
        for _attempt in range(32):
            code = random_gift_code(prefix)
            if try_insert_gift_code(conn, code, int(credits), expires_at=exp):
                created.append(code)
                break
        else:
            raise RuntimeError("gift code generation collision too many times")
    return len(created), created


def revoke_gift_codes(conn: sqlite3.Connection, codes: list[str]) -> int:
    """仅废除「未兑换」卡密（已使用的不改，避免账务混乱）。"""
    now = utc_now_iso()
    total = 0
    for raw in codes:
        c = (raw or "").strip()
        if len(c) < 4:
            continue
        cur = conn.execute(
            """
            UPDATE gift_codes SET revoked_at = ?
            WHERE code = ? AND used_by_device IS NULL AND revoked_at IS NULL
            """,
            (now, c),
        )
        total += cur.rowcount
    return total


def list_all_gift_codes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT code, credits, used_by_device, used_at, created_at, expires_at, revoked_at
        FROM gift_codes
        ORDER BY created_at DESC, code DESC
        """
    ).fetchall()


def gift_code_effective_status(row: sqlite3.Row, *, now_iso: str) -> str:
    if row["revoked_at"]:
        return "revoked"
    if row["used_by_device"]:
        return "used"
    exp = row["expires_at"]
    if exp and str(exp).strip() and str(exp) < now_iso:
        return "expired"
    return "unused"
