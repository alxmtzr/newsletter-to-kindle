from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from newsletter_kindle.models import Document
from newsletter_kindle.validation.epub_validator import ValidationResult, validate_epub


def _doc() -> Document:
    return Document(
        message_id="<v1>",
        data=b"PK\x03\x04fake",
        mime_type="application/epub+zip",
        filename="test.epub",
    )


def _report(errors: list[str], warnings: list[str]) -> str:
    messages = [{"severity": "ERROR", "message": e} for e in errors]
    messages += [{"severity": "WARNING", "message": w} for w in warnings]
    return json.dumps({"messages": messages})


def test_validate_no_jar(tmp_path: Path) -> None:
    result = validate_epub(_doc())
    assert result.ok is True
    assert any("not available" in w.lower() or "EPUBCheck" in w for w in result.warnings)


def test_validation_result_dataclass() -> None:
    r = ValidationResult(ok=True, errors=[], warnings=["test"])
    assert r.ok
    assert r.warnings == ["test"]


def _fake_run_factory(report_json: str) -> object:
    def fake_run(cmd: list, **kwargs: object) -> MagicMock:
        for arg in cmd:
            if isinstance(arg, str) and arg.endswith("report.json"):
                Path(arg).write_text(report_json)
        return MagicMock(returncode=0, stderr="")

    return fake_run


def test_epubcheck_passes_with_no_errors() -> None:
    with patch("newsletter_kindle.validation.epub_validator._EPUBCHECK_JAR") as j:
        j.exists.return_value = True
        with patch("newsletter_kindle.validation.epub_validator._EPUBCHECK_LIB") as lib:
            lib.exists.return_value = False
            with patch(
                "newsletter_kindle.validation.epub_validator.subprocess.run",
                side_effect=_fake_run_factory(_report([], ["minor warning"])),
            ):
                result = validate_epub(_doc())
    assert result.ok is True
    assert result.errors == []
    assert len(result.warnings) == 1


def test_epubcheck_fails_with_errors() -> None:
    with patch("newsletter_kindle.validation.epub_validator._EPUBCHECK_JAR") as j:
        j.exists.return_value = True
        with patch("newsletter_kindle.validation.epub_validator._EPUBCHECK_LIB") as lib:
            lib.exists.return_value = False
            with patch(
                "newsletter_kindle.validation.epub_validator.subprocess.run",
                side_effect=_fake_run_factory(_report(["Missing dc:title"], [])),
            ):
                result = validate_epub(_doc())
    assert result.ok is False
    assert "Missing dc:title" in result.errors[0]


def test_epubcheck_uses_classpath_when_lib_exists() -> None:
    captured: list[list[str]] = []

    def fake_run(cmd: list, **kwargs: object) -> MagicMock:
        captured.append(list(cmd))
        for arg in cmd:
            if isinstance(arg, str) and arg.endswith("report.json"):
                Path(arg).write_text(_report([], []))
        return MagicMock(returncode=0, stderr="")

    with patch("newsletter_kindle.validation.epub_validator._EPUBCHECK_JAR") as j:
        j.exists.return_value = True
        with patch("newsletter_kindle.validation.epub_validator._EPUBCHECK_LIB") as lib:
            lib.exists.return_value = True
            _run = "newsletter_kindle.validation.epub_validator.subprocess.run"
            with patch(_run, side_effect=fake_run):
                validate_epub(_doc())

    assert captured[0][1] == "-cp"  # classpath mode, not -jar


def test_epubcheck_no_report_returns_error() -> None:
    def fake_run(cmd: list, **kwargs: object) -> MagicMock:
        return MagicMock(returncode=1, stderr="Java crashed")

    with patch("newsletter_kindle.validation.epub_validator._EPUBCHECK_JAR") as j:
        j.exists.return_value = True
        with patch("newsletter_kindle.validation.epub_validator._EPUBCHECK_LIB") as lib:
            lib.exists.return_value = False
            _run = "newsletter_kindle.validation.epub_validator.subprocess.run"
            with patch(_run, side_effect=fake_run):
                result = validate_epub(_doc())

    assert result.ok is False
    assert "no report" in result.errors[0].lower()
