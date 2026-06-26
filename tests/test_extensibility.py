from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from newsletter_kindle.delivery.base import Sender
from newsletter_kindle.models import Document, Newsletter, RawMessage, Section, SendReceipt, Story
from newsletter_kindle.parsers.base import Parser
from newsletter_kindle.sources.base import Source
from newsletter_kindle.state.db import StateDB


class _FakeSource(Source):
    def __init__(self, messages: list[RawMessage]) -> None:
        self._messages = messages

    def fetch_new(self, known_ids: set[str]) -> Iterator[RawMessage]:
        for m in self._messages:
            if m.message_id not in known_ids:
                yield m


class _FakeParser(Parser):
    def parse(self, raw: RawMessage, metadata: dict) -> Newsletter:
        return Newsletter(
            source_name=raw.source_name,
            title="Fake Newsletter — 2024-01-15",
            date="2024-01-15",
            message_id=raw.message_id,
            received_at=raw.received_at,
            sections=[
                Section(
                    title="Tech",
                    emoji="⚡",
                    stories=[Story(title="Story 1", url="https://example.com", body="Body")],
                )
            ],
        )


class _FakeSender(Sender):
    sent: list[Document] = []

    def send(self, document: Document, attempt_no: int) -> SendReceipt:
        self.sent.append(document)
        return SendReceipt(
            message_id=document.message_id,
            sent_at=datetime.now(UTC),
            attempt_no=attempt_no,
        )

    def reconcile(self, db: StateDB) -> None:
        pass


def test_fake_source_skips_known() -> None:
    raw = RawMessage(
        source_name="test",
        message_id="<known>",
        received_at=datetime.now(UTC),
        raw_bytes=b"",
    )
    source = _FakeSource([raw])
    results = list(source.fetch_new({"<known>"}))
    assert results == []


def test_fake_parser_produces_newsletter() -> None:
    raw = RawMessage(
        source_name="test",
        message_id="<p1>",
        received_at=datetime.now(UTC),
        raw_bytes=b"",
    )
    parser = _FakeParser()
    nl = parser.parse(raw, {})
    assert nl.title == "Fake Newsletter — 2024-01-15"
    assert len(nl.sections) == 1


def test_fake_sender_captures_send(tmp_path: Path) -> None:
    sender = _FakeSender()
    doc = Document(
        message_id="<d1>",
        data=b"fake-epub-bytes",
        mime_type="application/epub+zip",
        filename="test.epub",
    )
    receipt = sender.send(doc, 1)
    assert receipt.message_id == "<d1>"
    assert sender.sent[0].filename == "test.epub"


def test_sender_reconcile_is_noop(tmp_path: Path) -> None:
    db = StateDB(tmp_path / "test.db")
    sender = _FakeSender()
    sender.reconcile(db)  # should not raise
