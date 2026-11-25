"""Hardware tools the agent can call.

Importing this module registers every tool. webServer.py imports it, which is new:
previously nothing imported tools.py, so the registry stayed empty and the LLM
was sent an empty `tools` list — the agent layer was wired up but inert.

    from webserver.tools import registry
    registry.names()            # ['drive', 'set_camera_mode', ...]
    registry.call("drive", "forward")
"""

from __future__ import annotations

from typing import Optional

from webserver.registry import registry

# Guarded so the registry is importable off the Pi, where GPIO/picamera are
# missing. Tools raise a clear RuntimeError instead of an ImportError at import.
try:
    import move
except ImportError:
    move = None
try:
    import RPIservo
except ImportError:
    RPIservo = None
try:
    import switch
except ImportError:
    switch = None
try:
    import ultra
except ImportError:
    ultra = None

DIRECTIONS = ("forward", "backward", "no")
TURNS = ("no", "left", "right")
CAMERA_MODES = ("none", "watchDog", "findColor", "findlineCV")


def _require(module, name: str):
    if module is None:
        raise RuntimeError(f"{name} is unavailable (hardware not attached)")
    return module


def _clamp(value: int, low: int, high: int, label: str) -> int:
    value = int(value)
    if not low <= value <= high:
        raise ValueError(f"{label} must be {low}..{high}, got {value}")
    return value


@registry.register
def drive(direction: str, turn: str = "no", speed: int = 100) -> str:
    """Drive the tank.

    direction: forward | backward | no
    turn:      no | left | right
    speed:     0-100
    """
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS}, got {direction!r}")
    if turn not in TURNS:
        raise ValueError(f"turn must be one of {TURNS}, got {turn!r}")
    speed = _clamp(speed, 0, 100, "speed")

    move = _require(move, "move")
    move.setup()
    move.move(speed, direction, turn, 0.6)
    return f"moving {direction} turn {turn} at {speed}"


@registry.register
def stop_motors() -> str:
    """Stop the drive motors."""
    _require(move, "move").motorStop()
    return "motors stopped"


@registry.register
def set_camera_mode(mode: str) -> str:
    """Choose OpenCV processing on the video stream: none | watchDog | findColor | findlineCV."""
    if mode not in CAMERA_MODES:
        raise ValueError(f"mode must be one of {CAMERA_MODES}, got {mode!r}")
    from camera_opencv import Camera
    Camera.modeSelect = mode
    return f"camera mode {mode}"


@registry.register
def set_color_target(h: int, s: int, v: int) -> str:
    """Set the HSV target for findColor mode (h 0-180, s 0-255, v 0-255)."""
    h = _clamp(h, 0, 180, "h")
    s = _clamp(s, 0, 255, "s")
    v = _clamp(v, 0, 255, "v")
    from camera_opencv import Camera
    Camera().colorFindSet(h, s, v)
    return f"color target set to ({h}, {s}, {v})"


@registry.register
def move_servo(channel: int, angle: int) -> str:
    """Move one servo `angle` degrees from its zero (negative = other direction)."""
    channel = _clamp(channel, 0, 15, "channel")
    angle = _clamp(angle, -180, 180, "angle")
    servo = _require(RPIservo, "RPIservo").servo()
    servo.moveAngle(channel, angle)
    return f"servo {channel} to {angle} degrees"


@registry.register
def read_distance() -> Optional[float]:
    """Distance to the nearest obstacle in metres, from the ultrasonic sensor."""
    ultrasonic = _require(ultra, "ultra")
    return ultrasonic.checkdist()


@registry.register
def switch_port(port: int, on: bool) -> str:
    """Switch one of the three HAT ports on or off (port 1-3)."""
    port = _clamp(port, 1, 3, "port")
    _require(switch, "switch").switch(port, 1 if on else 0)
    return f"port {port} {'on' if on else 'off'}"


if __name__ == "__main__":
    import json
    print(json.dumps(registry.names(), indent=2))
    print(json.dumps(registry.get_schemas(), indent=2))
