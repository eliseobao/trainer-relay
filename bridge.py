import asyncio
import logging
import os
import struct
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from app_info import APP_NAME, MAX_POWER, TRAINER_ID, VERSION
from protocol import Fec, Frames, Telemetry, frame, indoor_bike


def uuid(short):
    return f"0000{short}-0000-1000-8000-00805f9b34fb"


FTMS, BIKE, CONTROL, FEATURE, RANGE = map(uuid, ["1826", "2ad2", "2ad9", "2acc", "2ad8"])
log = logging.getLogger("bridge")


class Ant:
    def __init__(self, device_id):
        import usb.backend.libusb0
        import usb.core
        import usb.util

        self.usb = usb
        backend = usb.backend.libusb0.get_backend(
            find_library=lambda _: str(
                Path(os.environ.get("WINDIR", "C:/Windows")) / "System32/libusb0.dll"
            )
        )
        self.dev = usb.core.find(idVendor=0x0FCF, idProduct=0x1008, backend=backend)
        if self.dev is None:
            self.dev = usb.core.find(idVendor=0x0FCF, idProduct=0x1009, backend=backend)
        if self.dev is None:
            raise RuntimeError(
                "ANT USB stick not found. Close Garmin Express and other training apps."
            )
        self.parser = Frames()
        self.claimed = False
        self.opened = False
        try:
            self.dev.set_configuration()
            intf = self.dev.get_active_configuration()[(0, 0)]
            usb.util.claim_interface(self.dev, intf.bInterfaceNumber)
            self.claimed = True
            self.interface = intf.bInterfaceNumber
            self.epin = next(
                ep
                for ep in intf
                if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN
            )
            self.epout = next(
                ep
                for ep in intf
                if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_OUT
            )
            self.send(0x4A, b"\0")
            time.sleep(0.6)
            self.read()
            self.configure(0x46, b"\0" + bytes.fromhex("b9a521fbbd72c345"))
            self.configure(0x42, bytes([0, 0x10, 0]))
            self.configure(0x51, struct.pack("<BHBB", 0, device_id, 17, 5))
            self.configure(0x45, bytes([0, 57]))
            self.configure(0x43, struct.pack("<BH", 0, 8192))
            self.configure(0x4B, b"\0")
            self.opened = True
            log.info("ANT FE-C channel open, trainer ID %s", device_id)
        except BaseException:
            self.close()
            raise

    def send(self, message, payload):
        self.epout.write(frame(message, payload), timeout=1000)

    def read(self):
        try:
            return list(self.parser.feed(bytes(self.epin.read(512, timeout=1000))))
        except self.usb.core.USBError as exc:
            # libusb-win32 reports timeouts as a generic USBError.
            if isinstance(exc, self.usb.core.USBTimeoutError) or "timeout" in str(exc).lower():
                return []
            raise

    def configure(self, message, payload):
        self.send(message, payload)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            for mid, data in self.read():
                if mid == 0x40 and len(data) == 3 and data[1] == message:
                    if data[2]:
                        raise RuntimeError(f"ANT setup {message:02x} rejected: {data[2]:02x}")
                    return
        raise TimeoutError(f"ANT setup {message:02x} timed out")

    def broadcast(self, page):
        self.send(0x4E, b"\0" + page)

    def close(self):
        try:
            if self.opened:
                self.send(0x4C, b"\0")
                deadline = time.monotonic() + 2
                closed = False
                while time.monotonic() < deadline and not closed:
                    for mid, data in self.read():
                        if mid == 0x40 and data == b"\0\x01\x07":
                            closed = True
                if closed:
                    self.configure(0x41, b"\0")
                self.opened = False
        except Exception:
            log.exception("ANT shutdown")
        finally:
            try:
                if self.claimed:
                    self.usb.util.release_interface(self.dev, self.interface)
                    self.claimed = False
            finally:
                self.usb.util.dispose_resources(self.dev)


class AntSession:
    """Keep every operation on the old USB driver on one owning thread."""

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ANT-USB")
        self.device = None

    async def call(self, function, *args):
        return await asyncio.get_running_loop().run_in_executor(self.executor, function, *args)

    async def open(self, device_id):
        try:
            self.device = await self.call(Ant, device_id)
        except BaseException:
            self.executor.shutdown(wait=True)
            raise
        return self

    async def read(self):
        return await self.call(self.device.read)

    async def broadcast(self, page):
        await self.call(self.device.broadcast, page)

    async def close(self):
        try:
            await self.call(self.device.close)
        finally:
            self.executor.shutdown(wait=True)


