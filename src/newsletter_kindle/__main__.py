from __future__ import annotations

import argparse
from pathlib import Path

from newsletter_kindle.notify.logging_config import configure_logging
from newsletter_kindle.pipeline import run
from newsletter_kindle.state.db import StateDB


def _cmd_run(args: argparse.Namespace) -> None:
    configure_logging(args.log_level)
    run(config_path=args.config, dry_run=args.dry_run)


def _cmd_build(args: argparse.Namespace) -> None:
    """Parse a local .eml file and build an EPUB without touching IMAP, SQLite, or Kindle."""
    configure_logging("INFO")
    from datetime import UTC, datetime

    from newsletter_kindle.config import load_config
    from newsletter_kindle.epub.builder import build_epub
    from newsletter_kindle.models import RawMessage
    from newsletter_kindle.parsers.tldr_parser import TldrParser

    eml_path = Path(args.eml)
    if not eml_path.exists():
        print(f"Error: file not found: {eml_path}")
        raise SystemExit(1)

    cfg = load_config(args.config)
    source_name = args.source
    metadata: dict[str, object] = {}
    for src in cfg.get("sources", []):
        if src.get("name") == source_name:
            metadata = src.get("metadata", {})
            break

    raw = RawMessage(
        source_name=source_name,
        message_id=f"<local-build-{eml_path.stem}>",
        received_at=datetime.now(UTC),
        raw_bytes=eml_path.read_bytes(),
    )

    newsletter = TldrParser().parse(raw, metadata)
    out_dir = Path(args.output)
    doc = build_epub(newsletter, out_dir)
    out_path = out_dir / doc.filename
    print(f"EPUB written to: {out_path}  ({len(doc.data)} bytes)")


def _cmd_test_alert(args: argparse.Namespace) -> None:
    """Send a test notification email to verify SMTP credentials and alert recipient."""
    configure_logging("INFO")
    from newsletter_kindle.config import Secrets
    from newsletter_kindle.notify.notifier import Notifier

    secrets = Secrets()  # type: ignore[call-arg]
    notifier = Notifier(
        user=secrets.gmail_user,
        password=secrets.gmail_app_password,
        alert_recipient=secrets.alert_recipient,
        healthchecks_url=secrets.healthchecks_url,
    )
    print(f"Sending test alert to {secrets.alert_recipient} ...")
    notifier.send_failure_email(
        "Test alert",
        "This is a test notification from newsletter-to-kindle.\n\n"
        "If you received this, alert emails are working correctly.",
    )
    print("Done. Check your inbox.")


def _cmd_test_kindle(args: argparse.Namespace) -> None:
    """Send a deliberately invalid EPUB to Kindle to trigger an Amazon bounce.

    Use this to verify the full retry loop end-to-end:
      1. Sends a corrupt EPUB via SMTP to your @kindle.com address
      2. Amazon rejects it and sends a bounce back (usually within 5-10 min)
      3. On the next `run`, the reconciler detects the bounce and marks it failed
      4. The retry mechanism kicks in on the subsequent run

    Watch progress with: python -m newsletter_kindle status
    """
    configure_logging("INFO")
    import io
    import smtplib
    import uuid
    import zipfile
    from datetime import UTC, datetime
    from email.message import EmailMessage

    from newsletter_kindle.config import Secrets

    secrets = Secrets()  # type: ignore[call-arg]

    # Minimal but deliberately broken EPUB — valid ZIP, invalid EPUB structure
    # Amazon accepts the SMTP delivery but fails conversion and sends a bounce
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", "<broken>not valid epub xml</broken>")
        z.writestr("content.opf", "<also broken>")
    epub_bytes = buf.getvalue()
    filename = f"test-invalid-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.epub"

    # Record in SQLite so the reconciler can match the bounce by filename
    db = StateDB(args.db)
    fake_message_id = f"<test-kindle-{uuid.uuid4()}>"
    db.upsert_newsletter(
        message_id=fake_message_id,
        source="test",
        subject=f"Test invalid EPUB {filename}",
        received_at=datetime.now(UTC),
        status="validated",
    )
    db.set_status(fake_message_id, "validated", epub_path=f"/tmp/{filename}")

    msg = EmailMessage()
    msg["From"] = secrets.gmail_user
    msg["To"] = secrets.kindle_email
    msg["Subject"] = filename
    msg.set_content("Test invalid EPUB — sent by newsletter-to-kindle test-kindle command.")
    msg.add_attachment(epub_bytes, maintype="application", subtype="epub+zip", filename=filename)

    print(f"Sending invalid EPUB '{filename}' to {secrets.kindle_email} ...")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(secrets.gmail_user, secrets.gmail_app_password)
        s.send_message(msg)

    db.record_send(fake_message_id, 1)
    db.set_status(fake_message_id, "sent")

    print("Sent. Amazon will bounce within ~10 minutes.")
    print("Then run:  python -m newsletter_kindle run  (to trigger reconciliation)")
    print("Check:     python -m newsletter_kindle status")
    print(f"Message ID in DB: {fake_message_id}")


