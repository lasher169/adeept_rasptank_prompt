"""A minimal tool registry: name -> function, with OpenAI-shaped schemas.

    registry.register("forward", drive_forward, description="drive forward")
    registry.call("forward")
    registry.get_schemas()      # what the LLM sees as its available tools
"""

import inspect
import typing
from typing import Any, Callable, Dict, List, Optional


class ToolRegistry:
    """Registry of callable tools exposed to the LLM."""

    def __init__(self) -> None:
        self.tools: Dict[str, Callable] = {}
        self.descriptions: Dict[str, str] = {}

    def register(self, func: Optional[Callable] = None, name: Optional[str] = None,
                 description: Optional[str] = None) -> Callable:
        """Add a tool. Works bare (@registry.register) or with args.

        Re-registering a name replaces it. The docstring becomes the tool
        description the model sees.
        """
        def deco(f: Callable) -> Callable:
            key = name or f.__name__
            self.tools[key] = f
            self.descriptions[key] = description or inspect.getdoc(f) or ""
            return f
        return deco(func) if func is not None else deco

    def unregister(self, name: str) -> bool:
        """Remove a tool. Returns True if it existed."""
        self.descriptions.pop(name, None)
        return self.tools.pop(name, None) is not None

    def get(self, name: str) -> Callable:
        """Return a tool, raising KeyError if it is not registered."""
        if name not in self.tools:
            raise KeyError(f"unknown tool: {name}")
        return self.tools[name]

    def call(self, name: str, *args, **kwargs) -> Any:
        """Look up a tool by name and run it."""
        return self.get(name)(*args, **kwargs)

    def names(self) -> List[str]:
        return sorted(self.tools)

    def get_schemas(self) -> List[dict]:
        """OpenAI 'tools' payloads built from signatures + docstrings."""
        kinds = {str: "string", int: "integer", float: "number", bool: "boolean"}
        schemas: List[dict] = []
        for key in self.names():
            func = self.tools[key]
            # Resolve annotations to real types: `from __future__ import annotations`
            # turns them into strings, which would make every parameter a "string".
            try:
                hints = typing.get_type_hints(func)
            except Exception:
                hints = {}
            props: Dict[str, dict] = {}
            required: List[str] = []
            for pname, param in inspect.signature(func).parameters.items():
                props[pname] = {"type": kinds.get(hints.get(pname), "string")}
                if param.default is inspect.Parameter.empty:
                    required.append(pname)
            schemas.append({
                "type": "function",
                "function": {
                    "name": key,
                    "description": self.descriptions.get(key, ""),
                    "parameters": {"type": "object", "properties": props, "required": required},
                },
            })
        return schemas

    def has(self, name: str) -> bool:
        return name in self.tools

    def __contains__(self, name: str) -> bool:
        return name in self.tools

    def __len__(self) -> int:
        return len(self.tools)


if __name__ == "__main__":
    registry = ToolRegistry()

    @registry.register(description="drive forward")
    def forward():
        return "forward"

    @registry.register
    def wsB(speed: int) -> int:
        """set speed"""
        return int(speed)

    print(registry.names())
    print(registry.call("forward"))
    print(registry.call("wsB", 50))
    print(registry.has("fly"))
    print(json.dumps(registry.get_schemas(), indent=2))


registry = ToolRegistry()
