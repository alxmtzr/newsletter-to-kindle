from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Story:
    title: str
    url: str
    body: str
    read_time: str = ""


@dataclass
class Section:
    title: str
    emoji: str
    stories: list[Story] = field(default_factory=list)


@dataclass
class Newsletter:
    source_name: str
    title: str          # e.g. "TLDR — 2026-06-26"
    date: str           # ISO 8601 e.g. "2026-06-26"
    message_id: str
    received_at: datetime
    sections: list[Section] = field(default_factory=list)
    # populated from config.yaml per-source metadata block
    author: str = ""
    author_sort: str = ""
    publisher: str = ""
    subjects: list[str] = field(default_factory=list)
    language: str = "en"
    rights: str = ""


@dataclass
class RawMessage:
    source_name: str
    message_id: str
    received_at: datetime
    raw_bytes: bytes


@dataclass
class Document:
    message_id: str
    data: bytes
    mime_type: str
    filename: str


@dataclass
class SendReceipt:
    message_id: str
    sent_at: datetime
    attempt_no: int
