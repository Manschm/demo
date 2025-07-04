"""
Simple game logic implementation for a 4‑sensor “energy” game.

Hardware abstraction layer
--------------------------
All hardware specific operations are wrapped into *stub* functions at the
top of the file.  Replace their bodies with the real implementation that
talks to your sensors / LEDs / buttons / GUI / wind‑turbine.

Game overview
-------------
* 4 active‑LOW sensor signals, each with an RGB LED (red = 0, green = 1)
* 2 user push‑buttons (charge / discharge) with integrated LEDs
* A wind‑turbine that should spin “from time to time” (here: after every
  completed user action – tweak as you wish)
* 4‑digit score display
* 10‑segment state‑of‑charge (SoC) display

Rules (short version)
---------------------
* Idle state – everything dark, last score shown.
* Pressing either button starts a new game (max 10 actions).
* At the start (and after every action) each LED is randomly assigned 0/1.
* As soon as **any** sensor goes LOW → both button LEDs turn ON.
* The user can press **one** button while at least one sensor is LOW.
* Scoring depends on
    – the current LED value (0 / 1) of *that* sensor, and
    – which button was pressed (charge / discharge).
* Same sensor may be used again after ≥ 1 s.
* Switching to a *different* sensor costs one extra SoC level.
* After 10 actions the round ends and the game returns to idle.
* During the game a ≥ 3 s simultaneous press of *both* buttons resets
  everything immediately.

This implementation keeps the logic completely hardware‑agnostic.
"""
from __future__ import annotations

import random
import time
from typing import List, Optional, Dict
from led_controller import init_leds, g1, g2, g3, g4, r1, r2, r3, r4, off1, off2, off3, off4, cleanup #todo install
import gpiozero #todo install
from gui import ScoreGUI

# --------------------------------------------------------------------------- #
#                         ‑‑‑ Hardware Abstraction ‑‑‑                        #
# --------------------------------------------------------------------------- #

NUM_SENSORS   = 4
SOC_LEVELS    = 10
MAX_ACTIONS   = 10
BUTTONS       = ("charge", "discharge")
LED_COLOR     = {0: "red", 1: "green"}      # convenience mapping

# Initialize the GPIO pins for the sensors, buttons, LEDs, and windmill
btn_charge = gpiozero.Button(2, bounce_time=0.5)
btn_discharge = gpiozero.Button(3, bounce_time=0.5)
park_office = gpiozero.Button(4, bounce_time=0.5)
park_home = gpiozero.Button(17, bounce_time=0.5)
park_shop = gpiozero.Button(27, bounce_time=0.5)
park_charge = gpiozero.Button(22, bounce_time=0.5)
windmill = gpiozero.Servo(12, min_pulse_width=0.00149, max_pulse_width=0.0015)  # Adjust as needed
led_charge = gpiozero.LED(10)
led_discharge = gpiozero.LED(11)

if not init_leds(physical_leds=4):
    print("LED initialization failed. Exiting.")


# ---------- Replace the following stubs with real I/O code ---------- #

def read_sensor(index: int) -> bool:
    """Return *True* when the sensor line *index* is LOW (active)."""
    if index == 0:
        return park_office.is_pressed
    elif index == 1:
        return park_home.is_pressed
    elif index == 2:
        return park_shop.is_pressed
    elif index == 3:
        return park_charge.is_pressed


def set_led(index: int, color: str, on: bool = True) -> None:
    """Drive the RGB LED that belongs to *sensor index*."""
    if index == 0:
        off1()
    elif index == 1:
        off2()
    elif index == 2:
        off3()
    elif index == 3:
        off4()
    else:
        raise ValueError(f"Invalid sensor index: {index}")
    
    if on:
        if color == "red":
            if index == 0:
                r1()
            elif index == 1:
                r2()
            elif index == 2:
                r3()
            elif index == 3:
                r4()
            else:
                raise ValueError(f"Invalid sensor index: {index}")
        elif color == "green":
            if index == 0:
                g1()
            elif index == 1:
                g2()
            elif index == 2:
                g3()
            elif index == 3:
                g4()
            else:
                raise ValueError(f"Invalid sensor index: {index}")


def read_button(name: str) -> bool:
    """Return *True* while the named button is pressed."""
    if name == "charge":
        return btn_charge.is_pressed
    elif name == "discharge":
        return btn_discharge.is_pressed


def set_button_led(name: str, on: bool) -> None:
    """Turn the integrated LED of a button on/off."""
    if name == "charge":
        if on:
            led_charge.on()
            display.highlight_laden(active=True)
        else:
            led_charge.off()
            display.highlight_laden(active=False)
    elif name == "discharge":
        if on:
            led_discharge.on()
            display.highlight_entladen(active=True)
        else:
            led_discharge.off()
            display.highlight_entladen(active=False)


def set_windmill(on: bool) -> None:
    """Spin (True) or stop (False) the miniature wind‑turbine."""
    if on:
        windmill.max()
    else:
        windmill.detach()  # stop spinning


def update_score_display(score: int) -> None:
    """Update the 4‑digit 7‑segment display (0000 … 9999)."""
    display.set_score(score)


def update_soc_display(level: int) -> None:
    """Show a level between 0 and 10 on the SoC bar graph."""
    display.set_soc(level)


# --------------------------------------------------------------------------- #
#                               ‑‑‑  Game  ‑‑‑                               #
# --------------------------------------------------------------------------- #

# How many SoC levels are gained for sensors 0‑3 when “charging”.
SOC_INCREMENT = (2, 3, 4, 2)          # tweak freely


