"""Hardware tools the agent can call.

Importing this module registers every tool into ``webserver.registry.registry``.
The docstring of each function is the description the LLM sees.

    from webserver import tools
    registry.call("start_moving_and_start_camera", "forward")
"""

try:                       # server/ is the working directory, like webServer.py
    from registry import registry
except ImportError:        # imported as a package module
    from .registry import registry

# move.py and camera_opencv.py sit next to webServer.py in server/. Guarded so
# the registry can be imported off the Pi, where GPIO/picamera are missing.
try:
    import move
    from camera_opencv import Camera
except ImportError:
    move = None
    Camera = None

DIRECTIONS = ("forward", "backward", "no")
TURNS = ("no", "left", "right")
CAMERA_MODES = ("none", "watchDog", "findColor", "findlineCV")


@registry.register
def start_moving_and_start_camera(
    direction: str, 
    turn: str = "no",
    speed: int = 100,
    camera_mode: str = "watchDog") -> str:
    """Drive the tank and turn the camera's vision loop on.

    direction: forward | backward | no
    turn:      no | left | right
    speed:     0-100
    camera_mode: none | watchDog | findColor | findlineCV
    """
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS}, got {direction!r}")
    if turn not in TURNS:
        raise ValueError(f"turn must be one of {TURNS}, got {turn!r}")
    if camera_mode not in CAMERA_MODES:
        raise ValueError(f"camera_mode must be one of {CAMERA_MODES}, got {camera_mode!r}")
    if move is None:
        raise RuntimeError("move.py is not importable; run from the server/ directory")

    move.setup()
    move.move(int(speed), direction, turn, 0.6)

    if Camera is None:
        camera_state = "camera unavailable"
    else:
        Camera.modeSelect = camera_mode
        camera_state = f"camera mode {camera_mode}"

    return f"moving {direction} turn {turn} at {speed}; {camera_state}"


if __name__ == "__main__":
    for name in registry.names():
        print(f"{name}: {registry.descriptions.get(name, '')}")
