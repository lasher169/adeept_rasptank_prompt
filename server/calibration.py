"""Servo zero positions, stored as data instead of patched into source.

Historically the robot "saved" calibration by rewriting `init_pwmN = ...`
lines inside RPIservo.py at runtime (`replace_num` / `num_import_int`, three
copies of it across the repo). That made the running program edit its own
source, and any crash mid-write corrupted the code. Positions now live in
`server/calibration.json`.

    from calibration import get, set
    set(3, 320)          # persists to calibration.json
    get(3)               # -> 320
"""

from __future__ import annotations

import json
import os
import threading
from typing import Dict

NUM_CHANNELS = 16
DEFAULT_POS = 300
PATH = os.environ.get("CALIBRATION_FILE",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibration.json"))

_lock = threading.Lock()
_cache: Dict[int, int] | None = None


def _read() -> Dict[int, int]:
    try:
        with open(PATH) as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return {i: DEFAULT_POS for i in range(NUM_CHANNELS)}
    return {
        int(channel): int(raw.get(str(channel), DEFAULT_POS))
        for channel in range(NUM_CHANNELS)
    }


def load() -> Dict[int, int]:
    """Servo zero positions, channel -> pwm ticks. Cached after first read."""
    global _cache
    with _lock:
        if _cache is None:
            _cache = _read()
        return dict(_cache)


def get(channel: int) -> int:
    return load()[channel]


def set(channel: int, value: int) -> int:
    """Persist one channel's zero position. Returns the stored value."""
    channel = int(channel)
    value = int(value)
    if not 0 <= channel < NUM_CHANNELS:
        raise ValueError(f"servo channel must be 0..{NUM_CHANNELS - 1}, got {channel}")
    if not 100 <= value <= 560:
        raise ValueError(f"pwm ticks must be 100..560, got {value}")
    with _lock:
        if _cache is None:
            _cache = _read()
        _cache[channel] = value
        try:
            with open(PATH, "w") as fh:
                json.dump({str(k): v for k, v in _cache.items()}, fh, indent=2)
        except OSError as exc:
            print(f"could not save calibration: {exc}")
    return value


def reset() -> Dict[int, int]:
    """Return every channel to the factory zero."""
    with _lock:
        _cache = {i: DEFAULT_POS for i in range(NUM_CHANNELS)}
        try:
            with open(PATH, "w") as fh:
                json.dump({str(k): v for k, v in _cache.items()}, fh, indent=2)
        except OSError as exc:
            print(f"could not save calibration: {exc}")
    return dict(_cache)


if __name__ == "__main__":
    print(load())
