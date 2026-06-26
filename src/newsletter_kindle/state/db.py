from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

_DDL = """
CREATE TABLE IF NOT EXISTS newsletters (
    message_id   TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    subject      TEXT,
    received_at  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'fetched',
    epub_path    TEXT,
    last_error   TEXT
);

CREATE TABLE IF NOT EXISTS send_attempts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id    TEXT NOT NULL REFERENCES newsletters(message_id),
    attempt_no    INTEGER NOT NULL,
    sent_at       TEXT NOT NULL,
    confirmed_at  TEXT,
    outcome       TEXT,
    bounce_reason TEXT
);

CREATE TABLE IF NOT EXISTS link_cache (
    wrapper_url  TEXT PRIMARY KEY,
    real_url     TEXT NOT NULL,
    resolved_at  TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class StateDB:
    def __init__(self, path: Path | str) -> None:
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_DDL)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- newsletters ---

    def upsert_newsletter(
        self,
        *,
        message_id: str,
        source: str,
        subject: str,
        received_at: datetime,
        status: str = "fetched",
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO newsletters (message_id, source, subject, received_at, status)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(message_id) DO NOTHING
            """,
            (message_id, source, subject, received_at.isoformat(), status),
        )
        self._conn.commit()

    def set_status(
        self,
        message_id: str,
        status: str,
        *,
        epub_path: str | None = None,
        last_error: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE newsletters
            SET status = ?, epub_path = COALESCE(?, epub_path), last_error = ?
            WHERE message_id = ?
            """,
            (status, epub_path, last_error, message_id),
        )
        self._conn.commit()

    def known_message_ids(self, source: str) -> set[str]:
        rows = self._conn.execute(
            "SELECT message_id FROM newsletters WHERE source = ?", (source,)
        ).fetchall()
        return {r["message_id"] for r in rows}

    def pending_retries(self) -> list[sqlite3.Row]:
        """Newsletters stuck in confirmed_failed with fewer than 3 attempts."""
        return self._conn.execute(
            """
            SELECT n.message_id, n.epub_path, n.source,
                   COUNT(sa.id) AS attempts
            FROM newsletters n
            LEFT JOIN send_attempts sa ON sa.message_id = n.message_id
            WHERE n.status = 'confirmed_failed'
            GROUP BY n.message_id
            HAVING attempts < 3
            """
        ).fetchall()

    def open_sends(self) -> list[sqlite3.Row]:
        """Sends dispatched but not yet confirmed (outcome IS NULL)."""
        return self._conn.execute(
            """
            SELECT sa.id, sa.message_id, sa.sent_at, sa.attempt_no
            FROM send_attempts sa
            JOIN newsletters n ON n.message_id = sa.message_id
            WHERE sa.outcome IS NULL
            """
        ).fetchall()

    def dead_letters(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM newsletters WHERE status = 'dead_letter'"
        ).fetchall()

    def recent(self, limit: int = 20) -> list[sqlite3.Row]:
        return self._conn.execute(
            """
            SELECT n.message_id, n.source, n.subject, n.received_at,
                   n.status, n.last_error,
                   COUNT(sa.id) AS attempts
            FROM newsletters n
            LEFT JOIN send_attempts sa ON sa.message_id = n.message_id
            GROUP BY n.message_id
            ORDER BY n.received_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    # --- send_attempts ---

    def record_send(self, message_id: str, attempt_no: int) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO send_attempts (message_id, attempt_no, sent_at)
            VALUES (?, ?, ?)
            """,
            (message_id, attempt_no, _now()),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def confirm_send(self, attempt_id: int, outcome: str, bounce_reason: str | None = None) -> None:
        self._conn.execute(
            """
            UPDATE send_attempts
            SET outcome = ?, confirmed_at = ?, bounce_reason = ?
            WHERE id = ?
            """,
            (outcome, _now(), bounce_reason, attempt_id),
        )
        self._conn.commit()

    def attempt_count(self, message_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM send_attempts WHERE message_id = ?", (message_id,)
        ).fetchone()
        return int(row[0])

    # --- link_cache ---

    def get_real_url(self, wrapper_url: str) -> str | None:
        row = self._conn.execute(
            "SELECT real_url FROM link_cache WHERE wrapper_url = ?", (wrapper_url,)
        ).fetchone()
        return row["real_url"] if row else None

    def cache_url(self, wrapper_url: str, real_url: str) -> None:
        self._conn.execute(
            """
            INSERT INTO link_cache (wrapper_url, real_url, resolved_at)
            VALUES (?, ?, ?)
            ON CONFLICT(wrapper_url) DO NOTHING
            """,
            (wrapper_url, real_url, _now()),
        )
        self._conn.commit()
