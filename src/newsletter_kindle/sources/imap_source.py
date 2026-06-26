from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import structlog
from imap_tools import AND, MailBox

from newsletter_kindle.models import RawMessage
from newsletter_kindle.sources.base import Source

log = structlog.get_logger()


class ImapEmailSource(Source):
    def __init__(
        self,
        *,
        host: str,
        user: str,
        password: str,
        source_name: str,
        from_address: str,
        folder: str = "INBOX",
    ) -> None:
        self._host = host
        self._user = user
        self._password = password
        self._source_name = source_name
        self._from_address = from_address
        self._folder = folder

    def fetch_new(self, known_ids: set[str]) -> Iterator[RawMessage]:
        log.info("imap.connect", host=self._host, user=self._user)
        with MailBox(self._host).login(self._user, self._password) as mb:
            mb.folder.set(self._folder)
            for msg in mb.fetch(AND(from_=self._from_address, seen=False), mark_seen=False):
                raw_headers: dict[str, list[str]] = dict(msg.headers)
                mid_list = raw_headers.get("message-id", [])
                mid: str = (mid_list[0] if mid_list else None) or str(msg.uid)
                if mid in known_ids:
                    log.debug("imap.skip_known", message_id=mid)
                    continue
                received_at = msg.date or datetime.now(UTC)
                if received_at.tzinfo is None:
                    received_at = received_at.replace(tzinfo=UTC)
                log.info("imap.found", message_id=mid, subject=msg.subject)
                yield RawMessage(
                    source_name=self._source_name,
                    message_id=mid,
                    received_at=received_at,
                    raw_bytes=msg.obj.as_bytes(),
                )
