from __future__ import annotations

from unittest.mock import MagicMock, patch

from newsletter_kindle.notify.notifier import Notifier


def _notifier(**kwargs) -> Notifier:
    defaults = dict(user="u@gmail.com", password="pw", alert_recipient="me@example.com")
    defaults.update(kwargs)
    return Notifier(**defaults)


def test_ping_success_no_url() -> None:
    n = _notifier()
    n.ping_success()  # no-op when no URL, should not raise


def test_ping_success_calls_urlopen() -> None:
    n = _notifier(healthchecks_url="https://hc-ping.com/test-uuid")
    with patch("newsletter_kindle.notify.notifier.urllib.request.urlopen") as mock_open:
        n.ping_success()
    mock_open.assert_called_once()


def test_ping_failure_posts_fail_url() -> None:
    n = _notifier(healthchecks_url="https://hc-ping.com/test-uuid")
    with patch("newsletter_kindle.notify.notifier.urllib.request.urlopen") as mock_open:
        n.ping_failure("some error")
    called_url = mock_open.call_args[0][0].full_url
    assert called_url.endswith("/fail")


def test_ping_failure_no_url() -> None:
    n = _notifier()
    n.ping_failure("error")  # no-op when no URL


def test_send_failure_email_uses_smtp() -> None:
    n = _notifier()
    with patch("newsletter_kindle.notify.notifier.smtplib.SMTP_SSL") as mock_smtp:
        mock_ctx = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        n.send_failure_email("Pipeline crash", "traceback here")
    mock_ctx.send_message.assert_called_once()


def test_send_dead_letter_attaches_epub() -> None:
    n = _notifier()
    with patch("newsletter_kindle.notify.notifier.smtplib.SMTP_SSL") as mock_smtp:
        mock_ctx = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        n.send_dead_letter("<msg1>", b"epub-bytes", "tldr_20240115.epub")
    mock_ctx.send_message.assert_called_once()
    sent_msg = mock_ctx.send_message.call_args[0][0]
    assert "tldr_20240115.epub" in sent_msg["Subject"]


def test_configure_logging() -> None:
    import logging as _logging

    import structlog

    from newsletter_kindle.notify.logging_config import configure_logging as _configure

    try:
        _configure("INFO")
    finally:
        structlog.reset_defaults()
        structlog.configure(
            processors=[
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(_logging.WARNING),
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=False,
        )
