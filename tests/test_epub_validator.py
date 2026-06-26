from __future__ import annotations

from pathlib import Path

from newsletter_kindle.models import Document
from newsletter_kindle.validation.epub_validator import ValidationResult, validate_epub


def _doc() -> Document:
    return Document(
        message_id="<v1>",
        data=b"PK\x03\x04fake",
        mime_type="application/epub+zip",
        filename="test.epub",
    )


def test_validate_no_jar(tmp_path: Path) -> None:
    # When epubcheck.jar doesn't exist, returns ok=True with a warning
    result = validate_epub(_doc())
    assert result.ok is True
    assert any("not available" in w.lower() or "EPUBCheck" in w for w in result.warnings)


def test_validation_result_dataclass() -> None:
    r = ValidationResult(ok=True, errors=[], warnings=["test"])
    assert r.ok
    assert r.warnings == ["test"]
