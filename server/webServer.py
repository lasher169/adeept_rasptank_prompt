#!/usr/bin/env python3
"""RaspTank entry point.

One process, two servers:
  - Flask (webserver/app.py)  : FPV video, static front-end, /health, /prompt
  - WebSocket (this file)     : the joystick/serial-control commands the UI sends

Run:  python3 webServer.py
The WebSocket port is 8000; set WS_PASSWORD to require the "admin" handshake.

Commands the front-end can send (all JSON):
  wsA/wsB  P_servo/T_servo + angle        aim the two camera servos
  wsC      PWMD/SiLeft/SiRight/SiDown     nudge a servo zero
  wsD      PWMINIT/P_servo                save a servo zero (calibration.json)
  wsE      mode                           camera mode: none|watchDog|findColor|findlineCV
  wsF      H,S,V                          colour target for findColor
  wsG      automatic/trackLine/none       autonomous mode
  wsK      'yes'|'no'                    radar scan
  wsM      direction, turn, speed         drive
  wsN      'on'|'off'                    NeoPixel
  wsO      mode, port                     HAT port 1-3 on/off
  wsP      'yes'|'no'                    stop everything
  wsQ      1|2|3|4                        ultrasonic which sensor
  wsR      'yes'|'no'                    report distance
  wsS      'yes'|'no'                    report IP
  wsT      initPos, goalPos, autoTime, scSpeed, initAngle, goalAngle   raw servo move
  wsU      0/1 cameraDiagonalW/H, CameraMode, findColorSet
  wsV      'yes'|'no'                    print current servo positions
  wsW      mode                           camera mode (serial-control path)
  wsX      'yes'                          ultrasonic distance
  wsY      'yes'                         what revision is running (no self-overwrite)
  wsZ      'yes'|'no'                    reset camera/servo state
  prompt   text                           send to the LLM agent
"""

from __future__ import annotations

import asyncio
import json
import socket
import sys
import threading
import time

import websockets

import info
import move
import RPIservo
import robotLight
import switch
from calibration import load, set as set_zero, get as get_zero

from webserver import tools  # noqa: F401 - importing registers the agent tools
from webserver.app import camera, set_camera_mode, set_color_find, start
from webserver.config import env
from webserver.prompts import submit

import camera_opencv
import functions

WS_PORT = int(env("WS_PORT", 8000))
WS_PASSWORD = env("WS_PASSWORD", "123456")

servo = RPIservo.servo()
RL = robotLight.RobotLight()
RL.start()
fuc = functions.Functions()
fuc.start()

try:
    import OLED
    screen = OLED.OLED_CTRL()
    screen.show("Adeept Car")
except ImportError:
    screen = None
except Exception as exc:
    print("OLED unavailable:", exc)
    screen = None


def log(message: str) -> None:
    print(message)
    if screen:
        screen.show(message[:16])


def current_ip() -> str:
    """Best-effort local IP, without opening a socket to the internet."""
    try:
        hostname = socket.gethostbyname(socket.gethostname())
        if hostname.startswith("127.") and env("GET_EXTERNAL_IP"):
            return "127.0.0.1"
        return hostname
    except OSError:
        return "127.0.0.1"


def check_permit(data: dict) -> bool:
    """The UI sends {"admin": "..."} for privileged commands."""
    return data.get("admin") in (None, WS_PASSWORD)


def stop_everything() -> None:
    move.motorStop()
    fuc.pause()
    set_camera_mode("none")
    servo.stopWiggle()


def report_position() -> str:
    cal = load()
    return json.dumps({str(ch): cal[ch] for ch in range(RPIservo.NUM_CHANNELS)})


def revision() -> str:
    """What code is running. Used to be `git reset --hard origin/master; reboot`
    on a button press, which silently discarded local work and restarted the Pi.
    """
    import subprocess
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    except Exception as exc:
        return f"unknown ({exc})"


