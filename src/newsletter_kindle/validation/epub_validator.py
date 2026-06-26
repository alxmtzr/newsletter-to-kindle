from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import structlog

from newsletter_kindle.models import Document

log = structlog.get_logger()

_EPUBCHECK_JAR = Path("/opt/epubcheck/epubcheck.jar")


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str]
    warnings: list[str]


def validate_epub(document: Document) -> ValidationResult:
    if not _EPUBCHECK_JAR.exists():
        log.warning("epubcheck.jar_not_found", path=str(_EPUBCHECK_JAR))
        return ValidationResult(ok=True, errors=[], warnings=["EPUBCheck not available"])

    with tempfile.TemporaryDirectory() as tmp:
        epub_path = Path(tmp) / document.filename
        epub_path.write_bytes(document.data)
        report_path = Path(tmp) / "report.json"

        result = subprocess.run(
            [
                "java", "-jar", str(_EPUBCHECK_JAR),
                str(epub_path),
                "--json", str(report_path),
                "--mode", "epub",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

    if not report_path.exists():
        log.error("epubcheck.no_report", stderr=result.stderr[:500])
        return ValidationResult(ok=False, errors=["EPUBCheck produced no report"], warnings=[])

    report = json.loads(report_path.read_text())
    messages = report.get("messages", [])
    errors = [m["message"] for m in messages if m.get("severity") == "ERROR"]
    warnings = [m["message"] for m in messages if m.get("severity") == "WARNING"]

    ok = len(errors) == 0
    log.info("epubcheck.done", errors=len(errors), warnings=len(warnings), ok=ok)
    return ValidationResult(ok=ok, errors=errors, warnings=warnings)
