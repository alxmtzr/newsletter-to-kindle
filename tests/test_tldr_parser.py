from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from newsletter_kindle.models import RawMessage
from newsletter_kindle.parsers.tldr_parser import TldrParser

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "tldr"
FIXTURE_FILES = list(FIXTURE_DIR.glob("*.eml"))


@pytest.mark.parametrize("eml_path", FIXTURE_FILES, ids=[f.stem for f in FIXTURE_FILES])
def test_parse_fixture(eml_path: Path) -> None:
    raw = RawMessage(
        source_name="tldr",
        message_id=f"<test-{eml_path.stem}@fixture>",
        received_at=datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc),
        raw_bytes=eml_path.read_bytes(),
    )
    metadata = {
        "title_prefix": "TLDR",
        "author": "Dan Ni",
        "author_sort": "Ni, Dan",
        "publisher": "TLDR Newsletter",
        "subjects": ["Newsletter", "Technology"],
        "language": "en",
        "rights": "© TLDR Newsletter. Personal archival copy.",
    }
    parser = TldrParser()
    newsletter = parser.parse(raw, metadata)

    assert newsletter.source_name == "tldr"
    assert "TLDR" in newsletter.title
    assert newsletter.date != ""
    assert len(newsletter.sections) >= 1
    total_stories = sum(len(s.stories) for s in newsletter.sections)
    assert total_stories >= 1


def test_sponsor_filtered() -> None:
    eml_path = FIXTURE_DIR / "2024-01-15.eml"
    raw = RawMessage(
        source_name="tldr",
        message_id="<test-sponsor@fixture>",
        received_at=datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc),
        raw_bytes=eml_path.read_bytes(),
    )
    parser = TldrParser()
    newsletter = parser.parse(raw, {"title_prefix": "TLDR"})

    all_titles = [s.title for sec in newsletter.sections for s in sec.stories]
    assert not any("Sponsor" in t for t in all_titles)


def test_metadata_applied() -> None:
    eml_path = FIXTURE_DIR / "2024-01-15.eml"
    raw = RawMessage(
        source_name="tldr",
        message_id="<test-meta@fixture>",
        received_at=datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc),
        raw_bytes=eml_path.read_bytes(),
    )
    parser = TldrParser()
    newsletter = parser.parse(raw, {"title_prefix": "TLDR", "author": "Dan Ni", "publisher": "TLDR Newsletter"})

    assert newsletter.author == "Dan Ni"
    assert newsletter.publisher == "TLDR Newsletter"


def test_section_count() -> None:
    eml_path = FIXTURE_DIR / "2024-01-15.eml"
    raw = RawMessage(
        source_name="tldr",
        message_id="<test-sections@fixture>",
        received_at=datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc),
        raw_bytes=eml_path.read_bytes(),
    )
    parser = TldrParser()
    newsletter = parser.parse(raw, {})

    assert len(newsletter.sections) == 3
    assert any(s.emoji == "⚡" for s in newsletter.sections)