async def scan():
    from bleak import BleakScanner

    found = await BleakScanner.discover(timeout=10, return_adv=True)
    result = []
    for device, adv in found.values():
        name = adv.local_name or device.name or "Unnamed"
        log.info("BLE %s %s services=%s", name, device.address, adv.service_uuids)
        if FTMS in adv.service_uuids or any(
            x in name.lower() for x in ("magene", "van rysel", "d100", "t110")
        ):
            result.append((name, device.address))
    return result


class Ftms:
    def __init__(self, client, state):
        self.client, self.state = client, state
        self.waiter = None
        self.lock = asyncio.Lock()
        self.minimum, self.maximum, self.increment = 0, MAX_POWER, 1

    def indication(self, _, data):
        log.info("FTMS response %s", bytes(data).hex())
        if len(data) >= 3 and data[0] == 0x80 and self.waiter and data[1] == self.waiter[0]:
            if not self.waiter[1].done():
                self.waiter[1].set_result(data[2])

    def notification(self, _, data):
        try:
            indoor_bike(data, self.state)
        except (ValueError, struct.error):
            log.warning("Malformed Indoor Bike Data %s", bytes(data).hex())

    async def command(self, opcode, payload=b""):
        async with self.lock:
            future = asyncio.get_running_loop().create_future()
            self.waiter = opcode, future
            try:
                await self.client.write_gatt_char(CONTROL, bytes([opcode]) + payload, response=True)
                result = await asyncio.wait_for(future, 5)
                if result != 1:
                    raise RuntimeError(f"FTMS command {opcode:02x} rejected (result {result})")
            finally:
                self.waiter = None

    async def initialize(self):
        for characteristic in (BIKE, CONTROL, FEATURE):
            if not self.client.services.get_characteristic(characteristic):
                raise RuntimeError(f"Trainer missing required FTMS characteristic {characteristic}")
        features = await self.client.read_gatt_char(FEATURE)
        if len(features) < 8 or not struct.unpack_from("<I", features, 4)[0] & 8:
            raise RuntimeError("Trainer does not advertise FTMS target power (ERG) support")
        if self.client.services.get_characteristic(RANGE):
            self.minimum, self.maximum, self.increment = struct.unpack(
                "<hhH", await self.client.read_gatt_char(RANGE)
            )
            self.minimum = max(0, self.minimum)
            self.maximum = min(MAX_POWER, self.maximum)
            self.increment = max(1, self.increment)
        await self.client.start_notify(CONTROL, self.indication)
        await self.client.start_notify(BIKE, self.notification)
        await self.command(0)
        log.info(
            "FTMS control acquired. Power range %s..%s W, step %s W",
            self.minimum,
            self.maximum,
            self.increment,
        )

    async def target(self, watts):
        if watts == 0:
            await self.command(8, b"\x01")
            log.info("Cycling computer requested zero power: trainer stopped")
            return 0
        if not self.minimum <= watts <= self.maximum:
            raise ValueError(
                f"Target {watts:g} W outside supported {self.minimum}..{self.maximum} W"
            )
        watts = self.minimum + round((watts - self.minimum) / self.increment) * self.increment
        watts = min(self.maximum, watts)
        await self.command(5, struct.pack("<h", watts))
        await self.command(7)
        log.info("ERG target accepted by trainer: %s W", watts)
        return watts


@asynccontextmanager
async def trainer_connection(address, stop, report, disconnected, client_factory=None):
    if client_factory is None:
        from bleak import BleakClient

        client_factory = BleakClient
    for attempt in range(3):
        if stop.is_set():
            raise RuntimeError("Connection cancelled")
        client = client_factory(
            address,
            disconnected_callback=lambda _: disconnected.set(),
            timeout=25,
            services=[FTMS],
            winrt={"use_cached_services": False},
        )
        try:
            await client.connect()
        except OSError as exc:
            try:
                await client.disconnect()
            except Exception:
                log.exception("Cleanup after failed Bluetooth connection")
            code = getattr(exc, "winerror", None)
            if code is None and exc.args:
                code = exc.args[0]
            if code not in (-2147483629, 2147483667) or attempt == 2:
                raise
            log.warning("Windows closed GATT object during discovery; retry %s/2", attempt + 1)
            report("Windows interrupted Bluetooth service discovery. Retrying…")
            await asyncio.sleep(1)
            continue
        except BaseException:
            try:
                await client.disconnect()
            except Exception:
                log.exception("Bluetooth connection cleanup")
            raise
        disconnected.clear()
        try:
            yield client
        finally:
            await client.disconnect()
        return


