from __future__ import annotations
"""
Combined GUI + game‑logic so you can just run **energy_game_combined.py**.
The script …
* builds the Tk‑based GUI (Battery + Score + status labels)
* starts the GPIO‑based game logic in a background thread

Running the file pops up the window immediately while the game loop
keeps polling the hardware and updating the GUI.

⚠️ Thread‑safety: All calls that *touch* Tk widgets are marshalled back to
   the GUI thread via `display.after(0, …)`.
   Hardware I/O (GPIO, LEDs, wind‑mill) is still performed in the worker
   thread.

Adjust the GPIO pin numbers / LED helpers for your hardware if needed.
"""

###########################################################################
#                                 Imports                                 #
###########################################################################
import random
import threading
import time
from typing import List, Optional

import gpiozero  # sudo pip install gpiozero
from led_controller import (
    init_leds,
    g1,
    g2,
    g3,
    g4,
    r1,
    r2,
    r3,
    r4,
    off1,
    off2,
    off3,
    off4,
    cleanup,
)  # your own helper module
import tkinter as tk
from tkinter import ttk

###########################################################################
#                               GUI classes                               #
###########################################################################
BLUE = "#1976d2"  # “LADEN” label colour
YELLOW_DK = "#cc9900"  # “ENTLADEN” label colour


class BatteryCanvas(tk.Canvas):
    """A scalable, 10‑segment battery visual that redraws on resize."""

    def __init__(self, master, segments: int = 10, *args, **kwargs):
        super().__init__(master, highlightthickness=0, *args, **kwargs)
        self.segments = segments
        self.level = 0  # 0‑segments (int)
        self.bind("<Configure>", lambda ev: self._redraw())

    # --------------------------- Public API --------------------------- #
    def set_level(self, level: int) -> None:
        self.level = max(0, min(level, self.segments))
        self._redraw()

    # ------------------------ Internal helpers ------------------------ #
    def _redraw(self) -> None:
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1 or h <= 1:
            return  # geometry not yet available

        body_margin = min(w, h) * 0.05
        body_h = h * 0.9
        body_w = w * 0.8
        tip_h = h * 0.03

        x0, y0 = (w - body_w) / 2, (h - body_h) / 2
        x1, y1 = x0 + body_w, y0 + body_h

        # Battery outline
        self.create_rectangle(x0, y0, x1, y1, width=3)
        # Battery tip
        tip_w = body_w * 0.4
        tip_x0 = (w - tip_w) / 2
        self.create_rectangle(tip_x0, y0, tip_x0 + tip_w, y0 - tip_h, width=3)

        # Segments (draw bottom‑up)
        seg_h = body_h / self.segments
        for i in range(self.segments):
            seg_y0 = y1 - seg_h * (i + 1)
            seg_y1 = y1 - seg_h * i
            fill_colour = "#22aa22" if i < self.level else ""
            self.create_rectangle(
                x0 + 4, seg_y0 + 4, x1 - 4, seg_y1 - 4, width=0, fill=fill_colour
            )


class ScoreGUI(tk.Tk):
    """Main window showing battery, 4‑digit score, and two status labels."""

    def __init__(self):
        super().__init__()
        self.title("Energy‑Game Display")
        self.minsize(480, 260)

        # ---- Layout: 1 row × 2 columns (weights 1:2) ----
        self.columnconfigure(0, weight=1)  # Battery column
        self.columnconfigure(1, weight=2)  # Score + status column
        self.rowconfigure(0, weight=1)

        # Battery ------------------------------------------------------
        self.battery = BatteryCanvas(self, bg="white")
        self.battery.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # Right‑hand container ----------------------------------------
        right = ttk.Frame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        # Score label --------------------------------------------------
        self._score_var = tk.StringVar(value="0000")
        ttk.Label(
            right,
            textvariable=self._score_var,
            font=("Courier", 96, "bold"),
            anchor="center",
            justify="center",
        ).grid(row=0, column=0)

        # Status labels container -------------------------------------
        status = ttk.Frame(right)
        status.grid(row=1, column=0, sticky="s")
        self.laden_lbl = tk.Label(status, text="LADEN", fg=BLUE, font=("Helvetica", 20, "bold"))
        self.entl_lbl = tk.Label(
            status, text="ENTLADEN", fg=YELLOW_DK, font=("Helvetica", 20, "bold")
        )
        self.laden_lbl.pack(side="left", padx=(0, 20))
        self.entl_lbl.pack(side="left")

    # --------------------------- Public API --------------------------- #
    def set_score(self, value: int) -> None:
        self._score_var.set(f"{value:04d}")

    def set_soc(self, level: int) -> None:
        self.battery.set_level(level)

    # ------------------------ Highlight helpers ----------------------- #
    def highlight_laden(self, active: bool = True) -> None:
        self._set_highlight(self.laden_lbl, active)

    def highlight_entladen(self, active: bool = True) -> None:
        self._set_highlight(self.entl_lbl, active)

    def _set_highlight(self, label: tk.Label, active: bool) -> None:
        cfg = {
            "relief": "flat",
            "highlightbackground": label.cget("fg") if active else label.cget("background"),
            "highlightcolor": label.cget("fg") if active else label.cget("background"),
            "highlightthickness": 2 if active else 2,
        }
        label.config(**cfg)