def _cmd_cleanup(args: argparse.Namespace) -> None:
    """Remove entries from the SQLite state DB."""
    configure_logging("WARNING")
    db = StateDB(args.db)

    removed = 0

    if args.test:
        cur = db._conn.execute("DELETE FROM send_attempts WHERE message_id LIKE '<test-kindle-%'")
        removed += cur.rowcount
        cur = db._conn.execute("DELETE FROM newsletters WHERE message_id LIKE '<test-kindle-%'")
        removed += cur.rowcount
        db._conn.commit()
        print(f"Removed {removed} test-kindle rows.")

    if args.old is not None:
        cur = db._conn.execute(
            """
            DELETE FROM send_attempts WHERE message_id IN (
                SELECT message_id FROM newsletters
                WHERE status IN ('confirmed_ok', 'dead_letter')
                AND received_at < date('now', ?)
            )
            """,
            (f"-{args.old} days",),
        )
        sa_removed = cur.rowcount
        cur = db._conn.execute(
            """
            DELETE FROM newsletters
            WHERE status IN ('confirmed_ok', 'dead_letter')
            AND received_at < date('now', ?)
            """,
            (f"-{args.old} days",),
        )
        nl_removed = cur.rowcount
        db._conn.commit()
        print(
            f"Removed {nl_removed} newsletters and {sa_removed} send attempts"
            f" older than {args.old} days."
        )

    if not args.test and args.old is None:
        print("Nothing to do. Use --test to remove test entries,")
        print("  or --old N to remove confirmed/dead entries older than N days.")
        print("Example: python -m newsletter_kindle cleanup --test --old 30")


def _cmd_status(args: argparse.Namespace) -> None:
    configure_logging("WARNING")
    db = StateDB(args.db)
    rows = db.recent(limit=args.limit)
    header = (
        f"{'MESSAGE_ID':<45} {'SOURCE':<12} {'STATUS':<18} "
        f"{'ATTEMPTS':<9} {'RECEIVED':<24} {'ERROR'}"
    )
    print(header)
    print("-" * 120)
    for row in rows:
        err = (row["last_error"] or "")[:60].replace("\n", " ")
        print(
            f"{str(row['message_id'])[:44]:<45} "
            f"{row['source']:<12} "
            f"{row['status']:<18} "
            f"{row['attempts']:<9} "
            f"{row['received_at']:<24} "
            f"{err}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(prog="newsletter-kindle")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run the pipeline once")
    p_run.add_argument("--config", default="config.yaml")
    p_run.add_argument("--dry-run", action="store_true", help="Skip SMTP send")
    p_run.add_argument("--log-level", default="INFO")
    p_run.set_defaults(func=_cmd_run)

    p_build = sub.add_parser("build", help="Build an EPUB from a local .eml file")
    p_build.add_argument("eml", help="Path to a .eml file")
    p_build.add_argument("--source", default="tldr", help="Source name (for metadata lookup)")
    p_build.add_argument("--config", default="config.yaml")
    p_build.add_argument("--output", default="/tmp", help="Output directory for the EPUB")
    p_build.set_defaults(func=_cmd_build)

    p_alert = sub.add_parser("test-alert", help="Send a test notification email")
    p_alert.set_defaults(func=_cmd_test_alert)

    p_kindle = sub.add_parser(
        "test-kindle", help="Send an invalid EPUB to Kindle to test the bounce/retry loop"
    )
    p_kindle.add_argument("--db", default="data/state.db")
    p_kindle.set_defaults(func=_cmd_test_kindle)

    p_cleanup = sub.add_parser("cleanup", help="Remove entries from the state DB")
    p_cleanup.add_argument("--db", default="data/state.db")
    p_cleanup.add_argument("--test", action="store_true", help="Remove test-kindle entries")
    p_cleanup.add_argument(
        "--old", type=int, metavar="DAYS", help="Remove confirmed/dead entries older than N days"
    )
    p_cleanup.set_defaults(func=_cmd_cleanup)

    p_status = sub.add_parser("status", help="Show recent newsletter state")
    p_status.add_argument("--db", default="data/state.db")
    p_status.add_argument("--limit", type=int, default=20)
    p_status.set_defaults(func=_cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
