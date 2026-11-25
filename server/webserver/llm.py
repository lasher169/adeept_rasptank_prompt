"""OpenAI-compatible chat client using only the standard library.

Works with any OpenAI-shaped endpoint (api.openai.com, Ollama's /v1,
llama.cpp's server, LM Studio, ...), so there is no vendor SDK to install on
the Pi. Set LLM_BASE_URL, LLM_API_KEY and LLM_MODEL.

    from webserver.llm import ask
    ask("drive forward")

`run()` is the agent loop: send the prompt plus the tool schemas, execute any
tool calls the model asks for, feed the results back, and return the final text.
`ask()` is the thin wrapper that returns just that text.

No credentials are ever printed. The previous version did
`print("do i have the following", base, key, model)` on every request.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from webserver.config import env
from webserver.registry import registry

DEFAULT_TIMEOUT = 120
MAX_TURNS = 4
SYSTEM_PROMPT = (
    "You control a Raspberry Pi robot tank. Call the available tools to move it; "
    "answer briefly once the action is done."
)


def _config() -> Dict[str, Optional[str]]:
    return {
        "base": env("LLM_BASE_URL"),
        "key": env("LLM_API_KEY"),
        "model": env("LLM_MODEL"),
    }


def configured() -> bool:
    """True when LLM_BASE_URL and LLM_MODEL are set."""
    cfg = _config()
    return bool(cfg["base"] and cfg["model"])


def _post(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    key = env("LLM_API_KEY", "")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"LLM HTTP {exc.code}: {exc.read().decode()[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM request failed: {exc}") from exc
    except ssl.SSLError as exc:
        raise RuntimeError(f"TLS handshake failed: {exc}") from exc


def chat(messages: List[dict], tools: Optional[List[dict]] = None) -> dict:
    """Send one chat completion request and return the raw response."""
    cfg = _config()
    if not cfg["base"] or not cfg["model"]:
        raise RuntimeError(
            "LLM is not configured. Set LLM_BASE_URL, LLM_API_KEY and LLM_MODEL "
            "in server/config.txt, or export them."
        )

    base = cfg["base"].rstrip("/")
    if base.endswith("/chat/completions"):
        url = base
    elif base.endswith("/v1"):
        url = base + "/chat/completions"
    else:
        url = base + "/v1/chat/completions"

    payload: Dict[str, Any] = {"model": cfg["model"], "messages": messages}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    return _post(url, payload)


def run(prompt: str, tools: Optional[List[dict]] = None) -> Dict[str, Any]:
    """Run the agent loop, executing tool calls, and return reply + calls made.

    Returns {"reply": str, "calls": [{"name": ..., "args": {...}, "result": ...}]}.
    A model that ignores the tools and just answers in text is handled too.
    """
    if tools is None:
        from webserver.tools import registry
        tools = registry.get_schemas()

    messages: List[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    calls: List[dict] = []

    for _ in range(MAX_TURNS):
        response = chat(messages, tools)
        choice = response["choices"][0]
        message = choice["message"]
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            return {"reply": (message.get("content") or "").strip(), "calls": calls}

        messages.append(message)
        for call in tool_calls:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except ValueError:
                args = {}
            try:
                result = registry.call(name, **args)
            except Exception as exc:          # a bad tool call must not kill the robot
                result = f"error: {exc}"
            calls.append({"name": name, "args": args, "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", name),
                "content": str(result),
            })

    return {"reply": "stopped after %d tool turns" % MAX_TURNS, "calls": calls}


def ask(prompt: str) -> str:
    """Send a prompt to the configured LLM and return the text reply."""
    return run(prompt)["reply"]


if __name__ == "__main__":
    import sys
    print(ask(" ".join(sys.argv[1:])))
