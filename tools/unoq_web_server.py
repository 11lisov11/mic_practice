#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import serial

FRAME_LEN = 20
CMD_HDR0 = 0xAA
CMD_HDR1 = 0x55
RSP_HDR0 = 0x55
RSP_HDR1 = 0xAA

FLAG_ENABLE = 0x01
FLAG_ESTOP = 0x02
FLAG_DIAG_PWM = 0x04
FLAG_CLEAR_FAULT = 0x08
FLAG_VECTOR_ROTATE = 0x10

MODE_OFF = 0
MODE_DIAG = 1
MODE_DUTY = 2
MODE_SCALAR = 3
MODE_VECTOR = 4
MODE_FOC = 5

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
}


def log(msg: str) -> None:
    print(msg, flush=True)


def crc_xor(buf: bytes) -> int:
    c = 0
    for i in range(FRAME_LEN - 1):
        c ^= buf[i]
    return c & 0xFF


def read_frame(ser: serial.Serial, timeout_s: float) -> bytes | None:
    state = 0
    idx = 0
    buf = bytearray(FRAME_LEN)
    start = time.monotonic()
    while (time.monotonic() - start) < timeout_s:
        b = ser.read(1)
        if not b:
            continue
        val = b[0]
        if state == 0:
            if val == RSP_HDR0:
                buf[0] = val
                state = 1
        elif state == 1:
            if val == RSP_HDR1:
                buf[1] = val
                idx = 2
                state = 2
            elif val == RSP_HDR0:
                buf[0] = val
                state = 1
            else:
                state = 0
        else:
            buf[idx] = val
            idx += 1
            if idx >= FRAME_LEN:
                return bytes(buf)
    return None


def clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def clamp11(x: float) -> float:
    if x < -1.0:
        return -1.0
    if x > 1.0:
        return 1.0
    return x


def q15_from_unit(x: float) -> int:
    return int(clamp01(x) * 32767.0) & 0xFFFF


def q15_from_signed(x: float) -> int:
    return int(clamp11(x) * 32767.0) & 0xFFFF


class SharedState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.enable = False
        self.estop = False
        self.mode = MODE_OFF
        self.diag = False
        self.vector_rotate = False
        self.freq_hz = 5.0
        self.foc_freq_hz = 5.0
        self.mag = 0.30
        self.alpha = 0.3
        self.beta = 0.0
        self.id_ref = 0.0
        self.iq_ref = 0.3
        self.duty_u = 0.2
        self.duty_v = 0.2
        self.duty_w = 0.2
        self.clear_pending = False

        self.link_ok = False
        self.last_rsp = None  # type: bytes | None
        self.last_seq = 0
        self.last_rtt_ms = None  # type: float | None
        self.last_rx_time = 0.0

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "enable": self.enable,
                "estop": self.estop,
                "mode": self.mode,
                "diag": self.diag,
                "vector_rotate": self.vector_rotate,
                "freq_hz": self.freq_hz,
                "foc_freq_hz": self.foc_freq_hz,
                "mag": self.mag,
                "alpha": self.alpha,
                "beta": self.beta,
                "id_ref": self.id_ref,
                "iq_ref": self.iq_ref,
                "duty_u": self.duty_u,
                "duty_v": self.duty_v,
                "duty_w": self.duty_w,
            }


