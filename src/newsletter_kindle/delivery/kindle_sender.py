from __future__ import annotations

import contextlib
import re
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import structlog
from imap_tools import AND, MailBox

from newsletter_kindle.delivery.base import Sender
from newsletter_kindle.models import Document, SendReceipt
from newsletter_kindle.state.db import StateDB

log = structlog.get_logger()

_AMAZON_BOUNCE_SENDERS = {
    "mailer-daemon@amazon.com",
    "noreply@amazon.com",
    "device@kindleunlimited.com",
}
_BOUNCE_SUBJECT_RE = re.compile(
    r"(delivery failed|not delivered|conversion failed|document not delivered)",
    re.IGNORECASE,
)
_SUCCESS_WINDOW = timedelta(minutes=30)


class KindleEmailSender(Sender):
    def __init__(
        self,
        *,
        smtp_host: str = "smtp.gmail.com",
        smtp_port: int = 587,
        user: str,
        password: str,
        kindle_email: str,
        imap_host: str = "imap.gmail.com",
    ) -> None:
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._user = user
        self._password = password
        self._kindle_email = kindle_email
        self._imap_host = imap_host

    def send(self, document: Document, attempt_no: int) -> SendReceipt:
        msg = EmailMessage()
        msg["From"] = self._user
        msg["To"] = self._kindle_email
        msg["Subject"] = document.filename
        msg.set_content("Sent by newsletter-to-kindle.")
        msg.add_attachment(
            document.data,
            maintype="application",
            subtype="epub+zip",
            filename=document.filename,
        )

        with smtplib.SMTP(self._smtp_host, self._smtp_port) as s:
            s.starttls()
            s.login(self._user, self._password)
            s.send_message(msg)

        log.info(
            "kindle.sent",
            message_id=document.message_id,
            filename=document.filename,
            attempt=attempt_no,
        )
        return SendReceipt(
            message_id=document.message_id,
            sent_at=datetime.now(UTC),
            attempt_no=attempt_no,
        )

    def reconcile(self, db: StateDB) -> None:
        """Scan inbox for Amazon bounce emails and update state accordingly."""
        self._reconcile_bounces(db)
        self._confirm_stale_sends(db)

    def _reconcile_bounces(self, db: StateDB) -> None:
        log.info("reconcile.checking_bounces")
        try:
            with MailBox(self._imap_host).login(self._user, self._password) as mb:
                for msg in mb.fetch(AND(seen=False), mark_seen=False):
                    from_addr = (msg.from_ or "").lower()
                    subject = msg.subject or ""
                    if from_addr not in _AMAZON_BOUNCE_SENDERS and not _BOUNCE_SUBJECT_RE.search(
                        subject
                    ):
                        continue

                    # Try to correlate with an open send attempt by subject / filename
                    matched = self._match_bounce(db, msg)
                    if matched:
                        attempt_id, message_id = matched
                        db.confirm_send(attempt_id, "failed", bounce_reason=subject)
                        db.set_status(message_id, "confirmed_failed")
                        # Move bounce to kindle-bounces label
                        with contextlib.suppress(Exception):
                            mb.flag([msg.uid], ["kindle-bounces"], True)
                        log.warning("reconcile.bounce", message_id=message_id, reason=subject)
        except Exception as exc:
            log.error("reconcile.imap_error", error=str(exc))

    def _match_bounce(self, db: StateDB, msg: object) -> tuple[int, str] | None:
        for row in db.open_sends():
            # Heuristic: the bounce subject often contains the sent filename or dates
            if str(row["message_id"])[:10] in str(getattr(msg, "subject", "")):
                return int(row["id"]), str(row["message_id"])
        return None

    def _confirm_stale_sends(self, db: StateDB) -> None:
        """After the success window, treat no-bounce as confirmed OK."""
        now = datetime.now(UTC)
        for row in db.open_sends():
            sent_at = datetime.fromisoformat(str(row["sent_at"]))
            if sent_at.tzinfo is None:
                sent_at = sent_at.replace(tzinfo=UTC)
            if now - sent_at > _SUCCESS_WINDOW:
                db.confirm_send(int(row["id"]), "ok")
                db.set_status(str(row["message_id"]), "confirmed_ok")
                log.info("reconcile.presumed_ok", message_id=row["message_id"])
