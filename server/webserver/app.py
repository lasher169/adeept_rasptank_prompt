"""The RaspTank HTTP layer: FPV stream, the Vue frontend, prompt intake, /health.

One Flask app, one entry point. Previously there were two — ``server/app.py``
(video + static files) and this module (prompt routes) — joined by
``add_prompt_routes(app)`` plus an orphan ``app = add_prompt_routes(Flask())``
that nobody served. ``webServer.py`` now imports this app and starts it.

Routes
    GET  /video_feed   multipart MJPEG stream from the camera
    GET  /             dist/index.html (and every static asset the SPA asks for)
    GET  /health       {"ok": true, ...}
    POST /prompt       {"prompt": "..."} -> runs it through the agent

Run standalone for development:  python -m webserver
"""

from __future__ import annotations

import logging
import os
import threading

from flask import Flask, jsonify, Response, request, send_from_directory
from werkzeug.serving import run_simple

try:
    from flask_cors import CORS
except ImportError:      # optional: the front-end is same-origin in production
    CORS = None

from webserver.config import host, port
from webserver.prompts import PROMPTS, submit

DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dist")

app = Flask(__name__)
if CORS:
    CORS(app, supports_credentials=True)

_camera = None
_server = None


def camera():
    """The camera instance, created on first use.

    Creating it at import time made this module unimportable without a camera
    attached, which is why there were no tests.
    """
    global _camera
    if _camera is None:
        from camera_opencv import Camera
        _camera = Camera()
    return _camera


def set_camera_mode(mode: str) -> None:
    """Switch OpenCV processing: none | watchDog | findColor | findlineCV."""
    from camera_opencv import Camera
    Camera.modeSelect = mode


def set_color_find(h: int, s: int, v: int) -> None:
    """Set the HSV target for findColor mode."""
    camera().colorFindSet(h, s, v)


def start() -> None:
    """Serve the HTTP app in a daemon thread so the WebSocket loop keeps running."""
    global _server
    if _server is not None:
        return _server
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    _server = threading.Thread(target=run_simple, args=(host(), port(), app),
                               kwargs={"threaded": True}, name="http")
    _server.start()
    return _server


@app.get("/video_feed")
def video_feed():
    """MJPEG stream — the src of the <img> in the frontend."""
    return Response(_stream(), mimetype="multipart/x-mixed-replace; boundary=frame")


def _stream():
    cam = camera()
    while True:
        for frame in cam.get_frame():
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")


@app.get("/")
def index():
    return send_from_directory(DIST, "index.html")


@app.route("/<path:filename>")   # js, css, fonts, img, favicon, service-worker...
def static_files(filename):
    return send_from_directory(DIST, filename)


@app.get("/health")
def health():
    return jsonify(ok=True, prompts=len(PROMPTS))


@app.post("/prompt")
def prompt():
    body = request.get_json(silent=True) or request.form
    return jsonify(submit((body.get("prompt") or "").strip()))


if __name__ == "__main__":
    start().join()
