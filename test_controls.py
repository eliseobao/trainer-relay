"""Control interoperability checks: FE-C requests through to actual FTMS packets."""

import struct
import unittest
from types import SimpleNamespace

from bridge import BIKE, CONTROL, FEATURE, RANGE, Ftms, FtmsRejected, uuid
from protocol import ControlRequest, Fec, Telemetry


class FakeTrainer:
    def __init__(self, features=0xA00C, resistance=(0, 1000, 10), results=None):
        self.calls = []
        self.results = results or {}
        self.values = {
            FEATURE: struct.pack("<II", 0x4001, features),
            RANGE: struct.pack("<hhH", 50, 600, 1),
            BIKE: b"",
            CONTROL: b"",
        }
        if resistance is not None:
            self.values[uuid("2ad6")] = struct.pack("<hhH", *resistance)
        self.services = SimpleNamespace(
            get_characteristic=lambda key: key if key in self.values else None
        )

    async def read_gatt_char(self, key):
        return self.values[key]

    async def start_notify(self, key, callback):
        if key == CONTROL:
            self.indication = callback

    async def write_gatt_char(self, key, data, response):
        self.calls.append(bytes(data))
        results = self.results.get(data[0], [])
        code = results.pop(0) if results else 1
        self.indication(None, bytes([128, data[0], code]))


class EncodingTests(unittest.TestCase):
    def test_resistance_half_percent_and_boundaries(self):
        for raw, percent in [(0, 0), (1, 0.5), (50, 25), (200, 100)]:
            request = Fec(capabilities=7).receive(bytes([48]) + b"\xff" * 6 + bytes([raw]))
            self.assertEqual((request.mode, request.value), ("resistance", percent))

    def test_invalid_resistance_not_forwarded(self):
        fec = Fec(capabilities=7)
        self.assertIsNone(fec.receive(bytes([48]) + b"\xff" * 6 + b"\xc9"))
        self.assertEqual(fec.status[3], 3)

    def test_real_edge_slope_packets(self):
        fec = Fec(capabilities=7)
        for packet, grade in [("33ffffffff844eff", 1), ("33ffffffff204eff", 0)]:
            request = fec.receive(bytes.fromhex(packet))
            self.assertAlmostEqual(request.value, grade)
            self.assertAlmostEqual(request.rolling, 0.004)

    def test_grade_sentinel_preserves_grade_for_rolling_update(self):
        request = Fec(capabilities=7).receive(bytes.fromhex("33ffffffffffff50"))
        self.assertIsNone(request.value)
        self.assertAlmostEqual(request.rolling, 0.004)

    def test_invalid_grade_rejected(self):
        fec = Fec(capabilities=7)
        self.assertIsNone(
            fec.receive(bytes([51]) + b"\xff" * 4 + struct.pack("<H", 40001) + b"\xff")
        )
        self.assertEqual(fec.status[3], 3)

    def test_wind_units_and_drafting(self):
        request = Fec(capabilities=7).receive(bytes([50]) + b"\xff" * 4 + bytes([51, 163, 50]))
        self.assertEqual(request.wind, (10, 0.51, 0.5))

    def test_default_wind_values(self):
        request = Fec(capabilities=7).receive(bytes([50]) + b"\xff" * 7)
        self.assertEqual(request.wind, (0, 0.51, 1))

    def test_unsupported_modes_match_advertisement(self):
        fec = Fec(capabilities=2)
        for page in (48, 50, 51):
            self.assertIsNone(fec.receive(bytes([page]) + b"\xff" * 7))
            self.assertEqual(fec.status[3], 2)
        self.assertEqual(fec.common(54)[7], 2)

    def test_bad_drafting_rejected(self):
        fec = Fec(capabilities=7)
        self.assertIsNone(fec.receive(bytes([50]) + b"\xff" * 4 + bytes([51, 127, 101])))
        self.assertEqual(fec.status[3], 3)


