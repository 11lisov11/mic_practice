#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import time
from dataclasses import dataclass

import serial
from serial.tools import list_ports

FRAME_LEN = 32
CRC_OFF = FRAME_LEN - 1

CMD_HDR0 = 0xAA
CMD_HDR1 = 0x55
RSP_HDR0 = 0x55
RSP_HDR1 = 0xAA

FLAG_ENABLE = 0x01
FLAG_ESTOP = 0x02
FLAG_DIAG_PWM = 0x04
FLAG_CLEAR_FAULT = 0x08

MODE_OFF = 0
MODE_DIAG = 1
MODE_DUTY = 2
MODE_SCALAR = 3

STATUS_LINK_OK = 0x01
STATUS_ENABLED = 0x02
STATUS_ESTOP = 0x04
STATUS_FAULT = 0x08
STATUS_TIMEOUT = 0x10
STATUS_PWM_ACTIVE = 0x20

FAULT_MAP = {
    0: "OK",
    1: "ESTOP",
    2: "TIMEOUT",
    3: "BAD_CRC",
    4: "BAD_HDR",
    5: "INTERNAL",
    6: "OVERTEMP",
}


def crc_xor(frame: bytes | bytearray) -> int:
    crc = 0
    for b in frame[:CRC_OFF]:
        crc ^= b
    return crc & 0xFF


def q15_unit(value: float) -> int:
    value = max(0.0, min(1.0, float(value)))
    return int(value * 32767.0) & 0xFFFF


def build_cmd(seq: int, mode: int = MODE_OFF, flags: int = 0, du: int = 0, dv: int = 0, dw: int = 0) -> bytes:
    frame = bytearray(FRAME_LEN)
    frame[0] = CMD_HDR0
    frame[1] = CMD_HDR1
    frame[2] = 0x02
    frame[3] = flags & 0xFF
    frame[4] = mode & 0xFF
    frame[5] = seq & 0xFF
    frame[6] = du & 0xFF
    frame[7] = (du >> 8) & 0xFF
    frame[8] = dv & 0xFF
    frame[9] = (dv >> 8) & 0xFF
    frame[10] = dw & 0xFF
    frame[11] = (dw >> 8) & 0xFF
    frame[CRC_OFF] = crc_xor(frame)
    return bytes(frame)


def read_rsp(ser: serial.Serial, timeout_s: float) -> bytes | None:
    state = 0
    idx = 0
    buf = bytearray(FRAME_LEN)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        b = ser.read(1)
        if not b:
            continue
        v = b[0]
        if state == 0:
            if v == RSP_HDR0:
                buf[0] = v
                state = 1
        elif state == 1:
            if v == RSP_HDR1:
                buf[1] = v
                idx = 2
                state = 2
            elif v == RSP_HDR0:
                buf[0] = v
            else:
                state = 0
        else:
            buf[idx] = v
            idx += 1
            if idx >= FRAME_LEN:
                return bytes(buf)
    return None


def parse_rsp(rsp: bytes) -> dict:
    crc_ok = len(rsp) == FRAME_LEN and rsp[CRC_OFF] == crc_xor(rsp)
    status = rsp[3] if len(rsp) > 3 else 0
    fault = rsp[9] if len(rsp) > 9 else 255
    good = rsp[5] | (rsp[6] << 8) if len(rsp) > 6 else 0
    bad = rsp[7] | (rsp[8] << 8) if len(rsp) > 8 else 0
    return {
        "crc_ok": crc_ok,
        "seq": rsp[4] if len(rsp) > 4 else None,
        "status": status,
        "link_ok": bool(status & STATUS_LINK_OK),
        "enabled": bool(status & STATUS_ENABLED),
        "estop": bool(status & STATUS_ESTOP),
        "fault_active": bool(status & STATUS_FAULT),
        "timeout": bool(status & STATUS_TIMEOUT),
        "pwm_active": bool(status & STATUS_PWM_ACTIVE),
        "fault": fault,
        "fault_text": FAULT_MAP.get(fault, "UNKNOWN"),
        "good": good,
        "bad": bad,
        "last_mode": rsp[10] if len(rsp) > 10 else None,
        "raw_hex": rsp.hex(" "),
    }