class Game:
    """
    Encapsulates one full game loop (idle <‑‑> play).
    A *Game* object can be re‑used indefinitely.
    """

    # -------------------------------- Idle -------------------------------- #

    def idle(self) -> None:
        """Idle loop — waits for any button press and keeps the last score."""
        # Darken everything
        for idx in range(NUM_SENSORS):
            set_led(idx, "off", on=False)
        set_button_led("charge", False)
        set_button_led("discharge", False)
        set_windmill(False)

        update_score_display(self.score)          # show last score once more

        # Block here until a button is pressed
        while True:
            if read_button("charge") or read_button("discharge"):
                # debounce
                while read_button("charge") or read_button("discharge"):
                    time.sleep(0.01)
                self._start_new_round()
                return
            time.sleep(0.02)

    # ------------------------------- Playing ------------------------------ #

    def _start_new_round(self) -> None:
        self.actions             = 0
        self.soc                 = SOC_LEVELS // 2         # arbitrary start
        self.last_sensor         = None                    # last active index
        self.last_action_ts      = [0.0] * NUM_SENSORS     # per‑sensor timer
        self._randomise_leds()
        update_soc_display(self.soc)

        self._play_round()        # enter main play loop

    def _play_round(self) -> None:
        both_pressed_since: Optional[float] = None

        while self.actions < MAX_ACTIONS:
            active = self._get_active_sensor()

            # enable / disable button illumination
            any_active = active is not None
            set_button_led("charge", any_active)
            set_button_led("discharge", any_active)

            # -------- Reset combo (both buttons ≥ 3 s) -------- #
            if read_button("charge") and read_button("discharge"):
                if both_pressed_since is None:
                    both_pressed_since = time.time()
                elif time.time() - both_pressed_since >= 3.0:
                    self._full_reset()
                    return
            else:
                both_pressed_since = None  # combo broken

            # -------- Handle a user action -------- #
            if active is not None:
                if read_button("charge"):
                    self._handle_action(active, "charge")
                elif read_button("discharge"):
                    self._handle_action(active, "discharge")

            time.sleep(0.01)      # 100 Hz polling

        # round finished → back to idle
        self.idle()

    # -------------------------- Action Processing ------------------------- #

    def _handle_action(self, sensor_idx: int, button: str) -> None:
        now = time.time()

        # enforce 1 s minimum delay for *same* sensor
        if now - self.last_action_ts[sensor_idx] < 1.0:
            return
        self.last_action_ts[sensor_idx] = now

        led_value   = self.led_values[sensor_idx]          # 0 / 1 on that LED
        soc_change  = 0
        score_delta = 0

        if led_value == 0:                     # RED LED
            if button == "charge":
                score_delta = 5
                soc_change  =  SOC_INCREMENT[sensor_idx]
            else:  # discharge
                score_delta = 100
                soc_change  = -1
        else:                                  # GREEN LED
            if button == "charge":
                score_delta = 50
                soc_change  =  SOC_INCREMENT[sensor_idx]
            else:  # discharge
                score_delta = 5

        # penalty when switching sensors
        if self.last_sensor is not None and self.last_sensor != sensor_idx:
            soc_change -= 1

        self.last_sensor = sensor_idx
        self.actions    += 1

        # apply score / SoC changes
        self.score += score_delta
        self.soc    = max(0, min(SOC_LEVELS, self.soc + soc_change))

        update_score_display(self.score)
        update_soc_display(self.soc)

        # visual feedback
        self._spin_windmill_briefly()

        # prepare next turn
        self._randomise_leds()

        # wait until the button is released (simple debounce)
        while read_button("charge") or read_button("discharge"):
            time.sleep(0.01)

    # ------------------------------ Helpers ------------------------------- #

    def _get_active_sensor(self) -> Optional[int]:
        """Return index of the *first* low‑active sensor, or *None*."""
        for idx in range(NUM_SENSORS):
            if read_sensor(idx):
                return idx
        return None

    def _randomise_leds(self) -> None:
        """Assign a fresh random 0/1 to every sensor LED."""
        self.led_values = [random.randint(0, 1) for _ in range(NUM_SENSORS)]
        for idx, val in enumerate(self.led_values):
            set_led(idx, LED_COLOR[val], on=True)

    @staticmethod
    def _spin_windmill_briefly() -> None:
        """Spin the turbine for ~200 ms as a little effect."""
        set_windmill(True)
        time.sleep(0.2)
        set_windmill(False)

    def _full_reset(self) -> None:
        """Hard reset (triggered by 3 s button combo)."""
        self.score = 0
        self.idle()

    # ---------------------------- Construction ---------------------------- #

    def __init__(self) -> None:
        self.score         = 0                # persists across rounds
        self.actions       = 0
        self.soc           = SOC_LEVELS // 2
        self.last_sensor   = None
        self.last_action_ts: List[float] = [0.0] * NUM_SENSORS
        self.led_values:   List[int]   = [0] * NUM_SENSORS


# --------------------------------------------------------------------------- #
#                               ‑‑‑  Main  ‑‑‑                               #
# --------------------------------------------------------------------------- #

def main() -> None:
    game = Game()
    try:
        while True:          # power‑up default is idle mode
            game.idle()
    except KeyboardInterrupt:
        # Graceful exit in a development environment
        for idx in range(NUM_SENSORS):
            set_led(idx, "off", on=False)
        set_button_led("charge", False)
        set_button_led("discharge", False)
        set_windmill(False)
        cleanup()


if __name__ == "__main__":
    main()
