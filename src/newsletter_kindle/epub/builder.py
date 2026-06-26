from __future__ import annotations

import uuid
from pathlib import Path

import structlog
from ebooklib import epub

from newsletter_kindle.epub.cover import generate_cover
from newsletter_kindle.models import Document, Newsletter

log = structlog.get_logger()

_STYLE_PATH = Path(__file__).parent / "style.css"


def build_epub(newsletter: Newsletter, output_dir: Path) -> Document:
    output_dir.mkdir(parents=True, exist_ok=True)

    book = epub.EpubBook()

    # Deterministic identifier — stable across re-generation of the same issue
    identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, newsletter.message_id))
    book.set_identifier(f"urn:uuid:{identifier}")
    book.set_title(newsletter.title)
    book.set_language(newsletter.language)

    if newsletter.author:
        book.add_author(newsletter.author, file_as=newsletter.author_sort or newsletter.author)
    if newsletter.publisher:
        book.add_metadata("DC", "publisher", newsletter.publisher)
    if newsletter.date:
        book.add_metadata("DC", "date", newsletter.date)
    if newsletter.rights:
        book.add_metadata("DC", "rights", newsletter.rights)
    book.add_metadata("DC", "source", newsletter.source_name)

    first_stories = [
        s.title for sec in newsletter.sections for s in sec.stories
    ][:3]
    if first_stories:
        book.add_metadata("DC", "description", " | ".join(first_stories))

    for subject in newsletter.subjects:
        book.add_metadata("DC", "subject", subject)

    # Accessibility
    book.add_metadata(
        None,
        "meta",
        "textual",
        {"property": "schema:accessMode"},
    )

    # Cover image
    cover_bytes = generate_cover(newsletter)
    book.set_cover("cover.jpg", cover_bytes, create_page=True)

    # Stylesheet
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

        parts = [f'<div class="section-header">{title}</div>']
        for story in section.stories:
            read_time_html = (
                f' <span class="read-time">({story.read_time})</span>'
                if story.read_time
                else ""
            )
            parts.append(
                f'<div class="article">'
                f'<div class="article-title">'
                f'<a href="{story.url}">{story.title}</a>{read_time_html}'
                f"</div>"
                f'<div class="article-body">{story.body}</div>'
                f"</div>"
            )

        chapter = epub.EpubHtml(title=title, file_name=f"{slug}.xhtml", lang="en")
        chapter.content = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<html xmlns="http://www.w3.org/1999/xhtml">'
            f"<head><title>{title}</title>"
            '<link rel="stylesheet" type="text/css" href="style.css"/>'
            "</head><body>" + "".join(parts) + "</body></html>"
        ).encode("utf-8")
        chapter.add_item(style)
        book.add_item(chapter)
        chapters.append(chapter)
        toc.append(epub.Link(f"{slug}.xhtml", title, slug))

    book.toc = toc
    book.spine = ["nav"] + chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    safe_date = newsletter.date.replace("-", "")
    filename = f"{newsletter.source_name}_{safe_date}.epub"
    out_path = output_dir / filename
    epub.write_epub(str(out_path), book)

    log.info("epub.built", path=str(out_path), size=out_path.stat().st_size)
    return Document(
        message_id=newsletter.message_id,
        data=out_path.read_bytes(),
        mime_type="application/epub+zip",
        filename=filename,
    )