async def run_bridge(address, stop, report, device_id=TRAINER_ID):
    state, fec = Telemetry(), Fec(device_id)
    disconnected = asyncio.Event()
    ant = None
    report(("link", "bluetooth", "Connecting"))
    async with trainer_connection(address, stop, report, disconnected) as client:
        ftms = Ftms(client, state)
        try:
            await ftms.initialize()
            report(("link", "bluetooth", "Connected"))
            report(("link", "ant", "Opening"))
            ant = await AntSession().open(device_id)
            await ant.broadcast(fec.next_page(state))
            report(("link", "ant", "Broadcasting"))
            report(("ready", device_id, ftms.minimum, ftms.maximum))
            commands = asyncio.Queue(maxsize=32)

            async def control_worker():
                while True:
                    watts, sequence = await commands.get()
                    try:
                        accepted = await ftms.target(watts)
                        if fec.sequence == sequence:
                            fec.result(0)
                        report(("target", accepted))
                    except ValueError as exc:
                        if fec.sequence == sequence:
                            fec.result(3)
                        report(str(exc))
                        log.warning("%s", exc)
                    except Exception as exc:
                        if fec.sequence == sequence:
                            fec.result(1)
                        report(f"ERG failed: {exc}")
                        log.exception("ERG command failed")
                        raise

            worker = asyncio.create_task(control_worker())
            try:
                last_report = 0
                while not stop.is_set():
                    if disconnected.is_set():
                        raise RuntimeError(
                            "Bluetooth disconnected. Bridge stopped; reconnect before continuing workout."
                        )
                    if worker.done():
                        await worker
                    for mid, payload in await ant.read():
                        if mid == 0x40 and len(payload) == 3 and payload[:2] == b"\0\x01":
                            if payload[2] == 3:
                                await ant.broadcast(fec.next_page(state))
                            elif payload[2] == 7:
                                raise RuntimeError("ANT channel closed")
                        elif mid in (0x4E, 0x4F) and len(payload) >= 9 and payload[0] & 31 == 0:
                            report(("link", "computer", "Signal received"))
                            log.info("ANT RX %s", payload[1:9].hex())
                            watts = fec.receive(payload[1:9])
                            if watts is not None:
                                # Sequence numbers keep status associated with the latest cycling-computer target.
                                if worker.done():
                                    await worker
                                if fec.status[3] == 4:
                                    try:
                                        commands.put_nowait((watts, fec.sequence))
                                    except asyncio.QueueFull:
                                        fec.result(1)
                    if time.monotonic() - last_report > 1:
                        report(
                            (
                                "telemetry",
                                state.power,
                                state.cadence,
                                state.speed,
                                time.monotonic() - state.updated,
                            )
                        )
                        last_report = time.monotonic()
            finally:
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
        finally:
            try:
                if client.is_connected:
                    await ftms.command(8, b"\x01")
            except Exception:
                log.exception("Trainer stop failed")
            if ant:
                await ant.close()


def gui():
    from interface import BridgeWindow

    BridgeWindow(scan, run_bridge, LOG_PATH).run()


LOG_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "TrainerBridge"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "bridge.log"


def main():
    from logging.handlers import RotatingFileHandler

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        ],
    )
    if "--version" in sys.argv:
        print(f"{APP_NAME} {VERSION}")
    elif "--preview" in sys.argv:
        from interface import BridgeWindow

        BridgeWindow(scan, run_bridge, LOG_PATH, preview=True).run()
    elif "--scan" in sys.argv:
        print(asyncio.run(scan()))
    elif "--ant-test" in sys.argv:
        ant = Ant(53001)
        try:
            fec, state = Fec(), Telemetry()
            ant.broadcast(fec.next_page(state))
            deadline = time.monotonic() + 3
            events = 0
            while time.monotonic() < deadline:
                for mid, data in ant.read():
                    if mid == 0x40 and data == b"\0\x01\x03":
                        events += 1
                        ant.broadcast(fec.next_page(state))
            print(f"ANT FE-C radio verified: {events} transmission events")
            if not events:
                raise RuntimeError("No ANT transmissions")
        finally:
            ant.close()
    else:
        gui()


if __name__ == "__main__":
    main()