class ControlModeTests(unittest.IsolatedAsyncioTestCase):
    async def trainer(self, **kwargs):
        client = FakeTrainer(**kwargs)
        ftms = Ftms(client, Telemetry())
        await ftms.initialize()
        client.calls.clear()
        return ftms, client

    async def test_features_control_advertisement(self):
        ftms, _ = await self.trainer()
        self.assertEqual(ftms.fec_capabilities, 7)
        ftms, _ = await self.trainer(features=8, resistance=None)
        self.assertEqual(ftms.fec_capabilities, 2)
        ftms, _ = await self.trainer(features=0xA00C, resistance=None)
        self.assertEqual(ftms.fec_capabilities, 6)

    async def test_simulation_only_trainer_is_supported(self):
        ftms, _ = await self.trainer(features=1 << 13, resistance=None)
        self.assertEqual(ftms.fec_capabilities, 4)
        with self.assertRaises(NotImplementedError):
            await ftms.target(200)

    async def test_broken_resistance_range_does_not_break_erg(self):
        ftms, _ = await self.trainer(resistance=(100, 0, 0))
        self.assertEqual(ftms.fec_capabilities, 6)
        self.assertEqual(await ftms.target(100), 100)

    async def test_resistance_maps_to_advertised_native_range(self):
        ftms, client = await self.trainer(resistance=(100, 1100, 10))
        self.assertEqual(await ftms.resistance(50), 50)
        self.assertEqual(client.calls, [bytes([4]) + struct.pack("<h", 600), b"\x07"])

    async def test_resistance_quantizes_inside_supported_grid(self):
        ftms, client = await self.trainer(resistance=(0, 100, 30))
        self.assertEqual(await ftms.resistance(100), 90)
        self.assertEqual(client.calls[0], b"\x04\x5a\x00")

    async def test_resistance_out_of_range_sends_nothing(self):
        ftms, client = await self.trainer()
        with self.assertRaises(ValueError):
            await ftms.resistance(101)
        self.assertEqual(client.calls, [])

    async def test_legacy_resistance_retry_and_cached_format(self):
        ftms, client = await self.trainer(resistance=(0, 100, 1), results={4: [3, 1, 1]})
        await ftms.resistance(50)
        await ftms.resistance(25)
        self.assertEqual(
            client.calls, [b"\x04\x32\x00", b"\x04\x32", b"\x07", b"\x04\x19", b"\x07"]
        )

    async def test_operation_failed_is_not_guessed_as_legacy(self):
        ftms, client = await self.trainer(resistance=(0, 100, 1), results={4: [4]})
        with self.assertRaises(FtmsRejected):
            await ftms.resistance(50)
        self.assertEqual(client.calls, [b"\x04\x32\x00"])

    async def test_slope_packet_includes_default_road_parameters(self):
        ftms, client = await self.trainer()
        request = Fec(capabilities=7).receive(bytes.fromhex("33ffffffff844eff"))
        self.assertEqual(await ftms.apply(request), (1, "Slope", "%"))
        self.assertEqual(
            client.calls, [bytes([17]) + struct.pack("<hhBB", 0, 100, 40, 51), b"\x07"]
        )

    async def test_wind_update_preserves_grade_and_applies_drafting(self):
        ftms, client = await self.trainer()
        await ftms.simulate(ControlRequest(51, "simulation", 3, 0.005))
        await ftms.simulate(ControlRequest(50, "simulation", wind=(10, 0.6, 0.5)))
        self.assertEqual(client.calls[2], bytes([17]) + struct.pack("<hhBB", 10000, 300, 50, 30))

    async def test_rolling_update_preserves_grade_when_unspecified(self):
        ftms, client = await self.trainer()
        await ftms.simulate(ControlRequest(51, "simulation", -1, 0.004))
        await ftms.simulate(ControlRequest(51, "simulation", None, 0.006))
        self.assertEqual(client.calls[2], bytes([17]) + struct.pack("<hhBB", 0, -100, 60, 51))

    async def test_wind_outside_ftms_encoding_is_rejected(self):
        ftms, client = await self.trainer()
        with self.assertRaises(ValueError):
            await ftms.simulate(ControlRequest(50, "simulation", wind=(40, 0.51, 1)))
        self.assertEqual(client.calls, [])

    async def test_rejected_simulation_does_not_commit_cached_parameters(self):
        ftms, client = await self.trainer(results={17: [3]})
        previous = ftms.simulation_parameters
        with self.assertRaises(FtmsRejected):
            await ftms.simulate(ControlRequest(51, "simulation", 5, 0.006))
        self.assertEqual(ftms.simulation_parameters, previous)
        self.assertEqual(len(client.calls), 1)

    async def test_erg_slope_resistance_erg_transitions(self):
        ftms, client = await self.trainer()
        self.assertEqual(await ftms.apply(ControlRequest(49, "erg", 200)), (200, "ERG", "W"))
        self.assertEqual(
            await ftms.apply(ControlRequest(51, "simulation", 2, 0.004)), (2, "Slope", "%")
        )
        self.assertEqual(
            await ftms.apply(ControlRequest(48, "resistance", 25)), (25, "Resistance", "%")
        )
        self.assertEqual(await ftms.apply(ControlRequest(49, "erg", 150)), (150, "ERG", "W"))
        self.assertEqual([data[0] for data in client.calls], [5, 7, 17, 7, 4, 7, 5, 7])
        self.assertEqual(ftms.mode, "erg")

    async def test_power_quantizes_inside_the_advertised_grid(self):
        ftms, client = await self.trainer()
        ftms.minimum, ftms.maximum, ftms.increment = 50, 60, 4
        self.assertEqual(await ftms.target(60), 58)
        self.assertEqual(client.calls[0], b"\x05\x3a\x00")

    async def test_start_failure_does_not_claim_an_accepted_mode(self):
        ftms, _ = await self.trainer(results={7: [4]})
        with self.assertRaisesRegex(RuntimeError, "Stop and reconnect"):
            await ftms.simulate(ControlRequest(51, "simulation", 2, 0.004))
        self.assertIsNone(ftms.mode)

    async def test_wind_does_not_cancel_erg_and_is_used_by_next_slope(self):
        ftms, client = await self.trainer()
        await ftms.target(200)
        previous = list(client.calls)
        result = await ftms.apply(ControlRequest(50, "simulation", wind=(10, 0.6, 0.5)))
        self.assertIsNone(result[0])
        self.assertEqual(client.calls, previous)
        self.assertEqual(ftms.mode, "erg")
        await ftms.simulate(ControlRequest(51, "simulation", 1, 0.004))
        self.assertEqual(client.calls[2], bytes([17]) + struct.pack("<hhBB", 10000, 100, 40, 30))

    async def test_wind_does_not_cancel_basic_resistance(self):
        ftms, client = await self.trainer()
        await ftms.resistance(25)
        count = len(client.calls)
        await ftms.apply(ControlRequest(50, "simulation", wind=(0, 0.51, 1)))
        self.assertEqual(len(client.calls), count)
        self.assertEqual(ftms.mode, "resistance")


class BridgeRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def run_session(self, results=None):
        import asyncio
        import threading
        from contextlib import asynccontextmanager
        from unittest.mock import patch

        from bridge import run_bridge

        client = FakeTrainer(results=results)
        client.is_connected = True
        stop = threading.Event()
        messages = []
        outcomes = []
        packets = [
            bytes([48]) + b"\xff" * 6 + bytes([100]),
            bytes.fromhex("33ffffffff844eff"),
            bytes([49]) + b"\xff" * 5 + struct.pack("<H", 800),
        ]

        def report(message):
            messages.append(message)
            if isinstance(message, tuple) and message[0] in ("target", "command_error"):
                outcomes.append(message)
                if len(outcomes) == len(packets):
                    stop.set()

        class Session:
            def __init__(self):
                self.sent = []
                self.page_requested = False
                self.tx = False
                self.index = 0

            async def open(self, device_id):
                return self

            async def broadcast(self, page):
                self.sent.append(page)

            async def close(self):
                self.closed = True

            async def read(self):
                await asyncio.sleep(0)
                if not self.page_requested:
                    self.page_requested = True
                    return [(0x4F, b"\0" + bytes([70, 255, 255, 255, 255, 1, 54, 1]))]
                if not self.tx:
                    self.tx = True
                    return [(0x40, b"\0\x01\x03")]
                if self.index < len(packets) and self.index == len(outcomes):
                    packet = packets[self.index]
                    self.index += 1
                    self.tx = False
                    return [(0x4F, b"\0" + packet)]
                return []

        ant = Session()

        @asynccontextmanager
        async def connection(*args):
            yield client

        with (
            patch("bridge.trainer_connection", connection),
            patch("bridge.AntSession", return_value=ant),
        ):
            await asyncio.wait_for(run_bridge("example", stop, report), 5)
        self.assertTrue(ant.closed)
        self.assertEqual(client.calls[-1], b"\x08\x01")
        self.assertTrue(any(page[0] == 54 and page[7] == 7 for page in ant.sent))
        return outcomes

    async def test_complete_bridge_routes_modes_and_stops_cleanly(self):
        outcomes = await self.run_session()
        self.assertEqual(
            outcomes,
            [
                ("target", 50, "Resistance", "%"),
                ("target", 1, "Slope", "%"),
                ("target", 200, "ERG", "W"),
            ],
        )

    async def test_complete_bridge_continues_after_a_normal_rejection(self):
        outcomes = await self.run_session(results={4: [3]})
        self.assertEqual(outcomes[0][0], "command_error")
        self.assertEqual(outcomes[1], ("target", 1, "Slope", "%"))
        self.assertEqual(outcomes[2], ("target", 200, "ERG", "W"))

    async def test_unusable_trainer_is_disconnected_without_unowned_stop_command(self):
        import threading
        from contextlib import asynccontextmanager
        from unittest.mock import patch

        from bridge import run_bridge

        client = FakeTrainer(features=0, resistance=None)
        client.is_connected = True

        @asynccontextmanager
        async def connection(*args):
            yield client

        with patch("bridge.trainer_connection", connection):
            with self.assertRaisesRegex(RuntimeError, "no usable"):
                await run_bridge("example", threading.Event(), lambda _: None)
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
