"""Small Windows UI. Radio work stays in a worker; widgets stay on Tk's thread."""

import asyncio
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from app_info import APP_NAME, TRAINER_ID, VERSION

BG = "#F3F5F7"
WHITE = "#FFFFFF"
INK = "#172B3A"
MUTED = "#637482"
BLUE = "#176B82"
GREEN = "#197454"
RED = "#AD3545"
BORDER = "#DFE6EB"


class BridgeWindow:
    def __init__(self, scan, bridge, log_path, preview=False):
        self.scan, self.bridge, self.log_path = scan, bridge, log_path
        self.preview = preview
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} — Bluetooth to ANT+")
        icon = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "assets" / "app.ico"
        if sys.platform == "win32" and icon.exists():
            self.root.iconbitmap(str(icon))
        self.root.geometry("820x760")
        self.root.minsize(780, 750)
        self.root.configure(bg=BG)
        self.messages = queue.Queue()
        self.stop = threading.Event()
        self.busy = self.connected = self.closing = False
        self.devices = []
        self.error = ""
        self.sample_at = 0
        self.sample_age = 0
        self.connection_detail = ""
        self.after_id = None
        self.links = {}
        self.values = {}
        self.build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if preview:
            self.combo["values"] = ["Example FTMS trainer (preview)"]
            self.combo.current(0)
            for name, value in [
                ("bluetooth", "Connected"),
                ("ant", "Broadcasting"),
                ("computer", "Signal received"),
            ]:
                self.link(name, value)
            self.handle(("target", 1.5, "Slope", "%"))
            self.values["power"].set("198")
            self.values["speed"].set("31.2")
            self.state(
                "Preview — no hardware connected", "Sample data for the interface preview.", BLUE
            )
            self.scan_button.configure(state="disabled")
            self.start_button.configure(state="disabled")
            self.activity("Preview only · no radio connections or trainer commands")
        self.poll()

    def label(self, parent, text="", size=10, color=INK, bold=False, **kwargs):
        return tk.Label(
            parent,
            text=text,
            bg=parent.cget("bg"),
            fg=color,
            font=("Segoe UI", size, "bold" if bold else "normal"),
            **kwargs,
        )

    def card(self, parent):
        return tk.Frame(
            parent,
            bg=WHITE,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            highlightthickness=1,
        )

    def build(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TButton", font=("Segoe UI", 10), padding=(14, 9))
        style.configure("Accent.TButton", background=BLUE, foreground=WHITE)
        style.map(
            "Accent.TButton",
            background=[("disabled", "#DBE1E5"), ("active", "#12566A")],
            foreground=[("disabled", "#84919A")],
        )
        style.configure("TCombobox", padding=8, font=("Segoe UI", 10))
        panel = tk.Frame(self.root, bg=BG, padx=24, pady=20)
        panel.pack(fill="both", expand=True)
        header = tk.Frame(panel, bg=BG)
        header.pack(fill="x")
        self.label(header, APP_NAME, 25, bold=True).pack(side="left")
        self.label(header, f"v{VERSION}", 10, color=MUTED).pack(side="right", pady=12)
        self.label(
            panel, "Your Bluetooth trainer. Your ANT+ cycling computer.", 11, color=MUTED
        ).pack(anchor="w", pady=(2, 16))

        connection = self.card(panel)
        connection.pack(fill="x")
        inside = tk.Frame(connection, bg=WHITE, padx=16, pady=14)
        inside.pack(fill="x")
        self.label(inside, "TRAINER", 9, color=MUTED, bold=True).pack(anchor="w", pady=(0, 6))
        row = tk.Frame(inside, bg=WHITE)
        row.pack(fill="x")
        self.combo = ttk.Combobox(row, state="readonly", font=("Segoe UI", 10))
        self.combo.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.combo.bind("<<ComboboxSelected>>", lambda _: self.buttons())
        self.scan_button = ttk.Button(row, text="Scan", command=self.do_scan)
        self.scan_button.pack(side="left")
        row = tk.Frame(inside, bg=WHITE)
        row.pack(fill="x", pady=(12, 0))
        self.start_button = ttk.Button(
            row, text="Start bridge", style="Accent.TButton", command=self.connect, state="disabled"
        )
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(row, text="Stop", command=self.request_stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        self.label(row, f"ANT+ trainer ID  {TRAINER_ID}", 10, color=MUTED).pack(side="right")

        links = tk.Frame(panel, bg=BG)
        links.pack(fill="x", pady=(12, 0))
        for i, (key, title) in enumerate(
            [
                ("bluetooth", "BLUETOOTH TRAINER"),
                ("ant", "ANT+ DONGLE"),
                ("computer", "CYCLING COMPUTER"),
            ]
        ):
            links.columnconfigure(i, weight=1, uniform="links")
            card = self.card(links)
            card.grid(row=0, column=i, sticky="nsew", padx=(0, 8) if i < 2 else 0)
            self.label(card, title, 8, color=MUTED, bold=True).pack(
                anchor="w", padx=12, pady=(10, 3)
            )
            variable = tk.StringVar(
                value="Not connected"
                if key == "bluetooth"
                else "Not broadcasting"
                if key == "ant"
                else "No signal yet"
            )
            widget = self.label(card, size=10)
            widget.configure(textvariable=variable)
            widget.pack(anchor="w", padx=12, pady=(0, 10))
            self.links[key] = (variable, widget)

        status = tk.Frame(panel, bg=BG)
        status.pack(fill="x", pady=(14, 10))
        self.status_title = self.label(status, "Ready to connect", 12, bold=True)
        self.status_title.pack(anchor="w")
        self.status_detail = self.label(
            status,
            "Power on your trainer and scan to begin.",
            10,
            color=MUTED,
            wraplength=735,
            justify="left",
        )
        self.status_detail.pack(anchor="w", pady=(3, 0))
        metrics = tk.Frame(panel, bg=BG)
        metrics.pack(fill="x")
        for i, (key, title, unit) in enumerate(
            [
                ("target", "CONTROL TARGET", ""),
                ("power", "TRAINER POWER", "W"),
                ("speed", "SPEED", "km/h"),
                ("cadence", "TRAINER CADENCE", "rpm"),
            ]
        ):
            metrics.columnconfigure(i, weight=1, uniform="metrics")
            card = self.card(metrics)
            card.grid(row=0, column=i, sticky="nsew", padx=(0, 8) if i < 3 else 0)
            title_label = self.label(card, title, 8, color=MUTED, bold=True)
            title_label.pack(anchor="w", padx=12, pady=(10, 1))
            if key == "target":
                self.target_heading = title_label
            value = tk.StringVar(value="—")
            self.values[key] = value
            widget = self.label(card, size=27, color=BLUE if key == "target" else INK, bold=True)
            widget.configure(textvariable=value)
            widget.pack(anchor="w", padx=12)
            unit_label = self.label(card, unit, 9, color=MUTED)
            unit_label.pack(anchor="w", padx=12, pady=(0, 10))
            if key == "target":
                self.target_unit = unit_label
        self.label(
            panel,
            "Trainer readings only · Crank power and cadence paired to your cycling computer are separate.",
            9,
            color=MUTED,
        ).pack(anchor="w", pady=(6, 12))
        pairing = self.card(panel)
        pairing.pack(fill="x")
        self.label(pairing, "Pair your cycling computer", 10, bold=True).pack(
            anchor="w", padx=14, pady=(10, 4)
        )
        self.label(
            pairing,
            "Open its indoor-trainer pairing menu and look for ANT+ trainer 53001.",
            10,
            color=MUTED,
        ).pack(anchor="w", padx=14)
        self.label(
            pairing,
            "Keep the app running while riding. Your cycling computer selects the control mode.",
            9,
            color=MUTED,
        ).pack(anchor="w", padx=14, pady=(4, 10))
        footer = tk.Frame(panel, bg=BG)
        footer.pack(fill="x", side="bottom", pady=(8, 0))
        self.event_text = tk.StringVar(
            value="Trainer control · Local connections · No account needed"
        )
        self.label(
            footer,
            color=MUTED,
            size=9,
            textvariable=self.event_text,
            anchor="w",
            wraplength=475,
            justify="left",
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="Open logs", command=self.open_logs).pack(side="right")
        self.copy_button = ttk.Button(
            footer, text="Copy error", command=self.copy_error, state="disabled"
        )
        self.copy_button.pack(side="right", padx=6)

    def state(self, title, detail, color=INK):
        self.status_title.configure(text=title, fg=color)
        self.status_detail.configure(text=detail)

    def link(self, name, value):
        variable, widget = self.links[name]
        variable.set(value)
        widget.configure(
            fg=GREEN if value in ("Connected", "Broadcasting", "Signal received") else MUTED
        )

    def activity(self, text):
        self.event_text.set(text)

    def buttons(self):
        self.scan_button.configure(state="disabled" if self.busy or self.closing else "normal")
        self.start_button.configure(
            state="normal"
            if not self.busy and self.combo.current() >= 0 and not self.closing
            else "disabled"
        )
        self.stop_button.configure(
            state="normal" if self.busy and not self.stop.is_set() else "disabled"
        )
        self.combo.configure(state="disabled" if self.busy or self.closing else "readonly")

    def launch(self, coro, operation):
        self.busy = True
        self.error = ""
        self.stop.clear()
        self.copy_button.configure(state="disabled")
        self.buttons()

        def work():
            import logging

            failed = False
            try:
                asyncio.run(coro)
            except Exception as exc:
                failed = True
                logging.getLogger("bridge").exception("%s failed", operation)
                self.messages.put(("error", str(exc) or type(exc).__name__))
            finally:
                self.messages.put(("idle", operation, failed))

        threading.Thread(target=work, daemon=True).start()

    def do_scan(self):
        self.state(
            "Looking for trainers…",
            "Scanning Bluetooth for 10 seconds. Close other apps connected to the trainer.",
        )

        async def go():
            self.messages.put(("devices", await self.scan()))

        self.launch(go(), "scan")

    def connect(self):
        if self.combo.current() < 0 or self.busy:
            return
        for variable in self.values.values():
            variable.set("—")
        self.sample_at = 0
        self.target_heading.configure(text="CONTROL TARGET")
        self.target_unit.configure(text="")
        self.link("computer", "No signal yet")
        self.state("Connecting…", "Opening the Bluetooth trainer and ANT+ dongle.")
        self.launch(
            self.bridge(self.devices[self.combo.current()][1], self.stop, self.messages.put),
            "bridge",
        )

    def request_stop(self):
        self.stop.set()
        self.buttons()
        self.state("Stopping…", "Finishing pending commands and releasing the connections.")

    def open_logs(self):
        try:
            os.startfile(str(self.log_path.parent))
        except OSError as exc:
            self.handle(("error", f"Could not open log folder: {exc}"))

    def copy_error(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(f"{APP_NAME} {VERSION}\n{self.error}")
        self.activity("Error copied. Attach a redacted log when reporting a problem.")

    def handle(self, message):
        if isinstance(message, str):
            self.status_detail.configure(text=message)
            return
        kind = message[0]
        if kind == "link":
            self.link(message[1], message[2])
        elif kind == "ready":
            self.connected = True
            self.connection_detail = f"ANT+ trainer {message[1]} · {message[2]}"
            self.state("Bridge running", self.connection_detail, GREEN)
            self.activity("Waiting for a target from your cycling computer.")
        elif kind == "target":
            mode, unit = message[2:] if len(message) > 2 else ("ERG", "W")
            self.values["target"].set(f"{message[1]:g}")
            self.target_heading.configure(text=f"{mode.upper()} TARGET")
            self.target_unit.configure(text=unit)
            if self.connected:
                self.state("Bridge running", self.connection_detail, GREEN)
            self.activity(
                f"{time.strftime('%H:%M:%S')} · Trainer accepted {mode.lower()} {message[1]:g}{unit if unit == '%' else ' ' + unit}"
            )
        elif kind == "settings":
            self.activity(message[1])
        elif kind == "command_error":
            self.error = message[1]
            self.state("Target not applied", self.error, RED)
            self.copy_button.configure(state="normal")
            self.activity("Bridge is still running. The last accepted target remains shown.")
        elif kind == "devices":
            self.devices = message[1]
            self.combo["values"] = [f"{name}  ·  {address}" for name, address in self.devices]
            if self.devices:
                self.combo.current(0)
                self.state(
                    "Trainer found"
                    if len(self.devices) == 1
                    else f"{len(self.devices)} trainers found",
                    "Select your trainer, then start the bridge.",
                )
            else:
                self.combo.set("")
                self.state(
                    "No trainer found",
                    "Wake or power-cycle the trainer, close other connected apps, and scan again.",
                )
        elif kind == "error":
            self.error = message[1]
            self.state("Connection needs attention", self.error, RED)
            self.copy_button.configure(state="normal")
            self.activity(
                "Open logs for details. USB timeout? Stop, reconnect the ANT stick, then retry."
            )
        elif kind == "idle":
            self.busy = False
            if message[1] == "bridge":
                self.connected = False
                self.sample_at = 0
                self.target_heading.configure(text="CONTROL TARGET")
                self.target_unit.configure(text="")
                for name, value in [
                    ("bluetooth", "Not connected"),
                    ("ant", "Not broadcasting"),
                    ("computer", "No signal yet"),
                ]:
                    self.link(name, value)
                for variable in self.values.values():
                    variable.set("—")
                if not message[2]:
                    self.state(
                        "Bridge stopped", "Connections released. You can start again when ready."
                    )
            self.buttons()
        elif kind == "telemetry":
            _, power, cadence, speed, age = message
            self.sample_at = time.monotonic()
            self.sample_age = age
            self.values["power"].set("—" if age >= 5 or power is None else str(power))
            self.values["cadence"].set("—" if age >= 5 or cadence is None else f"{cadence:g}")
            self.values["speed"].set("—" if age >= 5 or speed is None else f"{speed:.1f}")
        self.buttons()

    def poll(self):
        while not self.messages.empty():
            self.handle(self.messages.get_nowait())
        if self.sample_at and time.monotonic() - self.sample_at + self.sample_age >= 5:
            for key in ("power", "speed", "cadence"):
                self.values[key].set("—")
        if self.closing and not self.busy:
            self.root.destroy()
            return
        self.after_id = self.root.after(100, self.poll)

    def close(self):
        self.closing = True
        if self.busy:
            self.request_stop()
        else:
            if self.after_id:
                self.root.after_cancel(self.after_id)
            self.root.destroy()

    def run(self):
        self.root.mainloop()
