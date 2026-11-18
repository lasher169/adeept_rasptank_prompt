"""Prompt intake over HTTP.

POST /prompt  {"prompt": "drive forward"}  -> {"ok": true, "prompt": "..."}
GET  /health                               -> {"ok": true, "prompts": 0}

The LLM call goes where ``PROMPTS.append`` is; nothing consumes the list yet.
"""

from __future__ import annotations

from flask import Flask, jsonify, request

PROMPTS: list[str] = []


def add_prompt_routes(target: Flask) -> Flask:
    """Attach /health and /prompt to ``target``."""

    @target.get("/health")
    def health():
        return jsonify(ok=True, prompts=len(PROMPTS))

    @target.post("/prompt")
    def prompt():
        body = request.get_json(silent=True) or request.form
        text = (body.get("prompt") or "").strip()
        if not text:
            return jsonify(ok=False, error="missing 'prompt'"), 400

        PROMPTS.append(text)
        return jsonify(ok=True, prompt=text, count=len(PROMPTS))

    return target


app = add_prompt_routes(Flask(__name__))
