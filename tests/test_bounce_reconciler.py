from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from newsletter_kindle.delivery.kindle_sender import _BOUNCE_SUBJECT_RE, KindleEmailSender
from newsletter_kindle.state.db import StateDB


def test_bounce_subject_regex() -> None:
    # English patterns
    assert _BOUNCE_SUBJECT_RE.search("Delivery failed: tldr_20240115.epub")
    assert _BOUNCE_SUBJECT_RE.search("Conversion failed")
    assert _BOUNCE_SUBJECT_RE.search("Document not delivered to Kindle")
    # German patterns (actual Amazon DE format)
    assert _BOUNCE_SUBJECT_RE.search(
        "Es gab ein Problem mit dem/den Dokument/en, das/die Sie zu Kindle gesendet haben."
    )
    assert _BOUNCE_SUBJECT_RE.search("E999 - Send to Kindle - Interner Fehler")
    assert _BOUNCE_SUBJECT_RE.search("nicht zugestellt werden")
    # Should not match success
    assert not _BOUNCE_SUBJECT_RE.search("Your Kindle delivery was successful")


def test_match_bounce_by_filename(tmp_path: Path) -> None:
    db = StateDB(tmp_path / "state.db")
    db.upsert_newsletter(
        message_id="<msg1>",
        source="tldr",
        subject="TLDR 2026-06-26",
        received_at=datetime(2026, 6, 26, tzinfo=UTC),
        status="sent",
    )
    db.set_status("<msg1>", "sent", epub_path="/app/data/epubs/tldr/TLDR_2026-06-26.epub")
    aid = db.record_send("<msg1>", 1)

    sender = KindleEmailSender(user="u", password="p", kindle_email="k@kindle.com")

    # Simulate Amazon bounce email body containing the filename
    class FakeMsg:
        text = (
            "Folgende Dokumente konnten nicht zugestellt werden:\n\n"
            "* TLDR_2026-06-26.epub\n\n"
            "E999 - Send to Kindle - Interner Fehler"
        )
        subject = "Es gab ein Problem mit dem/den Dokument/en"

    matched = sender._match_bounce(db, FakeMsg())
    assert matched is not None
    assert matched == (aid, "<msg1>")


def test_match_bounce_no_match(tmp_path: Path) -> None:
    db = StateDB(tmp_path / "state.db")
    db.upsert_newsletter(
        message_id="<msg2>",
        source="tldr",
        subject="TLDR 2026-06-25",
        received_at=datetime(2026, 6, 25, tzinfo=UTC),
        status="sent",
    )
    db.set_status("<msg2>", "sent", epub_path="/app/data/epubs/tldr/TLDR_2026-06-25.epub")
    db.record_send("<msg2>", 1)

    sender = KindleEmailSender(user="u", password="p", kindle_email="k@kindle.com")

    # Bounce email mentions a different filename
    class FakeMsg:
        text = "* TLDR_2026-06-20.epub\n\nE999 error"
        subject = "Es gab ein Problem"

    matched = sender._match_bounce(db, FakeMsg())
    assert matched is None


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
