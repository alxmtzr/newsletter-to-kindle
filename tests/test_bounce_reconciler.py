from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from newsletter_kindle.delivery.kindle_sender import _BOUNCE_SUBJECT_RE, KindleEmailSender
from newsletter_kindle.state.db import StateDB


def test_bounce_subject_regex() -> None:
    assert _BOUNCE_SUBJECT_RE.search("Delivery failed: tldr_20240115.epub")
    assert _BOUNCE_SUBJECT_RE.search("Conversion failed")
    assert _BOUNCE_SUBJECT_RE.search("Document not delivered to Kindle")
    assert not _BOUNCE_SUBJECT_RE.search("Your Kindle delivery was successful")


def test_reconcile_confirms_stale_sends(tmp_path: Path) -> None:
    from datetime import timedelta

    db = StateDB(tmp_path / "state.db")
    db.upsert_newsletter(
        message_id="<stale1>",
        source="tldr",
        subject="TLDR 2024-01-15",
        received_at=datetime(2024, 1, 14, tzinfo=UTC),
        status="sent",
    )
    aid = db.record_send("<stale1>", 1)

    # Manually backdating sent_at to simulate a send 40 minutes ago
    db._conn.execute(
        "UPDATE send_attempts SET sent_at = ? WHERE id = ?",
        (
            (datetime.now(UTC) - timedelta(minutes=40)).isoformat(),
            aid,
        ),
    )
    db._conn.commit()

    sender = KindleEmailSender(user="u", password="p", kindle_email="k@kindle.com")
    # Skip IMAP reconcile (no real credentials) — only test the stale-send confirmation path
    sender._confirm_stale_sends(db)

    rows = db.recent()
    assert rows[0]["status"] == "confirmed_ok"