async def handler(websocket, message: str) -> None:
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        await websocket.send(json.dumps({"status": "bad json"}))
        return

    command = data.get("command", "")
    reply = {"command": command, "status": "ok"}

    try:
        if command in ("wsA", "wsB"):
            servo.moveAngle(int(data["P_servo"]), int(data["angle"]))
        elif command == "wsC":
            PWM = get_zero(int(data["P_servo"]))
            if data["SiLeft"] == 1:
                PWM += int(data["PWMD"])
            elif data["SiRight"] == 1:
                PWM -= int(data["PWMD"])
            elif data["SiDown"] == 1:
                PWM -= int(data["PWMD"])
            PWM = max(RPIservo.CTRL_RANGE_MIN, min(RPIservo.CTRL_RANGE_MAX, PWM))
            set_zero(int(data["P_servo"]), PWM)
            servo.moveCert(int(data["P_servo"]), PWM)
        elif command == "wsD":
            set_zero(int(data["P_servo"]), int(data["PWMINIT"]))
            servo.moveCert(int(data["P_servo"]), int(data["PWMINIT"]))
            log("saved servo %s zero" % data["P_servo"])
        elif command in ("wsE", "wsW"):
            set_camera_mode(data["mode"])
        elif command == "wsF":
            set_color_find(int(data["H"]), int(data["S"]), int(data["V"]))
            log("colour target %s %s %s" % (data["H"], data["S"], data["V"]))
        elif command == "wsG":
            if data["mode"] == "automatic":
                fuc.automatic()
            elif data["mode"] == "trackLine":
                fuc.trackLine()
            else:
                fuc.pause()
        elif command == "wsK":
            if data["scan"] == "yes":
                fuc.radarScan()
            else:
                fuc.pause()
        elif command == "wsM":
            move.move(int(data["speed"]), data["direction"], data["turn"], 0.6)
        elif command == "wsN":
            if data["light"] == "on":
                RL.setColor(10, 10, 10)
                RL.start()
            else:
                RL.stop()
        elif command == "wsO":
            if data["mode"] == "on":
                switch.switch(int(data["port"]), 1)
            else:
                switch.switch(int(data["port"]), 0)
        elif command == "wsP":
            stop_everything()
        elif command == "wsQ":
            info.Sensor_Selection = int(data["selection"])
        elif command == "wsR":
            log("distance %s cm" % info.checkdist())
        elif command == "wsS":
            log(current_ip())
        elif command == "wsT":
            servo.initConfig(int(data["initAngle"]), int(data["goalAngle"]))
            servo.moveAuto()
        elif command == "wsU":
            cam = camera()
            if data["cameraDiagonalW"] == 1:
                cam.cameraDiagonalW = 640
            elif data["cameraDiagonalW"] == 2:
                cam.cameraDiagonalW = 480
            if data["cameraDiagonalH"] == 1:
                cam.cameraDiagonalH = 480
            elif data["cameraDiagonalH"] == 2:
                cam.cameraDiagonalH = 360
            set_camera_mode(data["CameraMode"])
            if data.get("findColorSet"):
                set_color_find(int(data["H"]), int(data["S"]), int(data["V"]))
        elif command == "wsV":
            log(report_position())
        elif command == "wsX":
            log("distance %s cm" % info.checkdist())
        elif command == "wsY":
            log("revision %s" % revision())
        elif command == "wsZ":
            set_camera_mode("none")
        elif command == "prompt":
            result = submit(data.get("text", ""))
            reply.update(result)
            log(result.get("reply", result.get("error", ""))[:16])
        else:
            reply["status"] = "unknown command: %s" % command
    except Exception as exc:
        reply["status"] = f"error: {exc}"

    await websocket.send(json.dumps(reply))


async def main() -> None:
    start()
    async with websockets.serve(handler, "0.0.0.0", WS_PORT):
        print(f"WebSocket listening on 0.0.0.0:{WS_PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("shutting down")
