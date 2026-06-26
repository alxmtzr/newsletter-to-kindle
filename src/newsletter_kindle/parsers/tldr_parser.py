from __future__ import annotations

import email
import re
import urllib.parse
from datetime import datetime, timezone

import structlog
from bs4 import BeautifulSoup, Tag

from newsletter_kindle.models import Newsletter, RawMessage, Section, Story
from newsletter_kindle.parsers.base import Parser

log = structlog.get_logger()

_SPONSOR_KEYWORDS = {"sponsor", "advertise", "utm_source", "utm_campaign", "utm_medium"}
_TRACKING_DOMAINS = {"tracking.tldrnewsletter.com", "tracking.tldr.tech"}


def _unwrap_url(url: str) -> str:
    """Decode TLDR tracking redirect to the real destination URL."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc not in _TRACKING_DOMAINS:
            return url
        # Try to extract the real URL from the path or query string
        qs = urllib.parse.parse_qs(parsed.query)
        if "url" in qs:
            return qs["url"][0]
        # Some TLDR tracking URLs encode the destination in the path as base64
        # Fall back to an HTTP HEAD request if we can't decode statically
        return _follow_redirect(url)
    except Exception:
        return url


def _follow_redirect(url: str) -> str:
    import urllib.request
    try:
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "Mozilla/5.0")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.url
    except Exception:
        return url


def _is_sponsor(element: Tag) -> bool:
    text = element.get_text(" ", strip=True).lower()
    hrefs = " ".join(a.get("href", "") for a in element.find_all("a", href=True)).lower()
    combined = text + hrefs
    return any(kw in combined for kw in _SPONSOR_KEYWORDS)


def _extract_date(soup: BeautifulSoup) -> str:
    span = soup.find("span", id="date")
    if span:
        return span.get_text(strip=True)
    # fallback: look for a date-like string in common patterns
    for tag in soup.find_all(string=re.compile(r"\d{4}-\d{2}-\d{2}")):
        m = re.search(r"\d{4}-\d{2}-\d{2}", tag)
        if m:
            return m.group(0)
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _extract_sections(soup: BeautifulSoup) -> list[Section]:
    sections: list[Section] = []
    current_section: Section | None = None

    for block in soup.find_all("div", class_="text-block"):
        if not isinstance(block, Tag):
            continue

        emoji_span = block.find("span", style=lambda s: s and "font-size: 36px" in s)
        h1 = block.find("h1")

        if emoji_span and not h1:
            if current_section and current_section.stories:
                sections.append(current_section)
            current_section = Section(
                emoji=emoji_span.get_text(strip=True), title="", stories=[]
            )
            continue

        if h1 and current_section and not current_section.title:
            current_section.title = h1.get_text(strip=True)
            continue

        anchor = block.find("a")
        if anchor and current_section:
            if _is_sponsor(block):
                continue

            title_text: str = anchor.get_text(strip=True)
            raw_url: str = anchor.get("href", "")  # type: ignore[assignment]
            real_url = _unwrap_url(raw_url)

            read_time = ""
            if "minute read" in title_text:
                parts = title_text.rsplit("(", 1)
                if len(parts) == 2:
                    title_text = parts[0].strip()
                    read_time = parts[1].rstrip(")")

            body_span = block.find(
                "span", style=lambda s: s and "Helvetica" in s if s else False
            )
            body = body_span.get_text(" ", strip=True) if body_span else ""

            current_section.stories.append(
                Story(title=title_text, url=real_url, body=body, read_time=read_time)
            )

    if current_section and current_section.stories:
        sections.append(current_section)

    return sections


class TldrParser(Parser):
    def parse(self, raw: RawMessage, metadata: dict[str, object]) -> Newsletter:
        msg = email.message_from_bytes(raw.raw_bytes)

        html_body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        html_body = payload.decode(
                            part.get_content_charset() or "utf-8", errors="replace"
                        )
                    break
        else:
            payload = msg.get_payload(decode=True)
            if isinstance(payload, bytes):
                html_body = payload.decode(
                    msg.get_content_charset() or "utf-8", errors="replace"
                )

        soup = BeautifulSoup(html_body, "html.parser")
        date = _extract_date(soup)
        sections = _extract_sections(soup)

        title_prefix = str(metadata.get("title_prefix", "TLDR"))
        title = f"{title_prefix} — {date}"

        log.info(
            "parser.done",
            source=raw.source_name,
            date=date,
            sections=len(sections),
            stories=sum(len(s.stories) for s in sections),
        )

        return Newsletter(
            source_name=raw.source_name,
            title=title,
            date=date,
            message_id=raw.message_id,
            received_at=raw.received_at,
            sections=sections,
            author=str(metadata.get("author", "TLDR")),
            author_sort=str(metadata.get("author_sort", "")),
            publisher=str(metadata.get("publisher", "TLDR Newsletter")),
            subjects=list(metadata.get("subjects", [])),  # type: ignore[arg-type]
            language=str(metadata.get("language", "en")),
            rights=str(metadata.get("rights", "")),
        )
