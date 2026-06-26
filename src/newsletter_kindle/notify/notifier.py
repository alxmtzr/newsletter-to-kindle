from __future__ import annotations

import smtplib
import traceback
import urllib.request
from email.message import EmailMessage

import structlog

log = structlog.get_logger()


class Notifier:
    def __init__(
        self,
        *,
        smtp_host: str = "smtp.gmail.com",
        smtp_port: int = 587,
        user: str,
        password: str,
        alert_recipient: str,
        healthchecks_url: str = "",
    ) -> None:
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._user = user
        self._password = password
        self._alert_recipient = alert_recipient
        self._healthchecks_url = healthchecks_url

    def ping_success(self) -> None:
        if not self._healthchecks_url:
            return
        try:
            urllib.request.urlopen(self._healthchecks_url, timeout=5)
            log.debug("healthchecks.pinged")
        except Exception as exc:
            log.warning("healthchecks.ping_failed", error=str(exc))

    def ping_failure(self, detail: str = "") -> None:
        if not self._healthchecks_url:
            return
        try:
            fail_url = self._healthchecks_url.rstrip("/") + "/fail"
            req = urllib.request.Request(
                fail_url,
                data=detail.encode()[:10000],
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as exc:
            log.warning("healthchecks.fail_ping_error", error=str(exc))

    def send_failure_email(self, subject: str, body: str) -> None:
        self._send_email(subject=f"[newsletter-to-kindle] {subject}", body=body)

    def send_dead_letter(self, message_id: str, epub_data: bytes, epub_filename: str) -> None:
        msg = EmailMessage()
        msg["From"] = self._user
        msg["To"] = self._alert_recipient
        msg["Subject"] = f"[newsletter-to-kindle] Dead letter: {epub_filename}"
        msg.set_content(
            f"Delivery failed after 3 attempts.\n\nMessage ID: {message_id}\n"
            "The EPUB is attached — you can sideload it manually."
        )
        msg.add_attachment(
            epub_data,
            maintype="application",
            subtype="epub+zip",
            filename=epub_filename,
        )
        self._send(msg)
        log.warning("notifier.dead_letter_sent", message_id=message_id)

    def _send_email(self, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self._user
        msg["To"] = self._alert_recipient
        msg["Subject"] = subject
        msg.set_content(body)
        self._send(msg)

    def _send(self, msg: EmailMessage) -> None:
        try:
            with smtplib.SMTP(self._smtp_host, self._smtp_port) as s:
                s.starttls()
                s.login(self._user, self._password)
                s.send_message(msg)
        except Exception as exc:
            log.error("notifier.send_failed", error=str(exc))
