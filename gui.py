import tkinter as tk
from tkinter import ttk

BLUE      = "#1976d2"   # “LADEN” background
YELLOW_DK = "#cc9900"   # “ENTLADEN” background


class BatteryCanvas(tk.Canvas):
    """A scalable, 10‑segment battery visualization that redraws on resize."""

    def __init__(self, master, segments: int = 10, *args, **kwargs):
        super().__init__(master, highlightthickness=0, *args, **kwargs)
        self.segments = segments
        self.level = 0  # 0‑segments (int)
        self.bind("<Configure>", lambda ev: self._redraw())

    # ------- Public API -------------------------------------------------
    def set_level(self, level: int) -> None:
        """Clamp *level* to 0…segments and refresh the drawing."""
        self.level = max(0, min(level, self.segments))
        self._redraw()

    # ------- Internal helpers ------------------------------------------
    def _redraw(self) -> None:
        """Redraw the whole battery each time the widget is resized or level changes."""
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1 or h <= 1:  # geometry not yet calculated
            return

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
            self.create_rectangle(x0 + 4, seg_y0 + 4, x1 - 4, seg_y1 - 4,
                                   width=0, fill=fill_colour)


class ScoreGUI(tk.Tk):
    """Main window hosting a battery, 4‑digit score and two status labels."""

    def __init__(self):
        super().__init__()
        self.title("Score Display")
        self.minsize(400, 240)

        # ---- Top‑level grid: 1 row × 2 columns (weights 1:2) ------------
        self.columnconfigure(0, weight=1)   # Battery column
        self.columnconfigure(1, weight=2)   # Score + status column
        self.rowconfigure(0, weight=1)

        # Battery (left) --------------------------------------------------
        self.battery = BatteryCanvas(self, bg="white")
        self.battery.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # Right‑hand container -------------------------------------------
        right = ttk.Frame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)  # Score gets the extra vertical space
        right.rowconfigure(1, weight=0)

        # Score label (monospaced, centred) ------------------------------
        self._score_var = tk.StringVar(value="0000")
        self.score_lbl = ttk.Label(
            right,
            textvariable=self._score_var,
            font=("Courier", 96, "bold"),
            anchor="center",
            justify="center",
        )
        # No sticky flags ⇒ stays centred horizontally & vertically in its cell
        self.score_lbl.grid(row=0, column=0)

        # Status labels container (centred bottom) -----------------------
        status = ttk.Frame(right)
        status.grid(row=1, column=0, sticky="s")  # centred via grid defaults

        self.laden_lbl = tk.Label(status, text="LADEN", fg="blue",
                                   font=("Helvetica", 20, "bold"))
        self.entl_lbl = tk.Label(status, text="ENTLADEN", fg="#cc9900",
                                   font=("Helvetica", 20, "bold"))
        self.laden_lbl.pack(side="left", padx=(0, 20))
        self.entl_lbl.pack(side="left")

        # --- Public API --------------------------------------------------
    def set_score(self, value: int) -> None:
        """Update 4‑digit, zero‑padded score."""
        self._score_var.set(f"{value:04d}")

    def set_soc(self, level: int) -> None:
        """Update state‑of‑charge (0‑10)."""
        self.battery.set_level(level)

    #  Highlight helpers -------------------------------------------------
    def highlight_laden(self, active: bool = True) -> None:
        """Turn highlighting for the LADEN label on or off."""
        self._set_highlight(self.laden_lbl, active)
        #if active:
        #    self.highlight_entladen(False)  # optional mutual exclusion

    def highlight_entladen(self, active: bool = True) -> None:
        """Turn highlighting for the ENTLADEN label on or off."""
        self._set_highlight(self.entl_lbl, active)
        if active:
            self.highlight_laden(False)

    def _set_highlight(self, label: tk.Label, active: bool) -> None:
        """Apply or remove a bold border around *label* as the highlight."""
        if active:
            label.config(relief="flat", highlightbackground=label.cget("fg"), highlightcolor=label.cget("fg"), highlightthickness=2)
        else:
            label.config(relief="flat", highlightbackground=label.cget("background"), highlightcolor=label.cget("background"), highlightthickness=2)

    # # Demo loop (remove when integrating) -------------------------------
    # def _demo_tick(self):
    #     import random

    #     self.set_soc(random.randint(0, 10))
    #     self.set_score(random.randint(0, 9999))
    #     # Randomly highlight one of the two labels
    #     self.highlight_laden(False)
    #     self.highlight_entladen(False)
    #     if random.choice([True, False]):
    #         self.highlight_laden(True)
    #     else:
    #         self.highlight_entladen(True)

    #     self.after(1000, self._demo_tick)

    # # -------------------------------------------------------------------
    # def run_demo(self):
    #     """Start the optional self‑running demo."""
    #     self._demo_tick()


if __name__ == "__main__":
    gui = ScoreGUI()
    gui.run_demo()
    gui.mainloop()