def build_frame(state: SharedState, seq: int) -> bytes:
    frame = bytearray(FRAME_LEN)
    frame[0] = CMD_HDR0
    frame[1] = CMD_HDR1
    frame[2] = 0x02

    with state.lock:
        enable = state.enable
        estop = state.estop
        mode = state.mode
        diag = state.diag
        vector_rotate = state.vector_rotate
        freq_hz = state.freq_hz
        foc_freq_hz = state.foc_freq_hz
        mag = state.mag
        alpha = state.alpha
        beta = state.beta
        id_ref = state.id_ref
        iq_ref = state.iq_ref
        duty_u = state.duty_u
        duty_v = state.duty_v
        duty_w = state.duty_w
        clear_pending = state.clear_pending
        if clear_pending:
            state.clear_pending = False

    flags = 0
    if clear_pending:
        flags |= FLAG_CLEAR_FAULT
        enable = False
        estop = False
        mode = MODE_OFF
        diag = False
    if enable:
        flags |= FLAG_ENABLE
    if estop:
        flags |= FLAG_ESTOP
    if diag:
        flags |= FLAG_DIAG_PWM
    if vector_rotate:
        flags |= FLAG_VECTOR_ROTATE

    frame[3] = flags
    frame[4] = mode & 0xFF
    frame[5] = seq & 0xFF

    if mode == MODE_DUTY:
        du = q15_from_unit(duty_u)
        dv = q15_from_unit(duty_v)
        dw = q15_from_unit(duty_w)
        frame[6] = du & 0xFF
        frame[7] = (du >> 8) & 0xFF
        frame[8] = dv & 0xFF
        frame[9] = (dv >> 8) & 0xFF
        frame[10] = dw & 0xFF
        frame[11] = (dw >> 8) & 0xFF
    elif mode == MODE_VECTOR and not vector_rotate:
        a = q15_from_signed(alpha)
        b = q15_from_signed(beta)
        frame[6] = a & 0xFF
        frame[7] = (a >> 8) & 0xFF
        frame[8] = b & 0xFF
        frame[9] = (b >> 8) & 0xFF
    elif mode == MODE_FOC:
        id_q15 = q15_from_signed(id_ref)
        iq_q15 = q15_from_signed(iq_ref)
        frame[6] = id_q15 & 0xFF
        frame[7] = (id_q15 >> 8) & 0xFF
        frame[8] = iq_q15 & 0xFF
        frame[9] = (iq_q15 >> 8) & 0xFF
        foc_mhz = int(max(0.0, foc_freq_hz) * 1000.0)
        frame[10] = foc_mhz & 0xFF
        frame[11] = (foc_mhz >> 8) & 0xFF
        frame[12] = (foc_mhz >> 16) & 0xFF
        frame[13] = (foc_mhz >> 24) & 0xFF
    else:
        freq_mhz = int(max(0.0, freq_hz) * 1000.0)
        frame[6] = freq_mhz & 0xFF
        frame[7] = (freq_mhz >> 8) & 0xFF
        frame[8] = (freq_mhz >> 16) & 0xFF
        frame[9] = (freq_mhz >> 24) & 0xFF
        mag_q15 = q15_from_unit(mag)
        frame[10] = mag_q15 & 0xFF
        frame[11] = (mag_q15 >> 8) & 0xFF

    frame[19] = crc_xor(frame)
    return bytes(frame)


def parse_rsp(state: SharedState, rsp: bytes, rtt_ms: float) -> None:
    if len(rsp) != FRAME_LEN:
        return
    if rsp[0] != RSP_HDR0 or rsp[1] != RSP_HDR1:
        return
    if rsp[19] != crc_xor(rsp):
        return

    status = rsp[3]
    with state.lock:
        state.link_ok = (status & STATUS_LINK_OK) != 0
        state.last_rsp = rsp
        state.last_seq = rsp[4]
        state.last_rtt_ms = rtt_ms
        state.last_rx_time = time.monotonic()


def status_payload(state: SharedState) -> dict[str, Any]:
    with state.lock:
        rsp = state.last_rsp
        link_ok = state.link_ok
        last_rtt = state.last_rtt_ms
        last_rx = state.last_rx_time
        mode = state.mode
        enable = state.enable
        estop = state.estop
        freq_hz = state.freq_hz
        foc_freq_hz = state.foc_freq_hz
    data: dict[str, Any] = {
        "link": bool(link_ok),
        "enable": bool(enable),
        "estop": bool(estop),
        "freq_cmd": float(freq_hz),
        "foc_freq_cmd": float(foc_freq_hz),
        "mode_cmd": mode,
        "last_rtt_ms": last_rtt,
        "last_rx_age_s": (time.monotonic() - last_rx) if last_rx > 0 else None,
    }
    if rsp:
        status = rsp[3]
        good = rsp[5] | (rsp[6] << 8)
        bad = rsp[7] | (rsp[8] << 8)
        fault = rsp[9]
        last_mode = rsp[10]
        data.update(
            {
                "status_flags": status,
                "pwm": int(1 if (status & STATUS_PWM_ACTIVE) else 0),
                "timeout": int(1 if (status & STATUS_TIMEOUT) else 0),
                "estop": int(1 if (status & STATUS_ESTOP) else 0),
                "fault": int(fault),
                "fault_text": FAULT_MAP.get(int(fault), "UNKNOWN"),
                "good": int(good),
                "bad": int(bad),
                "last_mode": int(last_mode),
            }
        )
    return data


