from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Secrets(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gmail_user: str
    gmail_app_password: str
    kindle_email: str
    alert_recipient: str
    healthchecks_url: str = ""  # optional; empty = disabled


def _resolve_env(value: Any) -> Any:
    """Resolve ${VAR} references in config values."""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        var = value[2:-1]
        resolved = os.environ.get(var, "")
        if not resolved:
            raise ValueError(f"Config references undefined env var: {var}")
        return resolved
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    return value


def load_config(path: Path | str = "config.yaml") -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    raw: dict[str, Any] = yaml.safe_load(text)
    return _resolve_env(raw)
