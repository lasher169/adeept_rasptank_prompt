"""Behaviour loops: line following, obstacle avoidance, steady balancing, radar scan.

Everything shares the single PCA9685 handle and ServoCtrl from RPIservo. This
module used to open its own board, re-read `init_pwmN = ` literals out of
RPIservo.py's source, and reference an `sensor` variable that was never
defined (the MPU import was commented out) — so `steady` mode raised
NameError in the thread.
"""

from __future__ import annotations

import threading
import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None
try:
    from mpu6050 import mpu6050
except ImportError:
    mpu6050 = None

import Kalman_filter
import move
import ultra
import RPIservo

LINE_PIN_RIGHT = 19
LINE_PIN_MIDDLE = 16
LINE_PIN_LEFT = 20

kalman_filter_X = Kalman_filter.Kalman_filter(0.01, 0.1)


def setup() -> None:
    """Configure the line-following sensor pins."""
    if GPIO is None:
        return
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    for pin in (LINE_PIN_RIGHT, LINE_PIN_MIDDLE, LINE_PIN_LEFT):
        GPIO.setup(pin, GPIO.IN)


class Functions(threading.Thread):
    """A thread that runs whichever autonomous mode was last selected."""

    def __init__(self, *args, **kwargs):
        self.functionMode = "none"
        self.steadyGoal = 0
        self.rangeKeep = 0.7
        self.servo = RPIservo.servo()
        self.sensor = mpu6050(0x68) if mpu6050 else None

        setup()
        super().__init__(*args, **kwargs)
        self._flag = threading.Event()
        self._flag.clear()

    def radarScan(self) -> list:
        """Sweep servo 1 across 180 degrees and return [distance, angle] samples."""
        result = []
        self.servo.moveAngle(1, 180)
        time.sleep(0.8)
        for angle in range(180, -1, 3):
            self.servo.moveAngle(1, angle)
            dist = ultra.checkdist()
            if dist > 20:
                continue
            result.append([dist, angle])
        self.servo.moveAngle(1, 0)
        return result

    def pause(self) -> None:
        self.functionMode = "none"
        move.move(80, "no", "no", 0.5)
        self._flag.clear()

    def resume(self) -> None:
        self._flag.set()

    def automatic(self) -> None:
        self.functionMode = "Automatic"
        self.resume()

    def trackLine(self) -> None:
        self.functionMode = "trackLine"
        self.resume()

    def steady(self, goalPos: int) -> None:
        self.functionMode = "Steady"
        self.steadyGoal = goalPos
        self.resume()

    def trackLineProcessing(self) -> None:
        right, middle, left = (GPIO.input(p) for p in (LINE_PIN_RIGHT, LINE_PIN_MIDDLE, LINE_PIN_LEFT))
        if middle == 1:
            move.move(100, "forward", "no", 1)
        elif left == 1:
            move.move(100, "no", "right", 1)
        elif right == 1:
            move.move(100, "no", "left", 1)
        else:
            move.move(100, "backward", "no", 1)
        time.sleep(0.1)

    def automaticProcessing(self) -> None:
        distance = ultra.checkdist()
        if self.rangeKeep / 3 > distance:
            move.move(100, "backward", "no", 0.5)
        elif self.rangeKeep > distance:
            move.move(100, "no", "left", 0.5)
        else:
            move.move(100, "forward", "no", 0.5)
        time.sleep(0.1)

    def steadyProcessing(self) -> None:
        if self.sensor is None:
            self.pause()
            return
        tilt = self.sensor.get_accel_data()["x"]
        angle = kalman_filter_X.kalman(tilt * 9)
        self.servo.moveAngle(2, self.steadyGoal + int(round(angle)))
        time.sleep(0.05)

    def functionGoing(self) -> None:
        if self.functionMode == "Automatic":
            self.automaticProcessing()
        elif self.functionMode == "Steady":
            self.steadyProcessing()
        elif self.functionMode == "trackLine":
            self.trackLineProcessing()
        else:
            self.pause()

    def run(self) -> None:
        while True:
            self._flag.wait()
            self.functionGoing()


if __name__ == "__main__":
    print("modes: trackLine, automatic, steady, radarScan")
