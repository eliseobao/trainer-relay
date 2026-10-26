import asyncio
import struct
import unittest

from bridge import Ftms
from protocol import Fec, Frames, Telemetry, frame, indoor_bike


class ProtocolTests(unittest.TestCase):
    def test_indoor_bike_optional_fields(self):
        state = Telemetry()
        data = (
            struct.pack("<HHHH", 2 | 4 | 16 | 32 | 64, 2500, 2400, 180)
            + bytes([1, 2, 3])
            + struct.pack("<hh", 20, 215)
        )
        indoor_bike(data, state)
        self.assertEqual((state.speed, state.cadence, state.power), (25, 90, 215))

    def test_fragment_does_not_have_speed(self):
        state = Telemetry(speed=20)
        indoor_bike(struct.pack("<Hh", 1 | 64, 150), state)
        self.assertEqual((state.speed, state.power), (20, 150))

    def test_truncated_update_is_atomic(self):
        state = Telemetry(power=100, speed=10)
        with self.assertRaises(struct.error):
            indoor_bike(struct.pack("<HH", 64, 2400), state)
        self.assertEqual((state.speed, state.power), (10, 100))

    def test_framing_fragmented_and_corrupt(self):
        packet = frame(0x4F, bytes(range(9)))
        decoder = Frames()
        self.assertEqual(list(decoder.feed(b"noise" + packet[:4])), [])
        self.assertEqual(list(decoder.feed(packet[4:])), [(0x4F, bytes(range(9)))])
        bad = bytearray(packet)
        bad[-1] ^= 1
        self.assertEqual(list(decoder.feed(bad + packet)), [(0x4F, bytes(range(9)))])

    def test_garmin_target_quarter_watts_and_ack(self):
        fec = Fec()
        target = bytes([49]) + b"\xff" * 5 + struct.pack("<H", 800)
        self.assertEqual(fec.receive(target), 200)
        self.assertEqual(fec.status[:4], bytes([71, 49, 0, 4]))
        fec.result(0)
        self.assertEqual(fec.common(71), bytes([71, 49, 0, 0]) + target[4:8])

    def test_page_request_and_capabilities(self):
        fec = Fec()
        fec.receive(bytes([70, 255, 255, 255, 255, 2, 54, 1]))
        self.assertEqual(len(fec.pending), 2)
        self.assertEqual(fec.next_page(Telemetry())[-1], 2)

    def test_stale_power_is_unknown(self):
        fec = Fec()
        fec.count = 1
        page = fec.next_page(Telemetry(power=200, cadence=90))
        self.assertEqual(page[2], 255)
        self.assertEqual(struct.unpack_from("<H", page, 5)[0], 0xFFF)

    def test_all_pages_eight_bytes(self):
        fec = Fec()
        self.assertTrue(all(len(fec.next_page(Telemetry())) == 8 for _ in range(264)))


class FakeClient:
    def __init__(self, result=1):
        self.calls = []
        self.result = result

    async def write_gatt_char(self, uuid, data, response):
        self.calls.append(bytes(data))
        self.ftms.indication(None, bytes([128, data[0], self.result]))


class ControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_erg_conversion_and_start(self):
        client = FakeClient()
        ftms = Ftms(client, Telemetry())
        client.ftms = ftms
        await ftms.target(200)
        self.assertEqual(client.calls, [b"\x05\xc8\x00", b"\x07"])

    async def test_zero_target_stops(self):
        client = FakeClient()
        ftms = Ftms(client, Telemetry())
        client.ftms = ftms
        self.assertEqual(await ftms.target(0), 0)
        self.assertEqual(client.calls, [b"\x08\x01"])

    async def test_rejected_target_never_starts(self):
        client = FakeClient(4)
        ftms = Ftms(client, Telemetry())
        client.ftms = ftms
        with self.assertRaises(RuntimeError):
            await ftms.target(200)
        self.assertEqual(len(client.calls), 1)

    async def test_out_of_range_never_sent(self):
        client = FakeClient()
        ftms = Ftms(client, Telemetry())
        client.ftms = ftms
        with self.assertRaises(ValueError):
            await ftms.target(1000)
        self.assertEqual(client.calls, [])


class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_closed_object_retried_and_connections_released(self):
        import threading
        from unittest.mock import AsyncMock, patch

        from bridge import FTMS, trainer_connection

        clients = []

        class Client:
            def __init__(self, address, **kwargs):
                self.kwargs = kwargs
                self.closed = False
                clients.append(self)

            async def connect(self):
                if len(clients) == 1:
                    raise OSError(-2147483629, "Object closed")

            async def disconnect(self):
                self.closed = True

        with patch("bridge.asyncio.sleep", new_callable=AsyncMock):
            async with trainer_connection(
                "trainer", threading.Event(), lambda _: None, asyncio.Event(), Client
            ) as client:
                self.assertIs(client, clients[1])
                self.assertTrue(clients[0].closed)
                self.assertEqual(client.kwargs["services"], [FTMS])
                self.assertFalse(client.kwargs["winrt"]["use_cached_services"])
        self.assertTrue(clients[1].closed)

    async def test_other_errors_not_retried(self):
        import threading

        from bridge import trainer_connection

        clients = []

        class Client:
            def __init__(self, *args, **kwargs):
                self.closed = False
                clients.append(self)

            async def connect(self):
                raise OSError(5, "Access denied")

            async def disconnect(self):
                self.closed = True

        with self.assertRaises(OSError):
            async with trainer_connection(
                "trainer", threading.Event(), lambda _: None, asyncio.Event(), Client
            ):
                self.fail("Connection must fail")
        self.assertEqual(len(clients), 1)
        self.assertTrue(clients[0].closed)


class UsbLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_operations_share_one_usb_thread(self):
        import threading
        from unittest.mock import patch

        from bridge import AntSession

        threads = []

        class Device:
            def __init__(self, device_id):
                threads.append(threading.get_ident())

            def read(self):
                threads.append(threading.get_ident())
                return []

            def broadcast(self, page):
                threads.append(threading.get_ident())

            def close(self):
                threads.append(threading.get_ident())

        with patch("bridge.Ant", Device):
            session = await AntSession().open(53001)
            await session.read()
            await session.broadcast(b"12345678")
            await session.close()
        self.assertEqual(len(set(threads)), 1)
        self.assertNotEqual(threads[0], threading.get_ident())

    async def test_cleanup_disposes_even_if_release_fails(self):
        from types import SimpleNamespace
        from unittest.mock import Mock

        from bridge import Ant

        ant = Ant.__new__(Ant)
        ant.opened = False
        ant.claimed = True
        ant.interface = 0
        ant.dev = object()
        release = Mock(side_effect=RuntimeError("release failed"))
        dispose = Mock()
        ant.usb = SimpleNamespace(
            util=SimpleNamespace(release_interface=release, dispose_resources=dispose)
        )
        with self.assertRaises(RuntimeError):
            ant.close()
        dispose.assert_called_once_with(ant.dev)


if __name__ == "__main__":
    unittest.main()