###########################################################################
#                        GPIO & hardware abstraction                       #
###########################################################################

NUM_SENSORS = 4
SOC_LEVELS = 10
MAX_ACTIONS = 10
BUTTONS = ("charge", "discharge")
LED_COLOR = {0: "red", 1: "green"}

# --- GPIO objects ---------------------------------------------------
btn_charge = gpiozero.Button(2, bounce_time=0.05)
btn_discharge = gpiozero.Button(3, bounce_time=0.05)
park_office = gpiozero.Button(4, bounce_time=0.05)
park_home = gpiozero.Button(17, bounce_time=0.05)
park_shop = gpiozero.Button(27, bounce_time=0.05)
park_charge = gpiozero.Button(22, bounce_time=0.05)
windmill = gpiozero.Servo(10, min_pulse_width=0.00149, max_pulse_width=0.0015)
led_charge = gpiozero.LED(9)
led_discharge = gpiozero.LED(11)

if not init_leds(physical_leds=4):
    raise RuntimeError("LED initialisation failed. Check wiring and pin‑numbers.")

# The **display** instance is created *once* and shared across the module.
# All GUI‑updates from other threads are marshalled via display.after.
display = ScoreGUI()

def _gui_call(func, *args, **kwargs):
    """Schedule *func* to run in the Tk/GUI thread ASAP."""
    display.after(0, lambda: func(*args, **kwargs))


# ---------- Sensor helpers ------------------------------------------ #

def read_sensor(index: int) -> bool:
    """Return *True* if sensor *index* is LOW (active)."""
    mapping = [park_office, park_home, park_shop, park_charge]
    return mapping[index].is_pressed


def set_led(index: int, color: str, on: bool = True) -> None:
    """Drive the RGB LED attached to *sensor index*."""
    off_funcs = [off1, off2, off3, off4]
    on_funcs_red = [r1, r2, r3, r4]
    on_funcs_green = [g1, g2, g3, g4]

    off_funcs[index]()  # always blank first
    if on:
        (on_funcs_red if color == "red" else on_funcs_green)[index]()


# ---------- Button helpers ------------------------------------------ #

def read_button(name: str) -> bool:  # charge / discharge
    return btn_charge.is_pressed if name == "charge" else btn_discharge.is_pressed


def set_button_led(name: str, on: bool) -> None:
    """Switch integrated LED and highlight label."""

    if name == "charge":
        (led_charge.on if on else led_charge.off)()
        _gui_call(display.highlight_laden, on)
    else:
        (led_discharge.on if on else led_discharge.off)()
        _gui_call(display.highlight_entladen, on)


# ---------- Wind‑mill ----------------------------------------------- #

def set_windmill(on: bool) -> None:
    windmill.max() if on else windmill.detach()


# ---------- GUI update wrappers ------------------------------------- #

def update_score_display(score: int) -> None:
    _gui_call(display.set_score, score)


def update_soc_display(level: int) -> None:
    _gui_call(display.set_soc, level)

###########################################################################
#                                 Game                                    #
###########################################################################

# SoC gain per sensor when *charging*
SOC_INCREMENT = (2, 3, 4, 2)


