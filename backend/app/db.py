from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ArchiveRow:
    id: str
    name: str
    stage: str
    scenario: str
    tags_json: str
    created_at: str
    updated_at: str

    @property
    def tags(self) -> Dict[str, Any]:
        try:
            return json.loads(self.tags_json) if self.tags_json else {}
        except json.JSONDecodeError:
            return {}


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS archives (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    scenario TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS uploads (
                    archive_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    content_path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    archive_id TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    report_markdown TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_usage_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    archive_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    step TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_tokens INTEGER,
                    completion_tokens INTEGER,
                    total_tokens INTEGER,
                    prompt_cache_hit_tokens INTEGER,
                    prompt_cache_miss_tokens INTEGER,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_llm_usage_archive ON llm_usage_log(archive_id)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_run ON llm_usage_log(run_id)")
            from .entitlements_db import init_entitlements_schema

            init_entitlements_schema(self.db_path)

    def create_archive(
        self,
        archive_id: str,
        *,
        name: str,
        stage: str,
        scenario: str,
        tags: Dict[str, Any],
    ) -> None:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO archives (id, name, stage, scenario, tags_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    archive_id,
                    name or "",
                    stage or "",
                    scenario or "",
                    json.dumps(tags or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )

    def update_archive_updated_at(self, archive_id: str) -> None:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE archives SET updated_at = ? WHERE id = ?",
                (now, archive_id),
            )

    def get_archive(self, archive_id: str) -> Optional[ArchiveRow]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, name, stage, scenario, tags_json, created_at, updated_at
                FROM archives
                WHERE id = ?
                """,
                (archive_id,),
            ).fetchone()
            if not row:
                return None
            return ArchiveRow(
                id=row["id"],
                name=row["name"],
                stage=row["stage"],
                scenario=row["scenario"],
                tags_json=row["tags_json"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_archives(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT a.id, a.name, a.stage, a.scenario, a.tags_json, a.created_at, a.updated_at,
                       CASE WHEN u.archive_id IS NOT NULL THEN 1 ELSE 0 END AS has_upload,
                       CASE WHEN r.archive_id IS NOT NULL THEN 1 ELSE 0 END AS has_report
                FROM archives a
                LEFT JOIN uploads u ON u.archive_id = a.id
                LEFT JOIN reports r ON r.archive_id = a.id
                ORDER BY a.updated_at DESC
                """
            ).fetchall()
            out: List[Dict[str, Any]] = []
            for row in rows:
                tags = {}
                try:
                    tags = json.loads(row["tags_json"]) if row["tags_json"] else {}
                except json.JSONDecodeError:
                    tags = {}
                out.append(
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "stage": row["stage"],
                        "scenario": row["scenario"],
                        "tags": tags,
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                        "has_upload": bool(row["has_upload"]),
                        "has_report": bool(row["has_report"]),
                    }
                )
            return out

    def save_upload(self, archive_id: str, *, filename: str, content_path: Path) -> None:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO uploads (archive_id, filename, content_path, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(archive_id) DO UPDATE SET
                    filename = excluded.filename,
                    content_path = excluded.content_path,
                    created_at = excluded.created_at
                """,
                (archive_id, filename, str(content_path), now),
            )
            conn.execute(
                "UPDATE archives SET updated_at = ? WHERE id = ?",
                (now, archive_id),
            )

    def get_upload_path(self, archive_id: str) -> Optional[Path]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT content_path FROM uploads WHERE archive_id = ?
                """,
                (archive_id,),
            ).fetchone()
            if not row:
                return None
            return Path(row["content_path"])

    def save_report(self, archive_id: str, *, model: str, report_markdown: str) -> None:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reports (archive_id, model, report_markdown, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(archive_id) DO UPDATE SET
                    model = excluded.model,
                    report_markdown = excluded.report_markdown,
                    created_at = excluded.created_at
                """,
                (archive_id, model, report_markdown, now),
            )
            conn.execute(
                "UPDATE archives SET updated_at = ? WHERE id = ?",
                (now, archive_id),
            )

    def get_report(self, archive_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT model, report_markdown, created_at FROM reports WHERE archive_id = ?
                """,
                (archive_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "model": row["model"],
                "report_markdown": row["report_markdown"],
                "created_at": row["created_at"],
            }

    def log_llm_usage(
        self,
        *,
        archive_id: str,
        run_id: str,
        step: str,
        model: str,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        prompt_cache_hit_tokens: Optional[int] = None,
        prompt_cache_miss_tokens: Optional[int] = None,
    ) -> None:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_usage_log (
                    archive_id, run_id, step, model,
                    prompt_tokens, completion_tokens, total_tokens,
                    prompt_cache_hit_tokens, prompt_cache_miss_tokens, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    archive_id,
                    run_id,
                    step,
                    model,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    prompt_cache_hit_tokens,
                    prompt_cache_miss_tokens,
                    now,
                ),
            )

