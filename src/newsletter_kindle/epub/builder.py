from __future__ import annotations

import html as _html
import io
import re
import uuid
import zipfile
from pathlib import Path

import structlog
from ebooklib import epub  # type: ignore[import-untyped]
from PIL import Image

from newsletter_kindle.epub.cover import generate_cover
from newsletter_kindle.models import Document, Newsletter

log = structlog.get_logger()

_STYLE_PATH = Path(__file__).parent / "style.css"
_COVER_MAX_BYTES = 120_000
_COVER_WIDTH = 1200
_COVER_HEIGHT = 1800


def _fix_epub(path: Path) -> None:
    """Post-process the EPUB ZIP to fix Amazon compatibility issues."""
    with zipfile.ZipFile(path, "r") as zin:
        entries = {info.filename: (info, zin.read(info.filename)) for info in zin.infolist()}

    fixed: dict[str, tuple[zipfile.ZipInfo, bytes]] = {}
    for filename, (info, data) in entries.items():
        if filename.endswith(".xhtml") or filename.endswith(".html"):
            text = data.decode("utf-8")
            # Remove DOCTYPE — causes E999 on Amazon's converter
            text = text.replace("<!DOCTYPE html>\n", "").replace("<!DOCTYPE html>", "")
            data = text.encode("utf-8")
        elif "cover.jpg" in filename:
            if len(data) > _COVER_MAX_BYTES:
                img = Image.open(io.BytesIO(data))
                resized = img.resize((_COVER_WIDTH, _COVER_HEIGHT), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                resized.save(buf, format="JPEG", quality=80, optimize=True)
                data = buf.getvalue()
                log.info("epub.cover_recompressed", size=len(data))
        fixed[filename] = (info, data)

    tmp = path.with_suffix(".tmp.epub")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        if "mimetype" in fixed:
            info, data = fixed.pop("mimetype")
            info.compress_type = zipfile.ZIP_STORED
            zout.writestr(info, data)
        for _filename, (info, data) in fixed.items():
            zout.writestr(info, data)

    tmp.replace(path)


def _strip_emoji(text: str) -> str:
    """Remove emoji from text — Amazon's converter chokes on emoji in XHTML titles."""
    # Matches emoji in both BMP (U+2600-U+27FF) and supplementary planes
    return re.sub(
        r"[☀-⟿⬀-⯿\U0001F000-\U0010FFFF]", "", text
    ).strip()


def _chapter_html(title: str, body: str) -> bytes:
    """Minimal valid XHTML — matches the POC that successfully converted on Amazon."""
    escaped_title = _html.escape(title)
    return (
        f'<html xmlns="http://www.w3.org/1999/xhtml">\n'
        f"<head>\n"
        f"  <title>{escaped_title}</title>\n"
        f'  <link rel="stylesheet" href="style.css"/>\n'
        f"</head>\n"
        f"<body>\n"
        f"{body}\n"
        f"</body>\n"
        f"</html>"
    ).encode()


def build_epub(newsletter: Newsletter, output_dir: Path) -> Document:
    output_dir.mkdir(parents=True, exist_ok=True)

    book = epub.EpubBook()

    # Use raw UUID without urn:uuid: prefix — matches working POC
    identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, newsletter.message_id))
    book.set_identifier(identifier)
    book.set_title(newsletter.title)
    book.set_language(newsletter.language)
    book.add_author(newsletter.author or "TLDR Newsletter")

    # Cover — with create_page=True to match the working POC
    cover_bytes = generate_cover(newsletter)
    book.set_cover("cover.jpg", cover_bytes, create_page=True)

    style = epub.EpubItem(
        uid="style",
        file_name="style.css",
        media_type="text/css",
        content=_STYLE_PATH.read_bytes(),
    )
    book.add_item(style)

    chapters: list[epub.EpubHtml] = []
    toc: list[epub.Link] = []

    for i, section in enumerate(newsletter.sections):
        if not section.stories:
            continue
        slug = f"section_{i}"
        title = f"{section.emoji} {section.title}".strip() if section.emoji else section.title
        title_safe = _strip_emoji(title)  # no emoji in XHTML title/NCX — Amazon chokes

        # Use emoji-stripped title in h1 too — Kindle fonts lack emoji glyphs
        parts = [f"<h1>{_html.escape(title_safe)}</h1>"]
        for story in section.stories:
            read_time_html = (
                f' <span class="read-time">({_html.escape(story.read_time)})</span>'
                if story.read_time
                else ""
            )
            parts.append(
                f'<div class="article">'
                f'<div class="article-title">'
                f'<a href="{story.url}">{_html.escape(story.title)}</a>{read_time_html}'
                f"</div>"
                f'<div class="article-body">{_html.escape(story.body)}</div>'
                f"</div>"
            )

        chapter = epub.EpubHtml(title=title_safe, file_name=f"{slug}.xhtml", lang="en")
        chapter.content = _chapter_html(title_safe, "\n".join(parts))
        chapter.add_item(style)
        book.add_item(chapter)
        chapters.append(chapter)
        toc.append(epub.Link(f"{slug}.xhtml", title_safe, slug))

    book.toc = toc
    book.spine = ["nav"] + chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    filename = f"TLDR_{newsletter.date}.epub"
    out_path = output_dir / filename
    epub.write_epub(str(out_path), book)

    _fix_epub(out_path)

    log.info("epub.built", path=str(out_path), size=out_path.stat().st_size)
    return Document(
        message_id=newsletter.message_id,
        data=out_path.read_bytes(),
        mime_type="application/epub+zip",
        filename=filename,
    )