class Game:
    """Encapsulates one full game session (idle <‑‑> play)."""

    # ----------------------------- Idle ------------------------------ #

    def idle(self) -> None:
        """Idle loop – waits for a button press and shows last score."""
        for idx in range(NUM_SENSORS):
            set_led(idx, "off", on=False)
        set_button_led("charge", False)
        set_button_led("discharge", False)
        set_windmill(False)

        update_score_display(self.score)

        while True:
            if read_button("charge") or read_button("discharge"):
                # debounce until release
                while read_button("charge") or read_button("discharge"):
                    time.sleep(0.01)
                self._start_new_round()
                return
            time.sleep(0.02)

    # --------------------------- Playing ---------------------------- #

    def _start_new_round(self) -> None:
        self.actions = 0
        self.soc = SOC_LEVELS // 2
        self.last_sensor: Optional[int] = None
        self.last_action_ts = [0.0] * NUM_SENSORS
        self._randomise_leds()
        update_soc_display(self.soc)
        self._play_round()

    def _play_round(self) -> None:
        both_pressed_since: Optional[float] = None

        while self.actions < MAX_ACTIONS:
            active = self._get_active_sensor()
            any_active = active is not None
            set_button_led("charge", any_active)
            set_button_led("discharge", any_active)

            # Reset combo (≥3 s both pressed)
            if read_button("charge") and read_button("discharge"):
                if both_pressed_since is None:
                    both_pressed_since = time.time()
                elif time.time() - both_pressed_since >= 3.0:
                    self._full_reset()
                    return
            else:
                both_pressed_since = None

            if active is not None:
                if read_button("charge"):
                    self._handle_action(active, "charge")
                elif read_button("discharge"):
                    self._handle_action(active, "discharge")

            time.sleep(0.01)
        self.idle()

    # ------------------------ Action processing ---------------------- #

    def _handle_action(self, sensor_idx: int, button: str) -> None:
        now = time.time()
        if now - self.last_action_ts[sensor_idx] < 1.0:
            return  # same sensor cooldown
        self.last_action_ts[sensor_idx] = now

        led_value = self.led_values[sensor_idx]
        soc_change = 0
        score_delta = 0

        if led_value == 0:  # RED
            if button == "charge":
                score_delta = 5
                soc_change = SOC_INCREMENT[sensor_idx]
            else:  # discharge
                score_delta = 100
                soc_change = -1
        else:  # GREEN
            if button == "charge":
                score_delta = 50
                soc_change = SOC_INCREMENT[sensor_idx]
            else:  # discharge
                score_delta = 5

        if self.last_sensor is not None and self.last_sensor != sensor_idx:
            soc_change -= 1  # penalty when switching sensors
        self.last_sensor = sensor_idx
        self.actions += 1

        self.score += score_delta
        self.soc = max(0, min(SOC_LEVELS, self.soc + soc_change))

        update_score_display(self.score)
        update_soc_display(self.soc)

        self._spin_windmill_briefly()
        self._randomise_leds()

        while read_button("charge") or read_button("discharge"):
            time.sleep(0.01)

    # ----------------------------- Helpers --------------------------- #

    def _get_active_sensor(self) -> Optional[int]:
        for idx in range(NUM_SENSORS):
            if read_sensor(idx):
                return idx
        return None

    def _randomise_leds(self) -> None:
        self.led_values = [random.randint(0, 1) for _ in range(NUM_SENSORS)]
        for idx, val in enumerate(self.led_values):
            set_led(idx, LED_COLOR[val], on=True)

    @staticmethod
    def _spin_windmill_briefly() -> None:
        set_windmill(True)
        time.sleep(0.2)
        set_windmill(False)

    def _full_reset(self) -> None:
        self.score = 0
        self.idle()

    # --------------------------- Init ------------------------------- #

    def __init__(self) -> None:
        self.score = 0
        self.actions = 0
        self.soc = SOC_LEVELS // 2
        self.last_sensor: Optional[int] = None
        self.last_action_ts: List[float] = [0.0] * NUM_SENSORS
        self.led_values: List[int] = [0] * NUM_SENSORS

###########################################################################
#                                 Main                                    #
###########################################################################

def _game_worker() -> None:
    game = Game()
    try:
        while True:
            game.idle()
    except KeyboardInterrupt:
        pass
    finally:
        # tidy‑up on exit (Ctrl‑C)
        for i in range(NUM_SENSORS):
            set_led(i, "off", on=False)
        set_button_led("charge", False)
        set_button_led("discharge", False)
        set_windmill(False)
        cleanup()


def main() -> None:
    # start worker thread first (daemon dies with GUI)
    t = threading.Thread(target=_game_worker, daemon=True, name="GameThread")
    t.start()

    # now run the Tk main‑loop (blocks until window closed)
    display.mainloop()


if __name__ == "__main__":
    main()
