"""Run the prompt intake server: ``python -m webserver``."""

from __future__ import annotations

from . import config
from .app import app

if __name__ == "__main__":
    app.run(host=config.host(), port=config.port(), debug=False)
