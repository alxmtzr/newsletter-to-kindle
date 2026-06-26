from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

import structlog

from newsletter_kindle.config import Secrets, load_config
from newsletter_kindle.delivery.kindle_sender import KindleEmailSender
from newsletter_kindle.epub.builder import build_epub
from newsletter_kindle.models import Document
from newsletter_kindle.notify.logging_config import configure_logging
from newsletter_kindle.notify.notifier import Notifier
from newsletter_kindle.parsers.tldr_parser import TldrParser
from newsletter_kindle.sources.imap_source import ImapEmailSource
from newsletter_kindle.state.db import StateDB
from newsletter_kindle.validation.epub_validator import validate_epub

log = structlog.get_logger()

_EPUB_DIR = Path("data/epubs")
_DB_PATH = Path("data/state.db")

MAX_ATTEMPTS = 3


def _build_sender(sender_cfg: dict[str, Any], secrets: Secrets) -> KindleEmailSender:
    return KindleEmailSender(
        user=secrets.gmail_user,
        password=secrets.gmail_app_password,
        kindle_email=secrets.kindle_email,
        smtp_port=secrets.smtp_port,
        smtp_ssl=secrets.smtp_ssl,
    )


def run(config_path: str = "config.yaml", dry_run: bool = False) -> None:
    configure_logging()
    cfg = load_config(config_path)
    secrets = Secrets()  # type: ignore[call-arg]

    _EPUB_DIR.mkdir(parents=True, exist_ok=True)
    db = StateDB(_DB_PATH)
    notifier = Notifier(
        user=secrets.gmail_user,
        password=secrets.gmail_app_password,
        alert_recipient=secrets.alert_recipient,
        healthchecks_url=secrets.healthchecks_url,
        smtp_port=secrets.smtp_port,
        smtp_ssl=secrets.smtp_ssl,
    )

    try:
        sender_configs: dict[str, Any] = cfg.get("senders", {})

        # Step 1: Reconcile bounces and confirm stale sends
        for _sender_name, sender_cfg in sender_configs.items():
            sender = _build_sender(sender_cfg, secrets)
            sender.reconcile(db)

        # Step 2: Process each enabled source
        for source_cfg in cfg.get("sources", []):
            if not source_cfg.get("enabled", True):
                continue
            _process_source(source_cfg, secrets, db, notifier, dry_run=dry_run)

        # Step 3: Dead-letter check
        for row in db.dead_letters():
            epub_path = row["epub_path"]
            if epub_path and Path(epub_path).exists():
                notifier.send_dead_letter(
                    message_id=str(row["message_id"]),
                    epub_data=Path(epub_path).read_bytes(),
                    epub_filename=Path(epub_path).name,
                )

        notifier.ping_success()

    except Exception:
        tb = traceback.format_exc()
        log.error("pipeline.crash", traceback=tb)
        notifier.ping_failure(tb)
        notifier.send_failure_email("Pipeline crash", tb)
        raise


def _process_source(
    source_cfg: dict[str, Any],
    secrets: Secrets,
    db: StateDB,
    notifier: Notifier,
    *,
    dry_run: bool,
) -> None:
    name: str = source_cfg["name"]
    match = source_cfg.get("match", {})
    metadata: dict[str, Any] = source_cfg.get("metadata", {})

    source = ImapEmailSource(
        host="imap.gmail.com",
        user=secrets.gmail_user,
        password=secrets.gmail_app_password,
        source_name=name,
        from_address=match.get("from", ""),
    )
    parser = TldrParser()

    known_ids = db.known_message_ids(name)

    for raw in source.fetch_new(known_ids):
        try:
            db.upsert_newsletter(
                message_id=raw.message_id,
                source=name,
                subject="",
                received_at=raw.received_at,
            )

            newsletter = parser.parse(raw, metadata)
            db.set_status(raw.message_id, "parsed")

            epub_dir = _EPUB_DIR / name
            document = build_epub(newsletter, epub_dir)
            db.set_status(raw.message_id, "epub_built", epub_path=str(epub_dir / document.filename))

            result = validate_epub(document)
            if not result.ok:
                raise RuntimeError(f"EPUBCheck failed: {result.errors}")
            db.set_status(raw.message_id, "validated")

            if dry_run:
                log.info("pipeline.dry_run_skip_send", message_id=raw.message_id)
                continue

            attempt_no = db.attempt_count(raw.message_id) + 1
            sender = KindleEmailSender(
                user=secrets.gmail_user,
                password=secrets.gmail_app_password,
                kindle_email=secrets.kindle_email,
                smtp_port=secrets.smtp_port,
                smtp_ssl=secrets.smtp_ssl,
            )
            sender.send(document, attempt_no)
            db.record_send(raw.message_id, attempt_no)
            db.set_status(raw.message_id, "sent")

        except Exception:
            tb = traceback.format_exc()
            db.set_status(raw.message_id, "confirmed_failed", last_error=tb[:2000])
            log.error("pipeline.source_error", message_id=raw.message_id, traceback=tb)

    # Send validated-but-unsent rows (e.g. left over from a previous dry-run)
    if not dry_run:
        for row in db.pending_sends():
            epub_path = Path(str(row["epub_path"])) if row["epub_path"] else None
            if not epub_path or not epub_path.exists():
                log.warning("pipeline.pending_no_epub", message_id=row["message_id"])
                continue
            try:
                document = Document(
                    message_id=str(row["message_id"]),
                    data=epub_path.read_bytes(),
                    mime_type="application/epub+zip",
                    filename=epub_path.name,
                )
                attempt_no = db.attempt_count(str(row["message_id"])) + 1
                sender = KindleEmailSender(
                    user=secrets.gmail_user,
                    password=secrets.gmail_app_password,
                    kindle_email=secrets.kindle_email,
                    smtp_port=secrets.smtp_port,
                    smtp_ssl=secrets.smtp_ssl,
                )
                sender.send(document, attempt_no)
                db.record_send(str(row["message_id"]), attempt_no)
                db.set_status(str(row["message_id"]), "sent")
            except Exception:
                tb = traceback.format_exc()
                db.set_status(str(row["message_id"]), "confirmed_failed", last_error=tb[:2000])
                log.error("pipeline.pending_send_error", message_id=row["message_id"])

    # Retry failed deliveries
    for row in db.pending_retries():
        epub_path = Path(str(row["epub_path"])) if row["epub_path"] else None
        if not epub_path or not epub_path.exists():
            log.warning("pipeline.retry_no_epub", message_id=row["message_id"])
            continue

        try:
            data = epub_path.read_bytes()
            document = Document(
                message_id=str(row["message_id"]),
                data=data,
                mime_type="application/epub+zip",
                filename=epub_path.name,
            )
            attempt_no = int(row["attempts"]) + 1
            sender = KindleEmailSender(
                user=secrets.gmail_user,
                password=secrets.gmail_app_password,
                kindle_email=secrets.kindle_email,
                smtp_port=secrets.smtp_port,
                smtp_ssl=secrets.smtp_ssl,
            )
            sender.send(document, attempt_no)
            db.record_send(str(row["message_id"]), attempt_no)
            db.set_status(str(row["message_id"]), "sent")

            if attempt_no >= MAX_ATTEMPTS:
                db.set_status(str(row["message_id"]), "dead_letter")

        except Exception:
            tb = traceback.format_exc()
            db.set_status(str(row["message_id"]), "confirmed_failed", last_error=tb[:2000])
            log.error("pipeline.retry_error", message_id=row["message_id"])
