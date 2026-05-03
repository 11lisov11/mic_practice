#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import select
import socket
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Deque, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

try:
    import termios
except Exception:  # pragma: no cover - Windows/local dev without POSIX TTY
    termios = None

try:
    import msgpack
except Exception:  # pragma: no cover - allow text-only mode without msgpack
    msgpack = None

STATE_NAMES = {
    0: "SAFE",
    1: "VF_RUN",
    2: "FOC_ALIGN",
    3: "FOC_RUN",
    4: "FAULT",
}
MODE_NAMES = {
    0: "VF",
    1: "FOC",
    2: "MIC",
    3: "DIAG",
    4: "DUTY",
}
STATE_CODES = {v: k for k, v in STATE_NAMES.items()}
MODE_CODES = {v: k for k, v in MODE_NAMES.items()}
BP_MODE_DIAG = 1
BP_MODE_DUTY = 2


def effective_mode(
    mode_code: int,
    bp_mode: int,
    diag_mode: Optional[int] = None,
    duty_mode: Optional[int] = None,
) -> tuple[int, str]:
    if diag_mode is not None:
        if int(diag_mode) != 0:
            return 3, MODE_NAMES[3]
    elif bp_mode == BP_MODE_DIAG:
        return 3, MODE_NAMES[3]
    if duty_mode is not None:
        if int(duty_mode) != 0:
            return 4, MODE_NAMES[4]
    elif bp_mode == BP_MODE_DUTY:
        return 4, MODE_NAMES[4]
    return mode_code, MODE_NAMES.get(mode_code, str(mode_code))


def _now_ts() -> float:
    return time.time()


