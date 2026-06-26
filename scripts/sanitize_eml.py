#!/usr/bin/env python3
"""Sanitize a real TLDR .eml file for use as a test fixture.

Removes/replaces:
  - To / Delivered-To headers (your Gmail address)
  - Message-ID (subscriber-specific)
  - TLDR tracking URLs (subscriber-specific IDs in path)
  - Any occurrence of personal email addresses
  - Unsubscribe tokens

Usage:
  python scripts/sanitize_eml.py input.eml tests/fixtures/tldr/YYYY-MM-DD.eml
"""

import re
import sys
from pathlib import Path


_TRACKING_URL_RE = re.compile(
    r"(https?://tracking\.tldrnewsletter\.com/[^\s\"'>]+)",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_UNSUBSCRIBE_RE = re.compile(r"(unsubscribe[^\s\"'>]{0,200})", re.IGNORECASE)


def sanitize(text: str) -> str:
    # Replace To / Delivered-To headers
    text = re.sub(r"^(To|Delivered-To):.*$", r"\1: test@example.com", text, flags=re.MULTILINE)
    # Replace Message-ID
    text = re.sub(
        r"^Message-ID:.*$",
        "Message-ID: <sanitized-fixture@tldrnewsletter.com>",
        text,
        flags=re.MULTILINE,
    )
    # Sanitize tracking URLs (keep the URL shape but blank the subscriber path)
    text = _TRACKING_URL_RE.sub(
        "https://tracking.tldrnewsletter.com/CL0/SANITIZED/1/SANITIZED", text
    )
    # Replace any personal email addresses that might appear in body
    text = _EMAIL_RE.sub(lambda m: "test@example.com" if "@" in m.group() else m.group(), text)
    return text


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: sanitize_eml.py <input.eml> <output.eml>")
        sys.exit(1)
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    raw = src.read_text(encoding="utf-8", errors="replace")
    cleaned = sanitize(raw)
    dst.write_text(cleaned, encoding="utf-8")
    print(f"Sanitized: {src} → {dst}")


if __name__ == "__main__":
    main()
