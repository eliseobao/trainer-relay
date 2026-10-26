"""Wire formats for Bluetooth FTMS and ANT+ FE-C (little endian)."""

import struct
import time
from dataclasses import dataclass


@dataclass
class Telemetry:
    power: int | None = None
    cadence: float | None = None
    speed: float | None = None  # km/h
    updated: float = 0


@dataclass(frozen=True)
class ControlRequest:
    page: int
    mode: str
    value: float | None = None
    rolling: float | None = None
    wind: tuple[float, float, float] | None = None  # m/s, coefficient, drafting factor


def indoor_bike(data, state):
    flags = struct.unpack_from("<H", data)[0]
    offset = 2

    def take(fmt):
        nonlocal offset
        value = struct.unpack_from("<" + fmt, data, offset)[0]
        offset += struct.calcsize("<" + fmt)
        return value

    # Parse into a copy so a truncated packet cannot partially update state.
    values = {}
    if not flags & 1:
        values["speed"] = take("H") / 100
    if flags & 2:
        take("H")
    if flags & 4:
        values["cadence"] = take("H") / 2
    if flags & 8:
        take("H")
    if flags & 16:
        if len(data) < offset + 3:
            raise ValueError("Truncated distance")
        offset += 3
    if flags & 32:
        take("h")
    if flags & 64:
        values["power"] = take("h")
    if flags & 128:
        take("h")
    if flags & 256:
        take("H")
        take("H")
        take("B")
    if flags & 512:
        take("B")
    if flags & 1024:
        take("B")
    if flags & 2048:
        take("H")
    if flags & 4096:
        take("H")
    for key, value in values.items():
        setattr(state, key, value)
    state.updated = time.monotonic()


def frame(message, payload):
    packet = bytes([0xA4, len(payload), message]) + bytes(payload)
    checksum = 0
    for b in packet:
        checksum ^= b
    return packet + bytes([checksum])


class Frames:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        while self.buffer:
            if self.buffer[0] != 0xA4:
                del self.buffer[0]
                continue
            if len(self.buffer) < 4:
                return
            size = self.buffer[1] + 4
            if len(self.buffer) < size:
                return
            packet = self.buffer[:size]
            checksum = 0
            for b in packet:
                checksum ^= b
            if checksum:
                del self.buffer[0]
                continue
            del self.buffer[:size]
            yield packet[2], bytes(packet[3:-1])


class Fec:
    def __init__(self, device_id=53001, capabilities=2):
        self.device_id = device_id
        self.capabilities = capabilities
        self.count = self.event = self.accumulated = 0
        self.started = self.last = time.monotonic()
        self.distance = 0.0
        self.status = bytes([71, 255, 255, 255, 255, 255, 255, 255])
        self.sequence = 255
        self.pending = []

    def command_status(self, page, status, data):
        self.sequence = 0 if self.sequence >= 254 else self.sequence + 1
        self.status = bytes([71, page, self.sequence, status]) + bytes(data[4:8])

    def result(self, status):
        self.status = self.status[:3] + bytes([status]) + self.status[4:]
        self.pending.append(self.status)

    def common(self, page):
        if page == 54:
            return struct.pack("<B4BHB", 54, 255, 255, 255, 255, 0xFFFF, self.capabilities)
        if page == 71:
            return self.status
        if page == 80:
            return struct.pack("<BBBBHH", 80, 255, 255, 1, 255, 1)  # development manufacturer
        if page == 81:
            return struct.pack("<BBBBI", 81, 255, 0, 1, self.device_id)

    def receive(self, data):
        if len(data) != 8:
            return None
        page = data[0]
        if page == 70 and data[7] == 1:
            reply = self.common(data[6])
            if reply:
                self.pending.extend([reply] * min(10, max(1, data[5] & 0x7F)))
        elif page in (48, 49, 50, 51):
            required = {48: 1, 49: 2, 50: 4, 51: 4}[page]
            if not self.capabilities & required:
                self.command_status(page, 2, data)
                return None
            request = None
            if page == 49:
                raw = struct.unpack_from("<H", data, 6)[0]
                if raw != 0xFFFF:
                    request = ControlRequest(page, "erg", raw / 4)
            elif page == 48:
                if data[7] <= 200:
                    request = ControlRequest(page, "resistance", data[7] / 2)
            elif page == 51:
                raw = struct.unpack_from("<H", data, 5)[0]
                if raw <= 40000 or raw == 0xFFFF:
                    grade = None if raw == 0xFFFF else raw / 100 - 200
                    rolling = 0.004 if data[7] == 255 else data[7] * 0.00005
                    request = ControlRequest(page, "simulation", grade, rolling)
            else:
                coefficient = 0.51 if data[5] == 255 else data[5] * 0.01
                speed = 0 if data[6] == 255 else (data[6] - 127) / 3.6
                drafting = 1 if data[7] == 255 else data[7] * 0.01
                if 0 <= drafting <= 1:
                    request = ControlRequest(
                        page, "simulation", wind=(speed, coefficient, drafting)
                    )
            self.command_status(page, 4 if request else 3, data)
            return request
        elif page == 55:
            self.command_status(page, 2, data)  # User mass/configuration has no FTMS mapping here.

        return None

    def next_page(self, state):
        now = time.monotonic()
        fresh = now - state.updated < 5
        speed = state.speed if fresh else None
        self.distance += max(0, speed or 0) / 3.6 * (now - self.last)
        self.last = now
        n = self.count % 132
        self.count += 1
        if self.pending:
            return self.pending.pop(0)
        if n in (64, 65):
            return self.common(80)
        if n in (130, 131):
            return self.common(81)
        if n % 3 == 0:
            return struct.pack(
                "<BBBBHBB",
                16,
                25,
                int((now - self.started) * 4) & 255,
                int(self.distance) & 255,
                0xFFFF if speed is None else min(65534, max(0, round(speed / 3.6 * 1000))),
                255,
                (0x30 if fresh else 0x20) | 4,
            )
        self.event = (self.event + 1) & 255
        power = state.power if fresh else None
        if power is not None:
            self.accumulated = (self.accumulated + max(0, power)) & 65535
        cadence = state.cadence if fresh else None
        return struct.pack(
            "<BBBHHB",
            25,
            self.event,
            255 if cadence is None else min(253, max(0, round(cadence))),
            self.accumulated,
            0xFFF if power is None else min(4093, max(0, power)),
            0x30 if fresh else 0x20,
        )
