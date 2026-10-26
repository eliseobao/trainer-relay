"""UI-state checks use fake events and never access trainer or USB hardware."""

import os
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

try:
    import tkinter as tk

    from interface import BridgeWindow
except ImportError:
    tk = None


@unittest.skipIf(
    tk is None or (os.name != "nt" and not os.environ.get("DISPLAY")), "Tk display required"
)
class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.window = BridgeWindow(AsyncMock(), AsyncMock(), Path.home() / "logs" / "bridge.log")
        self.window.root.withdraw()

    def tearDown(self):
        self.window.close()

    def test_start_requires_selection_and_scan_clears_old_results(self):
        self.assertEqual(str(self.window.start_button["state"]), "disabled")
        self.window.handle(("devices", [("Example trainer", "example-address")]))
        self.assertEqual(str(self.window.start_button["state"]), "normal")
        self.window.handle(("devices", []))
        self.assertEqual(str(self.window.start_button["state"]), "disabled")
        self.assertEqual(self.window.combo.get(), "")

    def test_ready_does_not_claim_computer_is_connected(self):
        self.window.handle(("ready", 53001, 50, 600))
        self.assertEqual(self.window.links["computer"][0].get(), "No signal yet")
        self.window.handle(("link", "computer", "Signal received"))
        self.assertEqual(self.window.links["computer"][0].get(), "Signal received")

    def test_target_and_measured_power_are_distinct(self):
        self.window.handle(("target", 200))
        self.window.handle(("telemetry", 194, None, 28.5, 0))
        self.assertEqual(self.window.values["target"].get(), "200")
        self.assertEqual(self.window.values["power"].get(), "194")
        self.assertEqual(self.window.values["cadence"].get(), "—")

    def test_stale_readings_disappear_without_new_messages(self):
        self.window.handle(("telemetry", 200, 90, 30, 0))
        self.window.sample_at = time.monotonic() - 6
        self.window.root.after_cancel(self.window.after_id)
        self.window.poll()
        for key in ("power", "cadence", "speed"):
            self.assertEqual(self.window.values[key].get(), "—")

    def test_error_survives_worker_completion_and_can_be_copied(self):
        self.window.handle(("error", "USB timeout"))
        self.window.handle(("idle", "bridge", True))
        self.assertEqual(self.window.status_detail.cget("text"), "USB timeout")
        self.window.copy_error()
        self.assertIn("USB timeout", self.window.root.clipboard_get())
        self.assertEqual(str(self.window.copy_button["state"]), "normal")

    def test_clean_stop_clears_old_target_and_links(self):
        self.window.handle(("target", 250))
        self.window.handle(("link", "ant", "Broadcasting"))
        self.window.handle(("idle", "bridge", False))
        self.assertEqual(self.window.values["target"].get(), "—")
        self.assertEqual(self.window.links["ant"][0].get(), "Not broadcasting")
        self.assertEqual(self.window.status_title.cget("text"), "Bridge stopped")


if __name__ == "__main__":
    unittest.main()
