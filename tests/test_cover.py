from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from newsletter_kindle.epub.cover import generate_cover
from newsletter_kindle.models import Newsletter, Section, Story


def _sample_newsletter(date: str = "2024-01-15") -> Newsletter:
    return Newsletter(
        source_name="tldr",
        title=f"TLDR — {date}",
        date=date,
        message_id=f"<cover-test-{date}>",
        received_at=datetime(2024, 1, 15, tzinfo=UTC),
        sections=[
            Section(
                title="BIG TECH",
                emoji="⚡",
                stories=[
                    Story(title="Some Headline", url="https://example.com", body="Body text.")
                ],
            )
        ],
    )


def test_cover_returns_jpeg_bytes() -> None:
    data = generate_cover(_sample_newsletter())
    assert isinstance(data, bytes)
    assert len(data) > 1000
    # JPEG magic bytes
    assert data[:3] == b"\xff\xd8\xff"


def test_cover_is_deterministic() -> None:
    nl = _sample_newsletter()
    data1 = generate_cover(nl)
    data2 = generate_cover(nl)
    assert hashlib.sha256(data1).hexdigest() == hashlib.sha256(data2).hexdigest()


def test_cover_differs_by_date() -> None:
    data_jan = generate_cover(_sample_newsletter("2024-01-15"))
    data_feb = generate_cover(_sample_newsletter("2024-02-15"))
    assert data_jan != data_feb


def test_cover_size_reasonable() -> None:
    data = generate_cover(_sample_newsletter())
    # Should be between 50KB and 1MB for a 1600x2400 JPEG
    assert 50_000 < len(data) < 1_000_000
