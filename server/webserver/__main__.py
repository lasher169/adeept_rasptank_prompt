"""Run the prompt intake server: ``python -m webserver``."""

from __future__ import annotations

import logging

from werkzeug.serving import run_simple

from . import config
from .app import app

if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    run_simple(config.host(), config.port(), app, threaded=True)
