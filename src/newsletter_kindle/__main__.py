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
    print(f"EPUB written to: {out_path}  ({doc.data.__len__()} bytes)")


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

    p_status = sub.add_parser("status", help="Show recent newsletter state")
    p_status.add_argument("--db", default="data/state.db")
    p_status.add_argument("--limit", type=int, default=20)
    p_status.set_defaults(func=_cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
