#!/usr/bin/env python3
"""Servo control for the 16-channel PCA9685 driver board.

`ServoCtrl` is a thread that moves servos smoothly (interpolated "auto" mode,
constant-speed "certain" mode, or continuous "wiggle" for scanning). The PCA9685
handle is created lazily so this module can be imported — and tested — without
the hardware attached.

    from RPIservo import ServoCtrl
    servo = ServoCtrl()
    servo.start()
    servo.moveAngle(11, 40)        # channel 11 to 40 degrees from its zero
    servo.singleServo(14, -1, 3)   # sweep channel 14
    servo.stopWiggle()

There is one shared PCA9685, so create ONE ServoCtrl for the whole program.
The old code created six (scGear, P_sc, T_sc, H1_sc, H2_sc, G_sc), each with its
own 16-channel position table writing to the same board.
"""

from __future__ import annotations

import threading
import time
from typing import List, Sequence

from calibration import load

NUM_CHANNELS = 16
CTRL_RANGE_MAX = 560
CTRL_RANGE_MIN = 100
ANGLE_RANGE = 180
PWM_FREQ = 50

try:
    import Adafruit_PCA9685
except ImportError:          # allows import/test off the Pi
    Adafruit_PCA9685 = None

_board = None


def board():
    """The shared PCA9685 handle, opened on first use."""
    global _board
    if _board is None:
        if Adafruit_PCA9685 is None:
            raise RuntimeError("Adafruit_PCA9685 is not installed; servo control is unavailable")
        _board = Adafruit_PCA9685.PCA9685(busnum=1)
        _board.set_pwm_freq(PWM_FREQ)
    return _board


def pwm_set(channel: int, ticks: int) -> None:
    """Write one channel, clamped to the safe pulse range."""
    channel = max(0, min(NUM_CHANNELS - 1, int(channel)))
    ticks = int(max(CTRL_RANGE_MIN, min(CTRL_RANGE_MAX, ticks)))
    board().set_pwm(channel, 0, ticks)


def pwm_from_angle(angle: float) -> int:
    """Degrees of servo travel -> pwm ticks."""
    return int(round((CTRL_RANGE_MAX - CTRL_RANGE_MIN) / ANGLE_RANGE * angle))


