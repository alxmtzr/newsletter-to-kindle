from __future__ import annotations

from datetime import UTC, datetime
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
        received_at=datetime(2024, 1, 15, 8, 0, tzinfo=UTC),
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
        received_at=datetime(2024, 1, 15, 8, 0, tzinfo=UTC),
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
        received_at=datetime(2024, 1, 15, 8, 0, tzinfo=UTC),
        raw_bytes=eml_path.read_bytes(),
    )
    parser = TldrParser()
    newsletter = parser.parse(
        raw, {"title_prefix": "TLDR", "author": "Dan Ni", "publisher": "TLDR Newsletter"}
    )

    assert newsletter.author == "Dan Ni"
    assert newsletter.publisher == "TLDR Newsletter"


def test_section_count() -> None:
    eml_path = FIXTURE_DIR / "2024-01-15.eml"
    raw = RawMessage(
        source_name="tldr",
        message_id="<test-sections@fixture>",
        received_at=datetime(2024, 1, 15, 8, 0, tzinfo=UTC),
        raw_bytes=eml_path.read_bytes(),
    )
    parser = TldrParser()
    newsletter = parser.parse(raw, {})

    assert len(newsletter.sections) == 3
    assert any(s.emoji == "⚡" for s in newsletter.sections)


# --- URL unwrapping ---


def test_unwrap_tracking_url_from_path() -> None:
    from newsletter_kindle.parsers.tldr_parser import _unwrap_url

    wrapped = (
        "https://tracking.tldrnewsletter.com/CL0/"
        "https:%2F%2Farstechnica.com%2Fgadgets%2F2026%2F06%2Fibm/1/abc123"
    )
    result = _unwrap_url(wrapped)
    assert result == "https://arstechnica.com/gadgets/2026/06/ibm"


def test_unwrap_non_tracking_url_unchanged() -> None:
    from newsletter_kindle.parsers.tldr_parser import _unwrap_url

    url = "https://arstechnica.com/article"
    assert _unwrap_url(url) == url


def test_unwrap_tracking_url_with_query_param() -> None:
    from newsletter_kindle.parsers.tldr_parser import _unwrap_url

    wrapped = "https://tracking.tldrnewsletter.com/CL0/test?url=https%3A%2F%2Fexample.com"
    result = _unwrap_url(wrapped)
    assert result == "https://example.com"


# --- Sponsor detection ---


def test_is_sponsor_detects_ad_domain() -> None:
    from bs4 import BeautifulSoup

    from newsletter_kindle.parsers.tldr_parser import _is_sponsor

    html = (
        '<div><a href="https://tracking.tldrnewsletter.com/CL0/'
        'https:%2F%2Fadvertise.tldr.tech%2F">Advertise with us</a></div>'
    )
    block = BeautifulSoup(html, "html.parser").find("div")
    assert _is_sponsor(block)  # type: ignore[arg-type]


def test_is_sponsor_passes_real_article() -> None:
    from bs4 import BeautifulSoup

    from newsletter_kindle.parsers.tldr_parser import _is_sponsor

    html = (
        '<div><a href="https://tracking.tldrnewsletter.com/CL0/'
        'https:%2F%2Farstechnica.com%2Farticle">IBM chips (5 minute read)</a></div>'
    )
    block = BeautifulSoup(html, "html.parser").find("div")
    assert not _is_sponsor(block)  # type: ignore[arg-type]


def test_is_sponsor_detects_sponsor_keyword_in_text() -> None:
    from bs4 import BeautifulSoup

    from newsletter_kindle.parsers.tldr_parser import _is_sponsor

    html = '<div><a href="https://example.com">Sponsor: Check out this product</a></div>'
    block = BeautifulSoup(html, "html.parser").find("div")
    assert _is_sponsor(block)  # type: ignore[arg-type]


# --- Notifier healthchecks exception handling ---


def test_ping_success_swallows_network_error() -> None:
    import urllib.error
    from unittest.mock import patch

    from newsletter_kindle.notify.notifier import Notifier

    n = Notifier(
        user="u",
        password="p",
        alert_recipient="a@b.com",
        healthchecks_url="https://hc-ping.com/test-uuid",
    )
    with patch(
        "newsletter_kindle.notify.notifier.urllib.request.urlopen",
        side_effect=urllib.error.URLError("network unreachable"),
    ):
        n.ping_success()  # must not raise


def test_ping_failure_swallows_network_error() -> None:
    import urllib.error
    from unittest.mock import patch

    from newsletter_kindle.notify.notifier import Notifier

    n = Notifier(
        user="u",
        password="p",
        alert_recipient="a@b.com",
        healthchecks_url="https://hc-ping.com/test-uuid",
    )
    with patch(
        "newsletter_kindle.notify.notifier.urllib.request.urlopen",
        side_effect=urllib.error.URLError("timeout"),
    ):
        n.ping_failure("some error")  # must not raise
