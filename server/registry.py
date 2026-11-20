"""A minimal tool registry.

Tools are just name -> function. Register them, look them up, call them.

    registry = ToolRegistry()
    registry.register("forward", drive_forward, description="drive forward")
    registry.call("forward")
"""

import json
import json
from typing import Any, Callable, Dict, List
import inspect


class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.descriptions: Dict[str, str] = {}

    def register(self, func=None, name: str = None, description: str = None):
        """Add a tool. Works bare (@registry.register) or with args. Re-registering replaces."""
        def deco(f):
            key = name or f.__name__
            self.tools[key] = f
            self.descriptions[key] = description or inspect.getdoc(f) or ''
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
        schemas = []
        for key in self.names():
            func = self.tools[key]
            props, required = {}, []
            for pname, param in inspect.signature(func).parameters.items():
                kind = {str: 'string', int: 'integer',
                        float: 'number', bool: 'boolean'}.get(param.annotation, 'string')
                props[pname] = {'type': kind}
                if param.default is inspect.Parameter.empty:
                    required.append(pname)
            schemas.append({'type': 'function', 'function': {
                'name': key,
                'description': self.descriptions.get(key, ''),
                'parameters': {'type': 'object',
                    'properties': props,
                    'required': required},
            }})
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
