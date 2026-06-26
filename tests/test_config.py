from __future__ import annotations

from pathlib import Path

import pytest

from newsletter_kindle.config import _resolve_env, load_config


def test_resolve_env_plain_string() -> None:
    assert _resolve_env("hello") == "hello"


def test_resolve_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("_TEST_VAR_NTK", "resolved_value")
    assert _resolve_env("${_TEST_VAR_NTK}") == "resolved_value"


def test_resolve_env_missing_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("_MISSING_NTK", raising=False)
    with pytest.raises(ValueError, match="_MISSING_NTK"):
        _resolve_env("${_MISSING_NTK}")


def test_resolve_env_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("_TEST_HOST_NTK", "imap.gmail.com")
    result = _resolve_env({"host": "${_TEST_HOST_NTK}", "port": 993})
    assert result["host"] == "imap.gmail.com"
    assert result["port"] == 993


def test_load_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_KINDLE_NTK", "me@kindle.com")
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "sources:\n  - name: tldr\n    enabled: true\n"
        "senders:\n  kindle:\n    to: ${TEST_KINDLE_NTK}\n"
    )
    cfg = load_config(cfg_file)
    assert cfg["sources"][0]["name"] == "tldr"
    assert cfg["senders"]["kindle"]["to"] == "me@kindle.com"
