from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from pathlib import Path

from newsletter_kindle.epub.builder import build_epub
from newsletter_kindle.models import Newsletter, RawMessage, Section, Story
from newsletter_kindle.parsers.tldr_parser import TldrParser


def _sample_newsletter(date: str = "2024-01-15") -> Newsletter:
    return Newsletter(
        source_name="tldr",
        title=f"TLDR — {date}",
        date=date,
        message_id=f"<test-epub-{date}@fixture>",
        received_at=datetime(2024, 1, 15, tzinfo=UTC),
        sections=[
            Section(
                title="BIG TECH & STARTUPS",
                emoji="⚡",
                stories=[
                    Story(
                        title="Apple Announces New Tools",
                        url="https://example.com/apple",
                        body="Apple released new developer tools.",
                        read_time="3 minute read",
                    ),
                ],
            ),
            Section(
                title="PROGRAMMING",
                emoji="💻",
                stories=[
                    Story(
                        title="Rust 2024 Edition",
                        url="https://example.com/rust",
                        body="The Rust 2024 edition has improved async support.",
                    ),
                ],
            ),
        ],
        author="Dan Ni",
        author_sort="Ni, Dan",
        publisher="TLDR Newsletter",
        subjects=["Newsletter", "Technology"],
        language="en",
        rights="© TLDR Newsletter. Personal archival copy.",
    )


def test_epub_file_created(tmp_path: Path) -> None:
    newsletter = _sample_newsletter()
    doc = build_epub(newsletter, tmp_path)
    assert (tmp_path / doc.filename).exists()
    assert doc.mime_type == "application/epub+zip"


def test_epub_is_valid_zip(tmp_path: Path) -> None:
    doc = build_epub(_sample_newsletter(), tmp_path)
    assert zipfile.is_zipfile(tmp_path / doc.filename)


def test_epub_has_container_xml(tmp_path: Path) -> None:
    doc = build_epub(_sample_newsletter(), tmp_path)
    with zipfile.ZipFile(tmp_path / doc.filename) as z:
        assert "META-INF/container.xml" in z.namelist()
        assert "mimetype" in z.namelist()


def test_epub_metadata_complete(tmp_path: Path) -> None:
    newsletter = _sample_newsletter()
    doc = build_epub(newsletter, tmp_path)

    with zipfile.ZipFile(tmp_path / doc.filename) as z:
        # Find content.opf
        opf_names = [n for n in z.namelist() if n.endswith(".opf")]
        assert opf_names, "No .opf file found"
        opf_xml = z.read(opf_names[0]).decode("utf-8")

    assert "Dan Ni" in opf_xml
    assert "TLDR Newsletter" in opf_xml
    assert "2024-01-15" in opf_xml
    assert "TLDR" in opf_xml
    assert "Personal archival copy" in opf_xml


def test_epub_has_cover_image(tmp_path: Path) -> None:
    doc = build_epub(_sample_newsletter(), tmp_path)
    with zipfile.ZipFile(tmp_path / doc.filename) as z:
        names = z.namelist()
        # ebooklib stores cover under EPUB/ prefix
        assert any("cover.jpg" in n for n in names)


def test_epub_cover_image_property(tmp_path: Path) -> None:
    doc = build_epub(_sample_newsletter(), tmp_path)
    with zipfile.ZipFile(tmp_path / doc.filename) as z:
        opf_names = [n for n in z.namelist() if n.endswith(".opf")]
        opf_xml = z.read(opf_names[0]).decode("utf-8")
    assert "cover-image" in opf_xml


def test_epub_identifier_stable_across_runs(tmp_path: Path) -> None:
    newsletter = _sample_newsletter()
    doc1 = build_epub(newsletter, tmp_path / "run1")
    doc2 = build_epub(newsletter, tmp_path / "run2")

    def get_identifier(path: Path) -> str:
        with zipfile.ZipFile(path) as z:
            opf_names = [n for n in z.namelist() if n.endswith(".opf")]
            return z.read(opf_names[0]).decode("utf-8")

    opf1 = get_identifier(tmp_path / "run1" / doc1.filename)
    opf2 = get_identifier(tmp_path / "run2" / doc2.filename)
    # Same message_id → same UUID
    assert "urn:uuid:" in opf1
    uid_line1 = [line for line in opf1.splitlines() if "urn:uuid:" in line][0]
    uid_line2 = [line for line in opf2.splitlines() if "urn:uuid:" in line][0]
    assert uid_line1 == uid_line2


def test_epub_built_from_fixture(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "tldr" / "2024-01-15.eml"
    raw = RawMessage(
        source_name="tldr",
        message_id="<test-full@fixture>",
        received_at=datetime(2024, 1, 15, tzinfo=UTC),
        raw_bytes=fixture.read_bytes(),
    )
    newsletter = TldrParser().parse(raw, {"title_prefix": "TLDR", "author": "Dan Ni"})
    doc = build_epub(newsletter, tmp_path)
    assert (tmp_path / doc.filename).exists()
    assert doc.data[:4] == b"PK\x03\x04"  # ZIP magic bytes