class ServoCtrl(threading.Thread):
    """Smoothly drives all 16 channels from a single PCA9685."""

    def __init__(self, *args, **kwargs):
        init_pos = load()

        self.sc_direction = [1] * NUM_CHANNELS
        self.initPos = [init_pos[i] for i in range(NUM_CHANNELS)]
        self.goalPos = [300] * NUM_CHANNELS
        self.nowPos = [300] * NUM_CHANNELS
        self.bufferPos = [300.0] * NUM_CHANNELS
        self.lastPos = [300] * NUM_CHANNELS
        self.ingGoal = [300] * NUM_CHANNELS
        self.maxPos = [CTRL_RANGE_MAX] * NUM_CHANNELS
        self.minPos = [CTRL_RANGE_MIN] * NUM_CHANNELS
        self.scSpeed = [0] * NUM_CHANNELS

        self.scMode = 'auto'
        self.scTime = 2.0
        self.scSteps = 30
        self.scDelay = 0.037
        self.scMoveTime = 0.037

        self.goalUpdate = 0
        self.wiggleID = 0
        self.wiggleDirection = 1

        super().__init__(*args, **kwargs)
        self.__flag = threading.Event()
        self.__flag.clear()

    def pwmGenOut(self, angleInput: float) -> int:
        return pwm_from_angle(angleInput)

    def pause(self) -> None:
        self.__flag.clear()

    def resume(self) -> None:
        self.__flag.set()

    def _apply(self, channel: int, position) -> None:
        self.nowPos[channel] = position
        pwm_set(channel, position)

    def moveInit(self) -> None:
        """Return every servo to its zero position."""
        self.scMode = 'init'
        for i in range(NUM_CHANNELS):
            pwm_set(i, self.initPos[i])
            self.lastPos[i] = self.initPos[i]
            self.nowPos[i] = self.initPos[i]
            self.bufferPos[i] = float(self.initPos[i])
            self.goalPos[i] = self.initPos[i]
        self.pause()

    def initConfig(self, channel: int, initInput: int, moveTo: bool = True) -> None:
        """Set a servo's zero and persist it to calibration.json."""
        if self.minPos[channel] < initInput < self.maxPos[channel]:
            self.initPos[channel] = int(initInput)
            try:
                from calibration import set as save_channel
                save_channel(channel, self.initPos[channel])
            except ValueError as exc:
                print(exc)
            if moveTo:
                pwm_set(channel, self.initPos[channel])
        else:
            print('initPos value error: %s out of range' % initInput)

    def moveServoInit(self, channels: Sequence[int]) -> None:
        """Home the given channels to their zero positions."""
        self.scMode = 'init'
        for channel in channels:
            pwm_set(channel, self.initPos[channel])
            self.lastPos[channel] = self.initPos[channel]
            self.nowPos[channel] = self.initPos[channel]
            self.bufferPos[channel] = float(self.initPos[channel])
            self.goalPos[channel] = self.initPos[channel]
        self.pause()

    def posUpdate(self) -> None:
        self.goalUpdate = 1
        self.lastPos = list(self.nowPos)
        self.goalUpdate = 0

    def speedUpdate(self, channels: Sequence[int], speeds: Sequence[int]) -> None:
        for channel, speed in zip(channels, speeds):
            self.scSpeed[channel] = speed

    def _clamp_goal(self, channel: int, angle: float) -> int:
        goal = self.initPos[channel] + self.pwmGenOut(angle) * self.sc_direction[channel]
        return max(self.minPos[channel], min(self.maxPos[channel], goal))

    def moveAuto(self) -> int:
        for i in range(NUM_CHANNELS):
            self.ingGoal[i] = self.goalPos[i]

        for step in range(1, self.scSteps + 1):
            for channel in range(NUM_CHANNELS):
                if not self.goalUpdate:
                    target = self.lastPos[channel] + (self.goalPos[channel] - self.lastPos[channel]) / self.scSteps * step
                    self._apply(channel, int(round(target)))
                if self.ingGoal != self.goalPos:
                    self.posUpdate()
                    time.sleep(self.scTime / self.scSteps)
                    return 1
            time.sleep(self.scTime / self.scSteps - self.scMoveTime)

        self.posUpdate()
        self.pause()
        return 0

    def moveCert(self) -> int:
        for i in range(NUM_CHANNELS):
            self.ingGoal[i] = self.goalPos[i]
            self.bufferPos[i] = self.lastPos[i]

        while self.nowPos != self.goalPos:
            for channel in range(NUM_CHANNELS):
                if self.lastPos[channel] < self.goalPos[channel]:
                    self.bufferPos[channel] += self.pwmGenOut(self.scSpeed[channel]) / (1 / self.scDelay)
                    new_now = min(int(round(self.bufferPos[channel])), self.goalPos[channel])
                elif self.lastPos[channel] > self.goalPos[channel]:
                    self.bufferPos[channel] -= self.pwmGenOut(self.scSpeed[channel]) / (1 / self.scDelay)
                    new_now = max(int(round(self.bufferPos[channel])), self.goalPos[channel])
                else:
                    new_now = self.nowPos[channel]

                self.nowPos[channel] = new_now
                if not self.goalUpdate:
                    pwm_set(channel, new_now)

                if self.ingGoal != self.goalPos:
                    self.posUpdate()
                    return 1
            self.posUpdate()
            time.sleep(self.scDelay - self.scMoveTime)

        self.pause()
        return 0

    def moveWiggle(self) -> None:
        channel = self.wiggleID
        self.bufferPos[channel] += (
            self.wiggleDirection * self.sc_direction[channel]
            * self.pwmGenOut(self.scSpeed[channel]) / (1 / self.scDelay)
        )
        self.bufferPos[channel] = max(self.minPos[channel], min(self.maxPos[channel], self.bufferPos[channel]))
        self.nowPos[channel] = self.lastPos[channel] = int(round(self.bufferPos[channel]))

        if self.minPos[channel] < self.bufferPos[channel] < self.maxPos[channel]:
            pwm_set(channel, self.nowPos[channel])
        else:
            self.stopWiggle()
            return
        time.sleep(self.scDelay - self.scMoveTime)

    def stopWiggle(self) -> None:
        self.pause()
        self.posUpdate()

    def singleServo(self, channel: int, direction: int, speed: int) -> None:
        self.wiggleID = channel
        self.wiggleDirection = direction
        self.scSpeed[channel] = speed
        self.scMode = 'wiggle'
        self.posUpdate()
        self.resume()

    def moveAngle(self, channel: int, angleInput: float) -> None:
        position = int(self.initPos[channel] + self.sc_direction[channel] * self.pwmGenOut(angleInput))
        self.nowPos[channel] = max(self.minPos[channel], min(self.maxPos[channel], position))
        self.lastPos[channel] = self.nowPos[channel]
        pwm_set(channel, self.nowPos[channel])

    def autoSpeed(self, channels: Sequence[int], angles: Sequence[float]) -> None:
        self.scMode = 'auto'
        self.goalUpdate = 1
        for channel, angle in zip(channels, angles):
            self.goalPos[channel] = self._clamp_goal(channel, angle)
        self.goalUpdate = 0
        self.resume()

    def certSpeed(self, channels: Sequence[int], angles: Sequence[float], speeds: Sequence[int]) -> None:
        self.scMode = 'certain'
        self.goalUpdate = 1
        for channel, angle in zip(channels, angles):
            self.goalPos[channel] = self._clamp_goal(channel, angle)
        self.speedUpdate(channels, speeds)
        self.goalUpdate = 0
        self.resume()

    def setAutoTime(self, autoSpeedSet: float) -> None:
        self.scTime = autoSpeedSet

    def setDelay(self, delaySet: float) -> None:
        self.scDelay = delaySet

    def setPWM(self, channel: int, pwm_input: int) -> None:
        self.lastPos[channel] = self.nowPos[channel] = pwm_input
        self.bufferPos[channel] = float(pwm_input)
        self.goalPos[channel] = pwm_input
        pwm_set(channel, pwm_input)
        self.pause()

    def scMove(self) -> None:
        if self.scMode == 'init':
            self.moveInit()
        elif self.scMode == 'auto':
            self.moveAuto()
        elif self.scMode == 'certain':
            self.moveCert()
        elif self.scMode == 'wiggle':
            self.moveWiggle()

    def run(self) -> None:
        while True:
            self.__flag.wait()
            self.scMove()


_servo: ServoCtrl | None = None


def servo() -> ServoCtrl:
    """The one shared ServoCtrl.

    webServer.py used to create six (scGear, P_sc, T_sc, H1_sc, H2_sc, G_sc),
    each with its own 16-channel position table, all writing to the same board.
    A single instance keeps the position bookkeeping consistent.
    """
    global _servo
    if _servo is None:
        _servo = ServoCtrl()
        _servo.start()
    return _servo


if __name__ == '__main__':
    import random
    servo = ServoCtrl()
    servo.start()
    while True:
        servo.moveAngle(0, random.random() * 100 - 50)
        time.sleep(1)
        servo.moveAngle(1, random.random() * 100 - 50)
        time.sleep(1)
