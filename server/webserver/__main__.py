"""Run only the HTTP layer, for developing the front-end without a Pi attached.

    python -m webserver
"""

from __future__ import annotations

from . import config
from .app import app

if __name__ == "__main__":
    app.run(host=config.host(), port=config.port(), threaded=True)
