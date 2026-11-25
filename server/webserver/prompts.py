"""Prompt intake shared by the HTTP and WebSocket paths.

`POST /prompt` and the WebSocket message `{"title": "prompt", ...}` both used to
append to a list, but only the WebSocket path called the LLM — the HTTP one was
a queue nobody read. One function now, so both transports behave the same.

    from webserver.prompts import submit
    submit("drive forward")
    # -> {"ok": True, "prompt": ..., "reply": ..., "calls": [...]}
"""

from __future__ import annotations

from typing import Dict, List

from webserver.llm import configured, run

PROMPTS: List[str] = []


def submit(text: str) -> Dict[str, object]:
    """Record a prompt and run it through the agent.

    Never raises: an unconfigured or unreachable LLM comes back as
    {"ok": False, "error": ...} so the client can show the message.
    """
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "missing prompt"}

    PROMPTS.append(text)
    if not configured():
        return {"ok": False, "prompt": text,
                "error": "LLM not configured (set LLM_BASE_URL, LLM_API_KEY, LLM_MODEL)"}

    try:
        result = run(text)
    except RuntimeError as exc:
        return {"ok": False, "prompt": text, "error": str(exc)}

    return {"ok": True, "prompt": text, "reply": result["reply"], "calls": result["calls"]}


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(submit(" ".join(sys.argv[1:])), indent=2))
