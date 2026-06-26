from __future__ import annotations

from unittest.mock import MagicMock, patch

from newsletter_kindle.delivery.kindle_sender import KindleEmailSender
from newsletter_kindle.models import Document


def _doc() -> Document:
    return Document(
        message_id="<smtp-test>",
        data=b"epub-bytes",
        mime_type="application/epub+zip",
        filename="tldr_20240115.epub",
    )


def test_send_uses_smtp() -> None:
    sender = KindleEmailSender(
        user="u@gmail.com",
        password="pw",
        kindle_email="me@kindle.com",
    )
    with patch("newsletter_kindle.delivery.kindle_sender.smtplib.SMTP_SSL") as mock_smtp:
        mock_ctx = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        receipt = sender.send(_doc(), 1)

    mock_ctx.send_message.assert_called_once()
    assert receipt.message_id == "<smtp-test>"
    assert receipt.attempt_no == 1


def test_send_ssl_login_called() -> None:
    sender = KindleEmailSender(user="u@gmail.com", password="pw", kindle_email="k@kindle.com")
    with patch("newsletter_kindle.delivery.kindle_sender.smtplib.SMTP_SSL") as mock_smtp:
        mock_ctx = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        sender.send(_doc(), 1)
    mock_ctx.login.assert_called_once_with("u@gmail.com", "pw")
