"""Prompt intake over HTTP.

POST /prompt  {"prompt": "drive forward"}  -> {"ok": true, "prompt": "..."}
GET  /health                               -> {"ok": true, "prompts": 0}

The LLM call goes where ``PROMPTS.append`` is; nothing consumes the list yet.
"""

from __future__ import annotations

from flask import Flask, jsonify, request

app = Flask(__name__)

PROMPTS: list[str] = []


@app.get("/health")
def health():
    return jsonify(ok=True, prompts=len(PROMPTS))


@app.post("/prompt")
def prompt():
    body = request.get_json(silent=True) or request.form
    text = (body.get("prompt") or "").strip()
    if not text:
        return jsonify(ok=False, error="missing 'prompt'"), 400

    PROMPTS.append(text)
    return jsonify(ok=True, prompt=text, count=len(PROMPTS))
