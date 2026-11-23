"""Host side of the RED BOARD's independent challenge-response CZERO watchdog.

A heartbeat is renewed only AFTER fresh bench/servo acquisition and a verified
P145 update. Closing the port does not count as a hardware qualification.
"""
from __future__ import annotations

import re
import time

from .protocol import crc16


def wire_line(body):
    raw = body.encode("ascii")
    return raw + f" {crc16(raw):04X}\n".encode("ascii")


def parse_line(line):
    if len(line) > 64:
        raise ValueError("Watchdog frame too long")
    match = re.fullmatch(rb"(Q|ACK|OK|OFF) ([0-9A-F]{8}) ([0-9A-F]{4})\r?\n", line)
    if not match:
        raise ValueError("Watchdog frame syntax")
    body = match[1] + b" " + match[2]
    if crc16(body) != int(match[3], 16):
        raise ValueError("Watchdog CRC")
    return match[1].decode(), int(match[2], 16)


class Watchdog:
    def __init__(self, stream, clock=time.monotonic):
        self.stream, self.clock = stream, clock
        self.firmware_id=None
        self.trace=[]

    def _write(self,data):
        self.trace.append(dict(direction="out",host_monotonic=self.clock(),raw_hex=data.hex()))
        if self.stream.write(data)!=len(data):raise RuntimeError("Watchdog partial write")

    def _read(self):
        line=self.stream.readline(65)
        self.trace.append(dict(direction="in",host_monotonic=self.clock(),raw_hex=line.hex()))
        return line

    def identify(self,expected_id):
        self.firmware_id=None
        if expected_id!="RNRWD_AT32F403RC_20261122":
            raise RuntimeError("Unqualified red-board firmware identity")
        self.stream.reset_input_buffer()
        self._write(b"HELLO\n")  # always removes permit; never a torque command
        deadline=self.clock()+.6
        while self.clock()<deadline:
            line=self._read()
            if line.startswith(b"Q "):continue
            match=re.fullmatch(rb"(ID [A-Z0-9_]{1,40}) ([0-9A-F]{4})\r?\n",line)
            if not match or crc16(match[1])!=int(match[2],16):
                raise RuntimeError("Red-board firmware ID missing or CRC invalid")
            actual=match[1][3:].decode("ascii")
            if actual!=expected_id:raise RuntimeError("Wrong red-board firmware image")
            self.firmware_id=actual
            return actual
        raise RuntimeError("Red-board firmware identification timeout")

    def renew(self):
        if self.firmware_id is None:
            raise RuntimeError("Red-board firmware has not been identified")
        self.stream.reset_input_buffer()
        deadline = self.clock() + .25
        while self.clock() < deadline:
            line = self._read()
            if line.startswith(b"T3D-WD"):
                continue
            kind, nonce = parse_line(line)
            if kind != "Q":
                continue
            answer = wire_line(f"ACK {nonce:08X}")
            self._write(answer)
            while self.clock() < deadline:
                reply = self._read()
                kind2, nonce2 = parse_line(reply)
                if kind2 == "OK" and nonce2 == nonce:
                    return nonce
                if kind2 == "Q":
                    break
        raise RuntimeError("Watchdog renewal not acknowledged")

    def disarm(self):
        # Always-safe command; does not enable anything and needs no nonce.
        self.stream.reset_input_buffer()
        self._write(b"STOP\n")
        deadline = self.clock() + .3
        while self.clock() < deadline:
            kind, value = parse_line(self._read())
            if kind == "OFF" and value == 0:
                return
        raise RuntimeError("Watchdog STOP not acknowledged")