def apply_cmd(state: SharedState, cmd: str) -> tuple[bool, str]:
    cmd = cmd.strip()
    if not cmd:
        return False, "empty cmd"
    parts = cmd.split()
    head = parts[0].upper()

    with state.lock:
        if head == "START":
            state.enable = True
            state.estop = False
            return True, "ok"
        if head == "STOP":
            state.enable = False
            return True, "ok"
        if head == "ESTOP":
            if len(parts) > 1 and parts[1].upper() == "CLEAR":
                state.estop = False
                state.enable = False
                state.clear_pending = True
                return True, "ok"
            state.estop = True
            state.enable = False
            return True, "ok"
        if head == "CLEAR":
            state.enable = False
            state.estop = False
            state.clear_pending = True
            return True, "ok"
        if head == "MODE" and len(parts) >= 2:
            mode = parts[1].upper()
            if mode in ("VF", "SCALAR"):
                state.mode = MODE_SCALAR
                state.vector_rotate = False
                state.diag = False
            elif mode in ("VECTOR", "VEC"):
                state.mode = MODE_VECTOR
                state.diag = False
            elif mode in ("FOC",):
                state.mode = MODE_FOC
                state.diag = False
            elif mode in ("DUTY",):
                state.mode = MODE_DUTY
                state.diag = False
            elif mode in ("DIAG",):
                state.mode = MODE_DIAG
                state.diag = True
            elif mode in ("OFF",):
                state.mode = MODE_OFF
                state.diag = False
            else:
                return False, f"unknown mode {mode}"
            return True, "ok"
        if head == "FREQ" and len(parts) >= 2:
            try:
                f = float(parts[1])
            except ValueError:
                return False, "bad freq"
            state.freq_hz = f
            state.foc_freq_hz = f
            return True, "ok"
        if head == "FOC_FREQ" and len(parts) >= 2:
            try:
                f = float(parts[1])
            except ValueError:
                return False, "bad foc_freq"
            state.foc_freq_hz = f
            return True, "ok"
        if head == "MAG" and len(parts) >= 2:
            try:
                state.mag = float(parts[1])
            except ValueError:
                return False, "bad mag"
            return True, "ok"
        if head == "ALPHA" and len(parts) >= 2:
            try:
                state.alpha = float(parts[1])
            except ValueError:
                return False, "bad alpha"
            return True, "ok"
        if head == "BETA" and len(parts) >= 2:
            try:
                state.beta = float(parts[1])
            except ValueError:
                return False, "bad beta"
            return True, "ok"
        if head == "ID" and len(parts) >= 2:
            try:
                state.id_ref = float(parts[1])
            except ValueError:
                return False, "bad id"
            return True, "ok"
        if head == "IQ" and len(parts) >= 2:
            try:
                state.iq_ref = float(parts[1])
            except ValueError:
                return False, "bad iq"
            return True, "ok"
        if head == "DUTY":
            vals = parts[1:]
            if not vals:
                return False, "missing duty"
            try:
                flt = [float(v) for v in vals]
            except ValueError:
                return False, "bad duty"
            if len(flt) == 1:
                state.duty_u = flt[0]
                state.duty_v = flt[0]
                state.duty_w = flt[0]
            elif len(flt) >= 3:
                state.duty_u = flt[0]
                state.duty_v = flt[1]
                state.duty_w = flt[2]
            else:
                return False, "need 1 or 3 duty values"
            state.mode = MODE_DUTY
            return True, "ok"
        if head == "VROT" and len(parts) >= 2:
            state.vector_rotate = parts[1].upper() in ("1", "ON", "TRUE", "YES")
            return True, "ok"
        if head == "SET" and len(parts) >= 3:
            key = parts[1].upper()
            val = parts[2]
            if key == "FREQ":
                try:
                    f = float(val)
                except ValueError:
                    return False, "bad freq"
                state.freq_hz = f
                state.foc_freq_hz = f
                return True, "ok"
            if key == "MAG":
                try:
                    state.mag = float(val)
                except ValueError:
                    return False, "bad mag"
                return True, "ok"
            return False, f"unknown set {key}"
    return False, f"unknown cmd: {cmd}"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _send_json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._send(code, body)

    def do_GET(self):
        if self.path.startswith("/api/status"):
            data = status_payload(self.server.state)  # type: ignore[attr-defined]
            self._send_json(200, {"ok": True, "data": data})
            return
        if self.path in ("/", "/index.html"):
            html = self.server.html  # type: ignore[attr-defined]
            self._send(200, html, "text/html; charset=utf-8")
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path.startswith("/api/cmd"):
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                self._send_json(400, {"ok": False, "error": "bad json"})
                return
            cmd = body.get("cmd", "")
            ok, msg = apply_cmd(self.server.state, str(cmd))  # type: ignore[attr-defined]
            if ok:
                self._send_json(200, {"ok": True})
            else:
                self._send_json(400, {"ok": False, "error": msg})
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def log_message(self, fmt: str, *args) -> None:
        return


