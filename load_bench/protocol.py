"""HLTNC protocol: parameter numbers are DECIMAL addresses; status uses FC04.

Source: manufacturer Modbus description (cover V3.3), PDF pp. 7, 9-16.
Runtime writes are deliberately restricted to volatile P-145. No enable, alarm
clear, EEPROM-save, encoder-zero or JOG command is implemented here.
"""
from __future__ import annotations

import re
import struct
import time


class ProtocolError(RuntimeError):
    pass


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def frame(payload: bytes) -> bytes:
    return payload + struct.pack("<H", crc16(payload))


def i16(value: int) -> int:
    return value - 65536 if value & 0x8000 else value


def i32(lo: int, hi: int) -> int:
    value = lo | (hi << 16)
    return value - 2**32 if value & 0x80000000 else value


def verify_crc(raw: bytes) -> bytes:
    if len(raw) < 5 or crc16(raw[:-2]) != int.from_bytes(raw[-2:], "little"):
        raise ProtocolError("Bad/truncated RTU frame or CRC")
    return raw[:-2]


def read_request(unit: int, function: int, start: int, count: int) -> bytes:
    if not 1 <= unit <= 32 or function not in (3, 4) or not 1 <= count <= 8:
        raise ValueError("T3D requires unit 1..32 and at most 8 registers/read")
    if not 0 <= start <= 65535 or start + count > 65536:
        raise ValueError("Address range")
    return frame(struct.pack(">BBHH", unit, function, start, count))


def torque_request(unit: int, percent: int, cap_percent: int) -> bytes:
    if type(percent) is not int or not 0 <= cap_percent <= 100:
        raise ValueError("Integer torque and bounded cap required")
    if not 1 <= unit <= 32 or abs(percent) > cap_percent:
        raise ValueError("Torque exceeds permitted envelope")
    return frame(struct.pack(">BBHH", unit, 6, 145, percent & 0xFFFF))


def parse_reply(request: bytes, reply: bytes) -> list[int]:
    payload = verify_crc(reply)
    unit, function = request[:2]
    if payload[0] != unit:
        raise ProtocolError("Wrong slave address")
    if payload[1] == function | 0x80:
        if len(payload) != 3:
            raise ProtocolError("Malformed exception")
        raise ProtocolError(f"T3D exception {payload[2]:02x} for FC{function:02x}")
    if payload[1] != function:
        raise ProtocolError("Wrong function")
    if function == 6:
        if reply != request:
            raise ProtocolError("Write echo differs from request")
        return []
    count = int.from_bytes(request[4:6], "big")
    if len(payload) != 3 + count * 2 or payload[2] != count * 2:
        raise ProtocolError("Wrong byte count")
    return list(struct.unpack(">" + "H" * count, payload[3:]))


def open_identified_serial(identity: dict, baud: int, parity: str, timeout: float):
    """Explicit identity only: never guess a COM port or open the plotter."""
    import serial
    from serial.tools import list_ports

    port = identity.get("port")
    if not isinstance(port, str) or not re.fullmatch(r"COM[1-9][0-9]*|/dev/[A-Za-z0-9_./-]+", port):
        raise ValueError("Set an explicit physical port in the configuration")
    if type(identity.get("vid")) is not int or type(identity.get("pid")) is not int:
        raise ValueError("USB VID/PID are required")
    if not identity.get("serial_number") and not identity.get("location"):
        raise ValueError("USB serial number or physical USB location is required")
    found = [p for p in list_ports.comports() if p.device.casefold() == port.casefold()]
    if len(found) != 1:
        raise ValueError("Configured port absent or ambiguous")
    device = found[0]
    for key in ("vid", "pid", "serial_number", "location"):
        expected = identity.get(key)
        if expected is not None and getattr(device, key) != expected:
            raise ValueError(f"USB identity mismatch: {key}")
    stream = serial.Serial(port=None, baudrate=baud, parity=parity, stopbits=1,
                           timeout=timeout, write_timeout=timeout)
    stream.dtr = False
    stream.rts = False
    stream.port = port
    stream.open()
    return stream


class Rtu:
    def __init__(self, stream, unit=1, baud=19200, timeout=.12, clock=time.monotonic, sleep=time.sleep):
        if not 1 <= unit <= 32:
            raise ValueError("Invalid unit")
        self.stream, self.unit, self.timeout = stream, unit, timeout
        self.clock, self.sleep = clock, sleep
        self.gap = max(.00175, 3.5 * 11 / baud)
        self.last_end = -float("inf")
        self.trace = []

    def _exact(self, n, deadline):
        result = bytearray()
        while len(result) < n:
            if self.clock() >= deadline:
                raise ProtocolError("RTU receive deadline")
            data = self.stream.read(n-len(result))
            if not data:
                raise ProtocolError("RTU timeout/truncated response")
            result.extend(data)
        return bytes(result)

    def transact(self, request):
        self.sleep(max(0, self.gap - (self.clock() - self.last_end)))
        started = self.clock()
        response = b""
        error = None
        try:
            self.stream.reset_input_buffer()
            if self.stream.write(request) != len(request):
                raise ProtocolError("Partial RTU write")
            deadline = started + self.timeout
            head = self._exact(3, deadline)
            if head[1] & 0x80:
                response = head + self._exact(2, deadline)
            elif request[1] in (3, 4):
                if head[2] > 16 or head[2] % 2:
                    raise ProtocolError("Unbounded/odd RTU byte count")
                response = head + self._exact(head[2]+2, deadline)
            else:
                response = head + self._exact(5, deadline)
            result = parse_reply(request, response)
            if self.clock() > deadline:
                raise ProtocolError("Late response")
            return result
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            self.last_end = self.clock()
            self.trace.append(dict(start=started, end=self.last_end, request=request.hex(),
                                   response=response.hex(), error=error))

    def read(self, function, start, count=1):
        return self.transact(read_request(self.unit, function, start, count))

    def parameter(self, number):
        return i16(self.read(3, number)[0])

    def torque(self, percent, cap_percent):
        self.transact(torque_request(self.unit, percent, cap_percent))
        # The write echo alone is not a verified parameter update.
        if self.parameter(145) != percent:
            raise ProtocolError("P-145 readback mismatch")


PARAMETERS = (4, 26, 65, 66, 75, 77, 78, 98, 100, 101, 102, 103,
              108, 109, 110, 111, 120, 121, 122, 123, 124, 145, 146, 147, 148, 181, 182, 183)


def parameter_snapshot(rtu):
    return {str(p): rtu.parameter(p) for p in PARAMETERS}


def telemetry(rtu):
    start = rtu.clock()
    a = rtu.read(4, 0, 7)
    b = rtu.read(4, 9, 7)
    c = rtu.read(4, 0x12, 2)
    d = rtu.read(4, 0x17, 5)
    end = rtu.clock()
    return dict(rpm=i16(a[0]), position_raw=i32(a[5], a[6]),
                torque_percent=i16(b[0]), current_a=b[2] / 10,
                torque_command_percent=i16(b[6]), di_raw=c[0], do_raw=c[1],
                regen_load_percent=d[0], alarm=d[3], rpm_tenths=i16(d[4]) / 10,
                read_start_monotonic=start, read_end_monotonic=end,
                acquisition_span_s=end-start,
                # The manufacturer's DI word is HIGH/LOW, not normalized function state.
                # Electrical mapping is commissioned independently; do not infer active-low here.
                raw_blocks=[a, b, c, d])
