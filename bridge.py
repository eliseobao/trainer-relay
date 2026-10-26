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


class FtmsRejected(RuntimeError):
    def __init__(self, opcode, result):
        self.opcode, self.result = opcode, result
        names = {
            0: "control request",
            4: "resistance",
            5: "power target",
            7: "start",
            8: "stop",
            17: "slope",
        }
        reasons = {
            2: "not supported",
            3: "invalid parameter",
            4: "operation failed",
            5: "control not permitted",
        }
        super().__init__(
            f"Trainer rejected {names.get(opcode, f'command {opcode:02x}')}: {reasons.get(result, f'result {result}')}"
        )


class Ftms:
    def __init__(self, client, state):
        self.client, self.state = client, state
        self.waiter = None
        self.lock = asyncio.Lock()
        self.minimum, self.maximum, self.increment = 0, MAX_POWER, 1
        self.features = 8
        self.resistance_range = None
        self.resistance_format = "h"
        self.simulation_parameters = (
            0.0,
            0.0,
            0.004,
            0.51,
            1.0,
        )  # wind, grade, rolling, drag, drafting
        self.mode = None
        self.controlled = False

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
                    raise FtmsRejected(opcode, result)
            finally:
                self.waiter = None

    async def initialize(self):
        for characteristic in (BIKE, CONTROL, FEATURE):
            if not self.client.services.get_characteristic(characteristic):
                raise RuntimeError(f"Trainer missing required FTMS characteristic {characteristic}")
        features = await self.client.read_gatt_char(FEATURE)
        if len(features) != 8:
            raise RuntimeError("Trainer returned invalid FTMS feature data")
        self.features = struct.unpack_from("<I", features, 4)[0]
        if self.features & 8 and self.client.services.get_characteristic(RANGE):
            self.minimum, self.maximum, self.increment = struct.unpack(
                "<hhH", await self.client.read_gatt_char(RANGE)
            )
            self.minimum = max(0, self.minimum)
            self.maximum = min(MAX_POWER, self.maximum)
            self.increment = max(1, self.increment)
            if self.maximum < self.minimum:
                raise RuntimeError("Trainer returned an invalid power range")
        resistance_characteristic = uuid("2ad6")
        if self.features & 4 and self.client.services.get_characteristic(resistance_characteristic):
            low, high, step = struct.unpack(
                "<hhH", await self.client.read_gatt_char(resistance_characteristic)
            )
            if low < high and step > 0:
                self.resistance_range = (low, high, step)
            else:
                log.warning("Invalid resistance range: resistance mode disabled")
        if not self.fec_capabilities:
            raise RuntimeError(
                "Trainer exposes no usable power, resistance, or simulation controls"
            )
        log.info(
            "FTMS features %s; resistance range (raw tenths) %s",
            bytes(features).hex(),
            self.resistance_range,
        )
        await self.client.start_notify(CONTROL, self.indication)
        await self.client.start_notify(BIKE, self.notification)
        await self.command(0)
        self.controlled = True
        log.info(
            "FTMS control acquired. Power range %s..%s W, step %s W",
            self.minimum,
            self.maximum,
            self.increment,
        )

    @property
    def fec_capabilities(self):
        return (
            (2 if self.features & 8 else 0)
            | (1 if self.features & 4 and self.resistance_range else 0)
            | (4 if self.features & (1 << 13) else 0)
        )

    @property
    def description(self):
        modes = []
        if self.fec_capabilities & 2:
            modes.append(f"ERG {self.minimum}–{self.maximum} W")
        if self.fec_capabilities & 1:
            modes.append("Resistance")
        if self.fec_capabilities & 4:
            modes.append("Slope")
        return " · ".join(modes)

    async def apply(self, request):
        if request.mode == "erg":
            return await self.target(request.value), "ERG", "W"
        if request.mode == "resistance":
            return await self.resistance(request.value), "Resistance", "%"
        if request.mode == "simulation":
            return await self.simulate(request), "Slope", "%"
        raise NotImplementedError(f"Unknown trainer mode: {request.mode}")

    async def start_control(self):
        try:
            await self.command(7)
        except FtmsRejected as exc:
            # The target write may already have changed the brake. Stop this session
            # rather than keep controlling a trainer that could not start its mode.
            raise RuntimeError(
                "Trainer could not start the control mode. Stop and reconnect."
            ) from exc

    async def resistance(self, percent):
        if not self.fec_capabilities & 1:
            raise NotImplementedError("Trainer does not expose a usable resistance range")
        if not 0 <= percent <= 100:
            raise ValueError("Resistance must be between 0 and 100%")
        low, high, step = self.resistance_range
        raw = low + round((high - low) * percent / 100 / step) * step
        raw = max(low, min(low + ((high - low) // step) * step, raw))
        if self.resistance_format == "B" and not 0 <= raw <= 255:
            raise ValueError("Resistance exceeds the trainer's legacy one-byte format")
        try:
            await self.command(4, struct.pack("<" + self.resistance_format, raw))
        except FtmsRejected as exc:
            # Old FTMS 1.0 implementations accept UINT8 rather than corrected SINT16.
            # Retry only a parameter rejection, within the advertised range, before start.
            if self.resistance_format != "h" or exc.result != 3 or not 0 <= raw <= 255:
                raise
            await self.command(4, bytes([raw]))
            self.resistance_format = "B"
            log.info("Trainer accepted legacy UINT8 resistance format")
        await self.start_control()
        self.mode = "resistance"
        accepted = (raw - low) / (high - low) * 100
        log.info("Resistance accepted: %.1f%% (native %.1f)", accepted, raw / 10)
        return round(accepted, 1)

    async def simulate(self, request):
        if not self.fec_capabilities & 4:
            raise NotImplementedError("Trainer does not advertise indoor-bike simulation")
        wind, grade, rolling, drag, drafting = self.simulation_parameters
        if request.wind is not None:
            wind, drag, drafting = request.wind
        if request.value is not None:
            grade = request.value
        if request.rolling is not None:
            rolling = request.rolling
        speed_raw, grade_raw = round(wind * 1000), round(grade * 100)
        rolling_raw, drag_raw = round(rolling * 10000), round(drag * drafting * 100)
        if not (
            -32768 <= speed_raw <= 32767
            and -32768 <= grade_raw <= 32767
            and 0 <= rolling_raw <= 255
            and 0 <= drag_raw <= 255
        ):
            raise ValueError("Simulation parameters exceed the Bluetooth FTMS encoding range")
        if self.mode != "simulation" and (request.page == 50 or request.value is None):
            # Road settings configure simulation; only a valid grade selects that mode.
            # Sending FTMS 0x11 here would unexpectedly end ERG or basic resistance.
            self.simulation_parameters = (wind, grade, rolling, drag, drafting)
            log.info("Road settings saved for the next slope target")
            return None
        await self.command(0x11, struct.pack("<hhBB", speed_raw, grade_raw, rolling_raw, drag_raw))
        await self.start_control()
        self.simulation_parameters = (wind, grade, rolling, drag, drafting)
        self.mode = "simulation"
        log.info(
            "Slope accepted: %.2f%%; wind %.3f m/s, rolling %.5f, drag %.2f, drafting %.2f",
            grade,
            wind,
            rolling,
            drag,
            drafting,
        )
        return round(grade, 2)

    async def target(self, watts):
        if not self.features & 8:
            raise NotImplementedError("Trainer does not advertise ERG support")
        if watts == 0:
            await self.command(8, b"\x01")
            self.mode = None
            log.info("Cycling computer requested zero power: trainer stopped")
            return 0
        if not self.minimum <= watts <= self.maximum:
            raise ValueError(
                f"Target {watts:g} W outside supported {self.minimum}..{self.maximum} W"
            )
        watts = self.minimum + round((watts - self.minimum) / self.increment) * self.increment
        ceiling = self.minimum + ((self.maximum - self.minimum) // self.increment) * self.increment
        watts = min(ceiling, watts)
        await self.command(5, struct.pack("<h", watts))
        await self.start_control()
        self.mode = "erg"
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
            fec.capabilities = ftms.fec_capabilities
            report(("link", "bluetooth", "Connected"))
            report(("link", "ant", "Opening"))
            ant = await AntSession().open(device_id)
            await ant.broadcast(fec.next_page(state))
            report(("link", "ant", "Broadcasting"))
            report(("ready", device_id, ftms.description))
            commands = asyncio.Queue(maxsize=32)

            async def control_worker():
                while not stop.is_set():
                    request, sequence = await commands.get()
                    try:
                        accepted, mode, unit = await ftms.apply(request)
                        if fec.sequence == sequence:
                            fec.result(0)
                        if accepted is None:
                            report(("settings", "Road settings saved for the next slope target."))
                        else:
                            report(("target", accepted, mode, unit))
                    except (ValueError, NotImplementedError, FtmsRejected) as exc:
                        if isinstance(exc, NotImplementedError):
                            status = 2
                        elif isinstance(exc, FtmsRejected):
                            status = {2: 2, 3: 3}.get(exc.result, 1)
                        else:
                            status = 3
                        if fec.sequence == sequence:
                            fec.result(status)
                        report(("command_error", str(exc)))
                        log.warning("Control rejected: %s", exc)
                    except Exception:
                        if fec.sequence == sequence:
                            fec.result(1)
                        log.exception("Trainer control failed")
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
                            previous_sequence = fec.sequence
                            request = fec.receive(payload[1:9])
                            if (
                                request is None
                                and fec.sequence != previous_sequence
                                and payload[1] in (48, 49, 50, 51)
                            ):
                                mode = {
                                    48: "resistance",
                                    49: "ERG",
                                    50: "slope",
                                    51: "slope",
                                    55: "user configuration",
                                }.get(payload[1], "control")
                                reason = (
                                    "not supported by this connection"
                                    if fec.status[3] == 2
                                    else "invalid parameters"
                                )
                                report(("command_error", f"{mode.capitalize()} request: {reason}"))
                            if request is not None:
                                # Sequence numbers keep status associated with the latest cycling-computer target.
                                if worker.done():
                                    await worker
                                if fec.status[3] == 4:
                                    try:
                                        commands.put_nowait((request, fec.sequence))
                                    except asyncio.QueueFull:
                                        fec.result(1)
                                        report(
                                            (
                                                "command_error",
                                                "Trainer is busy. Try the target again shortly.",
                                            )
                                        )
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
                if client.is_connected and ftms.controlled:
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