HTML_UI = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>UNO Q Control</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; background: #0f1115; color: #e6e9ef; }
    .wrap { max-width: 980px; margin: 0 auto; padding: 16px; }
    .card { background: #171a21; border-radius: 12px; padding: 12px 16px; margin-bottom: 12px; }
    .row { display: flex; gap: 12px; flex-wrap: wrap; }
    .btn { padding: 10px 14px; border: 0; border-radius: 8px; background: #2b6cb0; color: #fff; cursor: pointer; }
    .btn.warn { background: #f59e0b; }
    .btn.danger { background: #d64545; }
    .btn.ghost { background: #1f2430; color: #e6e9ef; }
    label { font-size: 12px; color: #aab1c2; display: block; margin-bottom: 4px; }
    input, select { padding: 8px; border-radius: 8px; border: 1px solid #2a2f3a; background: #0f1115; color: #e6e9ef; }
    .k { color: #aab1c2; }
    .v { font-weight: 600; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    @media (max-width: 720px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <h2>UNO Q PWM Control</h2>
    <div class="card">
      <div class="row">
        <button class="btn" onclick="sendCmd('START')">START</button>
        <button class="btn ghost" onclick="sendCmd('STOP')">STOP</button>
        <button class="btn danger" onclick="sendCmd('ESTOP')">ESTOP</button>
        <button class="btn warn" onclick="sendCmd('ESTOP CLEAR')">CLEAR</button>
      </div>
    </div>

    <div class="card grid">
      <div>
        <label>Mode</label>
        <select id="mode" onchange="onMode()">
          <option value="VF">VF (Scalar)</option>
          <option value="FOC">FOC</option>
          <option value="VECTOR">Vector</option>
          <option value="DUTY">Duty</option>
          <option value="DIAG">Diag</option>
          <option value="OFF">Off</option>
        </select>
      </div>
      <div>
        <label>Freq (Hz)</label>
        <input id="freq" type="number" step="0.1" min="0" max="50" value="5.0" oninput="onFreq()">
      </div>
      <div>
        <label>Mag (0..1)</label>
        <input id="mag" type="number" step="0.01" min="0" max="1" value="0.30" oninput="onMag()">
      </div>
      <div>
        <label>Vector Alpha/Beta (-1..1)</label>
        <div class="row">
          <input id="alpha" type="number" step="0.01" min="-1" max="1" value="0.30" oninput="onAlpha()">
          <input id="beta" type="number" step="0.01" min="-1" max="1" value="0.00" oninput="onBeta()">
        </div>
      </div>
      <div>
        <label>FOC Id/Iq (-1..1)</label>
        <div class="row">
          <input id="id" type="number" step="0.01" min="-1" max="1" value="0.00" oninput="onId()">
          <input id="iq" type="number" step="0.01" min="-1" max="1" value="0.30" oninput="onIq()">
        </div>
      </div>
      <div>
        <label>Duty U/V/W (0..1)</label>
        <div class="row">
          <input id="du" type="number" step="0.01" min="0" max="1" value="0.20" oninput="onDuty()">
          <input id="dv" type="number" step="0.01" min="0" max="1" value="0.20" oninput="onDuty()">
          <input id="dw" type="number" step="0.01" min="0" max="1" value="0.20" oninput="onDuty()">
        </div>
      </div>
    </div>

    <div class="card">
      <div class="row">
        <div><span class="k">Link:</span> <span id="link" class="v">-</span></div>
        <div><span class="k">PWM:</span> <span id="pwm" class="v">-</span></div>
        <div><span class="k">Fault:</span> <span id="fault" class="v">-</span></div>
        <div><span class="k">Timeout:</span> <span id="timeout" class="v">-</span></div>
        <div><span class="k">RTT ms:</span> <span id="rtt" class="v">-</span></div>
      </div>
    </div>
  </div>
  <script>
    async function sendCmd(cmd) {
      await fetch('/api/cmd', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({cmd})
      });
    }
    function onMode(){ sendCmd('MODE ' + document.getElementById('mode').value); }
    function onFreq(){ sendCmd('FREQ ' + document.getElementById('freq').value); }
    function onMag(){ sendCmd('MAG ' + document.getElementById('mag').value); }
    function onAlpha(){ sendCmd('ALPHA ' + document.getElementById('alpha').value); }
    function onBeta(){ sendCmd('BETA ' + document.getElementById('beta').value); }
    function onId(){ sendCmd('ID ' + document.getElementById('id').value); }
    function onIq(){ sendCmd('IQ ' + document.getElementById('iq').value); }
    function onDuty(){
      const u = document.getElementById('du').value;
      const v = document.getElementById('dv').value;
      const w = document.getElementById('dw').value;
      sendCmd('DUTY ' + u + ' ' + v + ' ' + w);
    }
    async function poll() {
      try {
        const r = await fetch('/api/status');
        const j = await r.json();
        if (j.ok) {
          const d = j.data;
          document.getElementById('link').textContent = d.link ? 'OK' : 'NO';
          document.getElementById('pwm').textContent = d.pwm ? 'ON' : 'OFF';
          document.getElementById('fault').textContent = d.fault_text || d.fault || '-';
          document.getElementById('timeout').textContent = d.timeout ? 'YES' : 'NO';
          document.getElementById('rtt').textContent = d.last_rtt_ms ? d.last_rtt_ms.toFixed(1) : '-';
        }
      } catch (e) {}
      setTimeout(poll, 250);
    }
    poll();
  </script>
</body>
</html>
"""


def uart_worker(state: SharedState, port: str, baud: int, rate_hz: float, rx_timeout: float) -> None:
    period = 1.0 / max(5.0, rate_hz)
    seq = 1
    while True:
        try:
            ser = serial.Serial(port, baud, timeout=0.01)
        except Exception as exc:
            log(f"UART open failed {port}: {exc}")
            time.sleep(1.0)
            continue

        ser.dtr = False
        ser.rts = False
        log(f"UART ready on {port} @ {baud}")
        try:
            next_t = time.monotonic()
            while True:
                frame = build_frame(state, seq)
                t0 = time.monotonic()
                ser.write(frame)
                rsp = read_frame(ser, rx_timeout)
                if rsp and rsp[19] == crc_xor(rsp):
                    rtt = (time.monotonic() - t0) * 1000.0
                    parse_rsp(state, rsp, rtt)
                else:
                    with state.lock:
                        state.link_ok = False
                seq = (seq + 1) & 0xFF
                next_t += period
                sleep = next_t - time.monotonic()
                if sleep > 0:
                    time.sleep(sleep)
        except Exception as exc:
            log(f"UART error: {exc}")
            try:
                ser.close()
            except Exception:
                pass
            time.sleep(0.5)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", required=True, help="Serial port to Blue Pill, e.g. /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--rate", type=float, default=50.0, help="UART command rate (Hz)")
    ap.add_argument("--rx-timeout", type=float, default=0.08)
    args = ap.parse_args()

    state = SharedState()
    th = threading.Thread(
        target=uart_worker,
        args=(state, args.serial, args.baud, args.rate, args.rx_timeout),
        daemon=True,
    )
    th.start()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.state = state  # type: ignore[attr-defined]
    server.html = HTML_UI.encode("utf-8")  # type: ignore[attr-defined]

    log(f"HTTP server on http://{args.host}:{args.port}")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
