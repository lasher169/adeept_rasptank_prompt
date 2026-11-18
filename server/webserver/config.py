"""Settings from the repo-root ``.env``."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]

load_dotenv(ROOT / ".env")


def port() -> int:
    """Listen port from ``WEB_PORT``, default 5000."""
    raw = os.environ.get("WEB_PORT", "5000").strip()
    try:
        value = int(raw)
    except ValueError:
        raise SystemExit(f"WEB_PORT must be a number, got {raw!r}") from None
    if not 1 <= value <= 65535:
        raise SystemExit(f"WEB_PORT must be 1-65535, got {value}")
    return value


def host() -> str:
    """Bind address from ``WEB_HOST``, default 0.0.0.0."""
    return os.environ.get("WEB_HOST", "0.0.0.0").strip() or "0.0.0.0"