@dataclass
class ProbeResult:
    port: str
    baud: int
    ok: bool
    response: dict | None
    error: str = ""


def probe_port(port: str, baud: int, attempts: int, timeout_s: float) -> ProbeResult:
    try:
        ser = serial.Serial(port, baud, timeout=0.01, write_timeout=0.2)
    except Exception as exc:
        return ProbeResult(port=port, baud=baud, ok=False, response=None, error=str(exc))
    try:
        ser.dtr = False
        ser.rts = False
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        for seq in range(1, attempts + 1):
            # Always probe with OFF + CLEAR. It cannot enable PWM.
            try:
                ser.write(build_cmd(seq, mode=MODE_OFF, flags=FLAG_CLEAR_FAULT))
                ser.flush()
                rsp = read_rsp(ser, timeout_s)
            except Exception as exc:
                return ProbeResult(port=port, baud=baud, ok=False, response=None, error=type(exc).__name__ + ": " + str(exc))
            if rsp is not None:
                parsed = parse_rsp(rsp)
                safe_ok = bool(parsed["crc_ok"]) and not bool(parsed.get("pwm_active"))
                error = "" if safe_ok else "unsafe response: pwm_active" if parsed.get("pwm_active") else "bad crc"
                return ProbeResult(port=port, baud=baud, ok=safe_ok, response=parsed, error=error)
            time.sleep(0.03)
        return ProbeResult(port=port, baud=baud, ok=False, response=None, error="no response")
    finally:
        ser.close()


def _probe_worker(queue: mp.Queue, port: str, baud: int, attempts: int, timeout_s: float) -> None:
    queue.put(probe_port(port, baud, attempts, timeout_s))


def probe_port_timed(port: str, baud: int, attempts: int, timeout_s: float, hard_timeout_s: float) -> ProbeResult:
    ctx = mp.get_context("spawn")
    queue = ctx.Queue(maxsize=1)
    proc = ctx.Process(target=_probe_worker, args=(queue, port, baud, attempts, timeout_s))
    proc.start()
    proc.join(max(0.5, hard_timeout_s))
    if proc.is_alive():
        proc.terminate()
        proc.join(1.0)
        return ProbeResult(port=port, baud=baud, ok=False, response=None, error="hard timeout")
    if not queue.empty():
        return queue.get()
    if proc.exitcode not in (0, None):
        return ProbeResult(port=port, baud=baud, ok=False, response=None, error=f"worker exit {proc.exitcode}")
    return ProbeResult(port=port, baud=baud, ok=False, response=None, error="no result")


def available_ports() -> list[str]:
    return [p.device for p in list_ports.comports()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe direct PC -> Blue Pill UART protocol safely.")
    parser.add_argument("--port", default="auto", help="COM port, or auto")
    parser.add_argument("--baud", type=int, default=460800)
    parser.add_argument("--all-baud", action="store_true", help="Probe common baud rates")
    parser.add_argument("--attempts", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=0.2)
    parser.add_argument("--hard-timeout", type=float, default=0.0, help="Max seconds per port/baud probe")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    ports = available_ports() if args.port.lower() == "auto" else [args.port]
    bauds = [args.baud]
    if args.all_baud:
        bauds = [460800, 115200, 230400, 921600]

    results: list[ProbeResult] = []
    hard_timeout = args.hard_timeout
    if hard_timeout <= 0.0:
        hard_timeout = max(2.0, float(args.attempts) * (args.timeout + 0.08) + 1.0)
    for port in ports:
        for baud in bauds:
            result = probe_port_timed(port, baud, args.attempts, args.timeout, hard_timeout)
            results.append(result)
            if args.json:
                continue
            print(f"{port}@{baud}: {'OK' if result.ok else 'FAIL'} {result.error}")
            if result.response is not None:
                print(json.dumps(result.response, ensure_ascii=False, indent=2))

    if args.json:
        print(json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=2))

    return 0 if any(r.ok for r in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