def _fmt_ts(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


class LogStore:
    def __init__(self, max_bytes: int, log_path: Optional[str], file_max_bytes: int) -> None:
        self._max_bytes = max_bytes
        self._total_bytes = 0
        self._items: Deque[Tuple[float, str]] = deque()
        self._lock = threading.Lock()
        self._log_path = log_path
        self._file_max_bytes = file_max_bytes
        if self._log_path:
            log_dir = os.path.dirname(self._log_path)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)

    def add(self, line: str) -> None:
        ts = _now_ts()
        entry = f"{_fmt_ts(ts)} {line}"
        size = len(entry) + 1
        with self._lock:
            self._items.append((ts, entry))
            self._total_bytes += size
            while self._total_bytes > self._max_bytes and self._items:
                _, old = self._items.popleft()
                self._total_bytes -= (len(old) + 1)
            if self._log_path:
                self._append_to_file(entry)

    def _append_to_file(self, entry: str) -> None:
        if not self._log_path:
            return
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
            if self._file_max_bytes <= 0:
                return
            size = os.path.getsize(self._log_path)
            if size <= self._file_max_bytes:
                return
            self._truncate_file_tail()
        except Exception:
            pass

    def _truncate_file_tail(self) -> None:
        if not self._log_path:
            return
        try:
            with open(self._log_path, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                keep = min(size, self._file_max_bytes)
                f.seek(max(size - keep, 0))
                data = f.read()
            # Drop partial line at start
            nl = data.find(b"\n")
            if nl != -1:
                data = data[nl + 1 :]
            with open(self._log_path, "wb") as f:
                f.write(data)
        except Exception:
            pass

    @staticmethod
    def _parse_ts(entry: str) -> Optional[float]:
        try:
            ts_str = entry[:19]
            return time.mktime(time.strptime(ts_str, "%Y-%m-%d %H:%M:%S"))
        except Exception:
            return None

    def dump_since(self, since_ts: float) -> List[str]:
        if self._log_path and os.path.exists(self._log_path):
            try:
                with open(self._log_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.read().splitlines()
                out: List[str] = []
                for line in lines:
                    ts = self._parse_ts(line)
                    if ts is None or ts >= since_ts:
                        out.append(line)
                return out
            except Exception:
                pass
        with self._lock:
            return [entry for ts, entry in self._items if ts >= since_ts]


class RouterClient:
    def __init__(self, endpoint: str) -> None:
        if msgpack is None:
            raise RuntimeError("msgpack not available")
        self._endpoint = endpoint
        self._sock: Optional[socket.socket] = None
        self._unpacker: Optional[msgpack.Unpacker] = None
        self._packer = msgpack.Packer(use_bin_type=False)
        self._msgid = 1
        self._lock = threading.Lock()

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        self._unpacker = None

    def _connect(self) -> None:
        if self._sock is not None:
            return
        endpoint = self._endpoint
        if endpoint.startswith("unix:"):
            path = endpoint[5:]
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(path)
        elif "/" in endpoint or endpoint.startswith("."):
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(endpoint)
        else:
            host, port = self._parse_tcp(endpoint)
            sock = socket.create_connection((host, port), timeout=1.0)
        sock.settimeout(0.2)
        self._sock = sock
        self._unpacker = msgpack.Unpacker(raw=False)

    @staticmethod
    def _parse_tcp(endpoint: str) -> tuple[str, int]:
        if ":" in endpoint:
            host, port_str = endpoint.rsplit(":", 1)
        else:
            host, port_str = endpoint, "7501"
        host = host or "127.0.0.1"
        try:
            port = int(port_str)
        except ValueError:
            port = 7501
        return host, port

    def call(self, method: str, params: list, timeout: float = 1.5, retries: int = 1) -> Optional[list]:
        for attempt in range(retries + 1):
            with self._lock:
                try:
                    self._connect()
                    if self._sock is None or self._unpacker is None:
                        raise RuntimeError("no socket")
                    msgid = self._msgid
                    self._msgid += 1
                    self._sock.sendall(self._packer.pack([0, msgid, method, params]))
                    deadline = _now_ts() + timeout
                    while _now_ts() < deadline:
                        try:
                            data = self._sock.recv(4096)
                        except socket.timeout:
                            continue
                        if not data:
                            raise RuntimeError("router closed")
                        self._unpacker.feed(data)
                        for obj in self._unpacker:
                            if isinstance(obj, list) and len(obj) >= 4 and obj[0] == 1 and obj[1] == msgid:
                                return obj
                    raise RuntimeError("router timeout")
                except Exception:
                    self.close()
            if attempt < retries:
                time.sleep(0.05)
        return None


class SerialClient:
    def __init__(self, device: str, baud: int = 115200) -> None:
        if msgpack is None:
            raise RuntimeError("msgpack not available")
        self._device = device
        self._baud = baud
        self._fd: Optional[int] = None
        self._unpacker: Optional[msgpack.Unpacker] = None
        self._packer = msgpack.Packer(use_bin_type=False)
        self._msgid = 1
        self._lock = threading.Lock()

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except Exception:
                pass
        self._fd = None
        self._unpacker = None

    def _connect(self) -> None:
        if termios is None:
            raise RuntimeError("termios not available on this platform")
        if self._fd is not None:
            return
        fd = os.open(self._device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(fd)
        attrs[0] = 0  # iflag
        attrs[1] = 0  # oflag
        attrs[3] = 0  # lflag
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[4] = termios.B115200
        attrs[5] = termios.B115200
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        self._fd = fd
        self._unpacker = msgpack.Unpacker(raw=False)

    def call(self, method: str, params: list, timeout: float = 1.5, retries: int = 1) -> Optional[list]:
        for attempt in range(retries + 1):
            with self._lock:
                try:
                    self._connect()
                    if self._fd is None or self._unpacker is None:
                        raise RuntimeError("serial not open")
                    msgid = self._msgid
                    self._msgid += 1
                    os.write(self._fd, self._packer.pack([0, msgid, method, params]))
                    deadline = _now_ts() + timeout
                    while _now_ts() < deadline:
                        r, _, _ = select.select([self._fd], [], [], 0.05)
                        if not r:
                            continue
                        data = os.read(self._fd, 4096)
                        if not data:
                            raise RuntimeError("serial closed")
                        self._unpacker.feed(data)
                        for obj in self._unpacker:
                            if isinstance(obj, list) and len(obj) >= 4 and obj[0] == 1 and obj[1] == msgid:
                                return obj
                    raise RuntimeError("serial timeout")
                except Exception:
                    self.close()
            if attempt < retries:
                time.sleep(0.05)
        return None


class TextSerialClient:
    def __init__(self, device: str, baud: int = 115200) -> None:
        self._device = device
        self._baud = baud
        self._fd: Optional[int] = None
        self._lock = threading.Lock()
        self._rx_buf = bytearray()

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except Exception:
                pass
        self._fd = None
        self._rx_buf.clear()

    def _connect(self) -> None:
        if termios is None:
            raise RuntimeError("termios not available on this platform")
        if self._fd is not None:
            return
        fd = os.open(self._device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[3] = 0
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[4] = termios.B115200
        attrs[5] = termios.B115200
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        self._fd = fd

    def _read_lines(self, deadline: float) -> list[str]:
        lines: list[str] = []
        while _now_ts() < deadline:
            if self._fd is None:
                break
            r, _, _ = select.select([self._fd], [], [], 0.05)
            if not r:
                continue
            data = os.read(self._fd, 4096)
            if not data:
                raise RuntimeError("serial closed")
            self._rx_buf.extend(data)
            while True:
                nl = self._rx_buf.find(b"\n")
                if nl == -1:
                    break
                line = self._rx_buf[:nl].decode("utf-8", errors="ignore").strip()
                del self._rx_buf[: nl + 1]
                if line:
                    lines.append(line)
        return lines

    def _write_line(self, text: str) -> None:
        if self._fd is None:
            raise RuntimeError("serial not open")
        if not text.endswith("\n"):
            text += "\n"
        os.write(self._fd, text.encode("utf-8"))

    def cmd(self, cmd: str, timeout: float = 0.5, retries: int = 1) -> bool:
        for attempt in range(retries + 1):
            with self._lock:
                try:
                    self._connect()
                    self._write_line(cmd)
                    # Drain any queued lines quickly (non-blocking)
                    self._read_lines(_now_ts() + timeout)
                    return True
                except Exception:
                    self.close()
            if attempt < retries:
                time.sleep(0.05)
        return False

    def get(self, timeout: float = 1.0, retries: int = 1) -> Optional[str]:
        for attempt in range(retries + 1):
            with self._lock:
                try:
                    self._connect()
                    self._write_line("GET")
                    deadline = _now_ts() + timeout
                    while _now_ts() < deadline:
                        lines = self._read_lines(deadline)
                        for line in lines:
                            if line.startswith("DATA"):
                                return line
                    raise RuntimeError("serial timeout")
                except Exception:
                    self.close()
            if attempt < retries:
                time.sleep(0.05)
        return None


class RpcBridge:
    def __init__(self, endpoint: str) -> None:
        self._router: Optional[RouterClient] = None
        self._serial: Optional[SerialClient] = None
        self._serial_text: Optional[TextSerialClient] = None
        if endpoint.startswith("serial:"):
            self._serial_text = TextSerialClient(endpoint.replace("serial:", "", 1))
        elif endpoint.startswith("/dev/"):
            self._serial_text = TextSerialClient(endpoint)
        else:
            try:
                self._router = RouterClient(endpoint)
            except RuntimeError:
                self._router = None
            self._serial_text = TextSerialClient("/dev/ttyHS1")

    def _call(self, method: str, params: list, timeout: float = 1.5, retries: int = 1) -> Optional[list]:
        if self._router is not None:
            resp = self._router.call(method, params, timeout=timeout, retries=retries)
            if resp is not None:
                return resp
        return None

    def cmd(self, cmd: str) -> Tuple[bool, Optional[str]]:
        resp = self._call("cmd", [cmd], timeout=0.8, retries=2)
        if resp and len(resp) >= 4:
            err = resp[2]
            if err is not None:
                return False, str(err)
            return True, None
        if self._serial_text is not None:
            ok = self._serial_text.cmd(cmd, timeout=0.8, retries=2)
            return (ok, None if ok else "no response")
        return False, "no response"

    def get(self) -> Tuple[bool, Optional[dict], Optional[str]]:
        resp = self._call("get", [], timeout=2.0, retries=2)
        if resp and len(resp) >= 4:
            err = resp[2]
            if err is not None:
                return False, None, str(err)
            result = resp[3]
            if isinstance(result, str):
                parsed = self._parse_status_string(result)
                if parsed is None:
                    return False, None, "bad result"
                return True, parsed, None
            if not isinstance(result, list) or len(result) < 9:
                return False, None, "bad result"
            state_code = int(result[0])
            mode_code = int(result[1])
            bp_mode = int(result[29]) if len(result) >= 31 else 0
            diag_mode = int(result[45]) if len(result) >= 47 else None
            duty_mode = int(result[46]) if len(result) >= 47 else None
            mode_code_eff, mode_name_eff = effective_mode(mode_code, bp_mode, diag_mode, duty_mode)
            data = {
                "state_code": state_code,
                "state": STATE_NAMES.get(state_code, str(state_code)),
                "mode_code": mode_code_eff,
                "mode": mode_name_eff,
                "pwm": int(result[2]),
                "freq": float(result[3]),
                "speed": float(result[4]),
                "ia": float(result[5]),
                "ib": float(result[6]),
                "ic": float(result[7]),
                "vdc": float(result[8]),
                "ts": int(_now_ts() * 1000.0),
            }
            if len(result) >= 12:
                data["id"] = float(result[9])
                data["iq"] = float(result[10])
                data["i_rms"] = float(result[11])
            else:
                ia = data["ia"]
                ib = data["ib"]
                ic = data["ic"]
                data["i_rms"] = float(((ia * ia + ib * ib + ic * ic) / 3.0) ** 0.5)
            if len(result) >= 15:
                data["mic_active"] = int(result[12])
                data["id_ref"] = float(result[13])
                data["mic_saving_pct"] = float(result[14])
            else:
                data["mic_active"] = 0
                data["id_ref"] = 0.0
                data["mic_saving_pct"] = 0.0
            if len(result) >= 17:
                data["freq_cmd"] = float(result[15])
                data["estop"] = int(result[16])
            else:
                data["freq_cmd"] = data.get("freq", 0.0)
                data["estop"] = 0
            if len(result) >= 21:
                data["ntc"] = int(result[17])
                data["pfc"] = int(result[18])
                data["brake"] = int(result[19])
                data["brake_duty"] = float(result[20])
            else:
                data["ntc"] = 0
                data["pfc"] = 0
                data["brake"] = 0
                data["brake_duty"] = 0.0

            # Optional extended telemetry (keep in sync with UNOQ_MOTOR/UNOQ_MOTOR.ino rpc_send_response_get()).
            if len(result) >= 24:
                data["enc_raw"] = int(result[21])
                data["enc_ok"] = int(result[22])
                data["enc_deg"] = float(result[23])
            else:
                data["enc_raw"] = 0
                data["enc_ok"] = 0
                data["enc_deg"] = 0.0

            if len(result) >= 27:
                data["bp_good"] = int(result[24])
                data["bp_bad"] = int(result[25])
                data["bp_age_ms"] = int(result[26])
            else:
                data["bp_good"] = 0
                data["bp_bad"] = 0
                data["bp_age_ms"] = 999999

            if len(result) >= 31:
                data["bp_status"] = int(result[27])
                data["bp_fault"] = int(result[28])
                data["bp_mode"] = bp_mode
                data["bp_seq"] = int(result[30])
            else:
                data["bp_status"] = 0
                data["bp_fault"] = 0
                data["bp_mode"] = 0
                data["bp_seq"] = 0

            if len(result) >= 33:
                data["bp_ping_pairs"] = int(result[31])
                data["bp_ping_age_ms"] = int(result[32])
            else:
                data["bp_ping_pairs"] = 0
                data["bp_ping_age_ms"] = 999999

            if len(result) >= 34:
                data["bp_rsp_age_ms"] = int(result[33])
            else:
                data["bp_rsp_age_ms"] = 999999

            # Optional extended encoder telemetry (append-only after bp_rsp_age_ms).
            if len(result) >= 37:
                data["enc_rpm"] = float(result[34])
                data["enc_mech_hz"] = float(result[35])
                data["enc_elec_hz"] = float(result[36])
            else:
                data["enc_rpm"] = 0.0
                data["enc_mech_hz"] = 0.0
                data["enc_elec_hz"] = 0.0
            if len(result) >= 45:
                data["mic_gated"] = int(result[37])
                data["mic_enable_ai"] = int(result[38])
                data["mic_enc_used"] = int(result[39])
                data["mic_freq_meas_hz"] = float(result[40])
                data["mic_speed_err_hz"] = float(result[41])
                data["mic_speed_tol_hz"] = float(result[42])
                data["mic_link_flags"] = int(result[43])
                data["mic_status_flags"] = int(result[44])
            else:
                data["mic_gated"] = 0
                data["mic_enable_ai"] = 0
                data["mic_enc_used"] = 0
                data["mic_freq_meas_hz"] = 0.0
                data["mic_speed_err_hz"] = 0.0
                data["mic_speed_tol_hz"] = 0.0
                data["mic_link_flags"] = 0
                data["mic_status_flags"] = 0
            if len(result) >= 47:
                data["diag_mode"] = int(result[45])
                data["duty_mode"] = int(result[46])
            else:
                data["diag_mode"] = 1 if mode_code_eff == 3 else 0
                data["duty_mode"] = 1 if mode_code_eff == 4 else 0
            return True, data, None
        if self._serial_text is not None:
            line = self._serial_text.get(timeout=1.2, retries=2)
            if not line:
                return False, None, "no response"
            parsed = self._parse_status_string(line)
            if parsed is None:
                return False, None, "bad result"
            return True, parsed, None
        return False, None, "no response"

    @staticmethod
    def _parse_status_string(text: str) -> Optional[dict]:
        # Expected format: DATA freq=.. speed=.. ia=.. ib=.. ic=.. vdc=.. state=.. mode=.. pwm=..
        try:
            parts = text.replace("DATA", "").strip().split()
            kv = {}
            for part in parts:
                if "=" not in part:
                    continue
                k, v = part.split("=", 1)
                kv[k.strip()] = v.strip()
            state_s = kv.get("state", "")
            mode_s = kv.get("mode", "")
            state_code = STATE_CODES.get(state_s, -1)
            mode_code = MODE_CODES.get(mode_s, -1)
            diag_mode = int(float(kv.get("diag", "0")))
            duty_mode = int(float(kv.get("duty", "0")))
            mode_code_eff, mode_name_eff = effective_mode(mode_code, int(float(kv.get("bp_mode", "0"))), diag_mode, duty_mode)
            return {
                "state_code": int(state_code),
                "state": state_s or str(state_code),
                "mode_code": int(mode_code_eff),
                "mode": mode_name_eff,
                "pwm": int(float(kv.get("pwm", "0"))),
                "freq": float(kv.get("freq", "0")),
                "speed": float(kv.get("speed", "0")),
                "ia": float(kv.get("ia", "0")),
                "ib": float(kv.get("ib", "0")),
                "ic": float(kv.get("ic", "0")),
                "vdc": float(kv.get("vdc", "0")),
                "id": float(kv.get("id", "0")),
                "iq": float(kv.get("iq", "0")),
                "i_rms": float(kv.get("irm", "0")),
                "mic_active": int(float(kv.get("mic", "0"))),
                "id_ref": float(kv.get("idref", "0")),
                "mic_saving_pct": float(kv.get("save", "0")),
                "freq_cmd": float(kv.get("freqcmd", kv.get("freq", "0"))),
                "estop": int(float(kv.get("estop", "0"))),
                "ntc": int(float(kv.get("ntc", "0"))),
                "pfc": int(float(kv.get("pfc", "0"))),
                "brake": int(float(kv.get("brake", "0"))),
                "brake_duty": float(kv.get("brake_duty", "0")),
                "enc_raw": int(float(kv.get("enc_raw", "0"))),
                "enc_ok": int(float(kv.get("enc_ok", "0"))),
                "enc_deg": float(kv.get("enc_deg", "0")),
                "enc_rpm": float(kv.get("enc_rpm", "0")),
                "enc_mech_hz": float(kv.get("enc_mech_hz", "0")),
                "enc_elec_hz": float(kv.get("enc_elec_hz", "0")),
                "mic_gated": int(float(kv.get("mic_gated", "0"))),
                "mic_enable_ai": int(float(kv.get("mic_enable_ai", "0"))),
                "mic_enc_used": int(float(kv.get("mic_enc_used", "0"))),
                "mic_freq_meas_hz": float(kv.get("mic_fmeas", "0")),
                "mic_speed_err_hz": float(kv.get("mic_ferr", "0")),
                "mic_speed_tol_hz": float(kv.get("mic_ftol", "0")),
                "mic_link_flags": int(float(kv.get("mic_lflags", "0"))),
                "mic_status_flags": int(float(kv.get("mic_sflags", "0"))),
                "diag_mode": diag_mode,
                "duty_mode": duty_mode,
                "bp_good": int(float(kv.get("bp_good", "0"))),
                "bp_bad": int(float(kv.get("bp_bad", "0"))),
                "bp_age_ms": int(float(kv.get("bp_age_ms", "0"))),
                "ts": int(_now_ts() * 1000.0),
            }
        except Exception:
            return None


class AppState:
    def __init__(self, rpc: RpcBridge, logs: LogStore, status_log_interval: float) -> None:
        self.rpc = rpc
        self.logs = logs
        self._status_log_interval = status_log_interval
        self._last_status_log = 0.0
        self._lock = threading.Lock()

    def maybe_log_status(self, data: dict) -> None:
        now = _now_ts()
        with self._lock:
            if (now - self._last_status_log) < self._status_log_interval:
                return
            self._last_status_log = now
        line = (
            f"STAT state={data.get('state')} mode={data.get('mode')} pwm={data.get('pwm')} "
            f"freq={data.get('freq'):.2f} speed={data.get('speed'):.1f} vdc={data.get('vdc'):.2f}"
        )
        self.logs.add(line)


class Handler(BaseHTTPRequestHandler):
    server_version = "UNOQHMI/0.1"

    def _send_json(self, payload: dict, code: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _send_text(self, text: str, code: int = 200, filename: Optional[str] = None) -> None:
        data = text.encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            if filename:
                self.send_header("Content-Disposition", f"attachment; filename=\"{filename}\"")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _send_static(self, name: str, content_type: str) -> None:
        base = os.path.dirname(__file__)
        path = os.path.join(base, "static", name)
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            self.send_error(404)
            return
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_static("index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._send_static("app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/style.css":
            self._send_static("style.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/api/status":
            self._handle_status()
            return
        if parsed.path == "/api/logs":
            self._handle_logs(parsed)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/cmd":
            self._handle_cmd()
            return
        self.send_error(404)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _handle_cmd(self) -> None:
        data = self._read_json()
        cmd = str(data.get("cmd", "")).strip()
        if not cmd:
            self._send_json({"ok": False, "error": "missing cmd"}, 400)
            return
        ok, err = self.server.app.rpc.cmd(cmd)  # type: ignore[attr-defined]
        if ok:
            self.server.app.logs.add(f"CMD {cmd}")  # type: ignore[attr-defined]
            self._send_json({"ok": True})
        else:
            self.server.app.logs.add(f"CMD_FAIL {cmd} {err}")  # type: ignore[attr-defined]
            self._send_json({"ok": False, "error": err}, 500)

    def _handle_status(self) -> None:
        ok, data, err = self.server.app.rpc.get()  # type: ignore[attr-defined]
        if not ok or data is None:
            self._send_json({"ok": False, "error": err or "no response"}, 503)
            return
        self.server.app.maybe_log_status(data)  # type: ignore[attr-defined]
        self._send_json({"ok": True, "data": data})

    def _handle_logs(self, parsed) -> None:
        query = parse_qs(parsed.query)
        try:
            hours = float(query.get("hours", ["24"])[0])
        except ValueError:
            hours = 24.0
        download = query.get("download", ["0"])[0] in ("1", "true", "yes")
        since = _now_ts() - (hours * 3600.0)
        lines = self.server.app.logs.dump_since(since)  # type: ignore[attr-defined]
        text = "\n".join(lines) + ("\n" if lines else "")
        if download:
            self._send_text(text, filename="unoq_logs.txt")
        else:
            self._send_text(text)


def main() -> None:
    parser = argparse.ArgumentParser(description="UNOQ WiFi HMI server")
    parser.add_argument("--bind", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port")
    parser.add_argument(
        "--router",
        default="/run/arduino-router.sock",
        help="Router endpoint (unix:/path or host:port)",
    )
    parser.add_argument("--log-bytes", type=int, default=2 * 1024 * 1024, help="Max in-memory log bytes")
    parser.add_argument(
        "--log-file",
        default=os.path.join(os.path.dirname(__file__), "logs", "unoq.log"),
        help="Log file path (empty to disable)",
    )
    parser.add_argument("--log-file-bytes", type=int, default=4 * 1024 * 1024, help="Max log file bytes")
    parser.add_argument("--status-log-sec", type=float, default=5.0, help="Status log interval")
    args = parser.parse_args()
    if args.router == "/run/arduino-router.sock" and not os.path.exists(args.router):
        if os.path.exists("/var/run/arduino-router.sock"):
            args.router = "/var/run/arduino-router.sock"

    rpc = RpcBridge(args.router)
    log_path = args.log_file.strip() if isinstance(args.log_file, str) else args.log_file
    if log_path == "":
        log_path = None
    logs = LogStore(max_bytes=args.log_bytes, log_path=log_path, file_max_bytes=args.log_file_bytes)
    app = AppState(rpc, logs, args.status_log_sec)

    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    server.app = app  # type: ignore[attr-defined]
    server.daemon_threads = True

    print(f"UNOQ HMI on http://{args.bind}:{args.port} (router: {args.router})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
