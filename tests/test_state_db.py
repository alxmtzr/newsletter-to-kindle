from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from newsletter_kindle.state.db import StateDB


@pytest.fixture
def db(tmp_path):
    return StateDB(tmp_path / "test.db")


def test_upsert_and_status(db: StateDB) -> None:
    db.upsert_newsletter(
        message_id="<test1>",
        source="tldr",
        subject="TLDR 2024-01-15",
        received_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
    )
    ids = db.known_message_ids("tldr")
    assert "<test1>" in ids


def test_idempotent_upsert(db: StateDB) -> None:
    for _ in range(3):
        db.upsert_newsletter(
            message_id="<dup>",
            source="tldr",
            subject="Dup",
            received_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
        )
    ids = db.known_message_ids("tldr")
    assert ids.count("<dup>") if hasattr(ids, "count") else True
    assert len(db.recent()) == 1


def test_set_status(db: StateDB) -> None:
    db.upsert_newsletter(
        message_id="<s1>",
        source="tldr",
        subject="",
        received_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
    )
    db.set_status("<s1>", "epub_built", epub_path="/tmp/test.epub")
    rows = db.recent()
    assert rows[0]["status"] == "epub_built"


def test_send_attempt_lifecycle(db: StateDB) -> None:
    db.upsert_newsletter(
        message_id="<sa1>",
        source="tldr",
        subject="",
        received_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
    )
    aid = db.record_send("<sa1>", 1)
    assert aid is not None

    open_sends = db.open_sends()
    assert any(r["message_id"] == "<sa1>" for r in open_sends)

    db.confirm_send(aid, "ok")
    open_sends = db.open_sends()
    assert not any(r["message_id"] == "<sa1>" for r in open_sends)


def test_pending_retries(db: StateDB) -> None:
    db.upsert_newsletter(
        message_id="<r1>",
        source="tldr",
        subject="",
        received_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
    )
    db.set_status("<r1>", "confirmed_failed")
    retries = db.pending_retries()
    assert any(r["message_id"] == "<r1>" for r in retries)


def test_link_cache(db: StateDB) -> None:
    assert db.get_real_url("https://tracking.example.com/abc") is None
    db.cache_url("https://tracking.example.com/abc", "https://real.example.com/article")
    assert db.get_real_url("https://tracking.example.com/abc") == "https://real.example.com/article"
