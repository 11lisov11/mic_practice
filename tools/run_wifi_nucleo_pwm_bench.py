#!/usr/bin/env python3
"""Prove Wi-Fi -> UNO Q -> UART -> Nucleo PWM, then restore production images."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from nucleo_logic_capture import CHANNEL_MAP, capture_checks
from runtime_python import ensure_modules_or_reexec
from saleae_pwm_analyze import analyze_csv, channel_summary, load_csv


SAMPLE_RATE_HZ = 24_000_000
PWM_CHANNELS = list(CHANNEL_MAP)
CAPTURE_CHANNELS = [*PWM_CHANNELS, 6]
PWM_HZ = 10_000.0
CAPTURE_DURATION_S = 0.10
# UNOQ_MOTOR intentionally delays RouterBridge startup by 6 seconds. Give the
# MCU time to register its RPC methods before the Linux HMI sends any command.
UNOQ_ROUTER_BOOT_WAIT_S = 7.0


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_logged(command: list[str], log: Path, timeout: float = 180.0) -> None:
    result = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    log.write_text(result.stdout, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}); see {log.name}")


class WifiHmi:
    def __init__(self, base_url: str, token: str, report_commands: list[dict[str, Any]],
                 via_wsl: bool = False) -> None:
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme != "http" or not parsed.hostname:
            raise ValueError("HMI URL must be an explicit http://host:port URL")
        resolved = socket.gethostbyname(parsed.hostname)
        if resolved.startswith("127.") or resolved == "0.0.0.0":
            raise ValueError("loopback/ADB-forward HMI URLs are forbidden in the Wi-Fi proof")
        self.base = base_url.rstrip("/")
        self.host = parsed.hostname
        self.resolved = resolved
        self.token = token
        self.commands = report_commands
        self.via_wsl = via_wsl
        self._wsl_lock = threading.Lock()
        self._wsl_process: subprocess.Popen[str] | None = None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def close(self) -> None:
        with self._wsl_lock:
            process = self._wsl_process
            self._wsl_process = None
            if process is not None and process.poll() is None:
                assert process.stdin is not None
                process.stdin.close()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2.0)

    def _request_via_wsl(self, method: str, path: str, headers: dict[str, str],
                         body: dict[str, Any] | None,
                         response_format: str = "json") -> tuple[int, Any]:
        with self._wsl_lock:
            process = self._wsl_process
            if process is None or process.poll() is not None:
                helper = Path(__file__).resolve().with_name("wifi_http_via_wsl.py")
                windows_path = helper.as_posix()
                if len(windows_path) < 4 or windows_path[1:3] != ":/":
                    raise RuntimeError("WSL HTTP transport requires a Windows drive path")
                wsl_path = "/mnt/" + windows_path[0].lower() + windows_path[2:]
                process = subprocess.Popen(
                    ["wsl.exe", "-e", "python3", wsl_path],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                )
                self._wsl_process = process
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(json.dumps({"method": method, "url": self.base + path,
                                            "headers": headers, "body": body,
                                            "response_format": response_format}) + "\n")
            process.stdin.flush()
            response = process.stdout.readline()
            if not response:
                raise RuntimeError("WSL Wi-Fi helper stopped without a response")
            envelope = json.loads(response)
            if "error" in envelope:
                raise RuntimeError(f"WSL Wi-Fi request failed: {envelope['error']}")
            return int(envelope["code"]), envelope["payload"]

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if method != "GET":
            headers["X-UNOQ-Control-Token"] = self.token
        if self.via_wsl:
            code, data = self._request_via_wsl(method, path, headers, body)
        else:
            request = urllib.request.Request(self.base + path, data=payload, headers=headers, method=method)
            try:
                with self.opener.open(request, timeout=8.0) as response:
                    raw = response.read()
                    code = int(response.status)
            except urllib.error.HTTPError as exc:
                raw = exc.read()
                code = int(exc.code)
            data = json.loads(raw.decode("utf-8")) if raw else {}
        return code, data

    def status(self) -> dict[str, Any]:
        code, payload = self.request("GET", "/api/status")
        if code != 200 or payload.get("ok") is not True or not isinstance(payload.get("data"), dict):
            raise RuntimeError(f"Wi-Fi status failed: HTTP {code}: {payload}")
        return payload["data"]

    def post(self, path: str, body: dict[str, Any], label: str) -> dict[str, Any]:
        started = time.time()
        code, payload = self.request("POST", path, body)
        self.commands.append({
            "label": label,
            "path": path,
            "body": body,
            "http_status": code,
            "ok": payload.get("ok") is True,
            "host_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": round(time.time() - started, 3),
            "transport": "wsl_nat_wifi_http" if self.via_wsl else "direct_wifi_http",
        })
        if code != 200 or payload.get("ok") is not True:
            raise RuntimeError(f"{label} failed over Wi-Fi: HTTP {code}: {payload.get('error') or payload}")
        return payload

    def command(self, command: str) -> dict[str, Any]:
        return self.post("/api/cmd", {"cmd": command}, command)

    def fail_safe_stop(self) -> tuple[int, dict[str, Any]]:
        try:
            return self.request("POST", "/api/stop-sequence", {"emergency": False})
        except Exception as exc:
            return 0, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def wait_status(
    hmi: WifiHmi,
    predicate: Callable[[dict[str, Any]], bool],
    timeout_s: float,
    description: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] | None = None
    last_error = "no status"
    while time.monotonic() < deadline:
        try:
            last = hmi.status()
            if predicate(last):
                return last
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.15)
    raise RuntimeError(f"timeout waiting for {description}: {last or last_error}")


def safe_status_projection(status: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "state", "mode", "pwm", "estop", "vdc", "bp_status", "bp_fault",
        "bp_bad", "bp_bad_cnt", "bp_age_ms", "bp_vbus_raw", "bp_vbus_valid",
        "bp_softstart_ready", "bp_temp_c", "bp_temp_valid", "bp_mcsdk_telemetry",
        "fw_build", "mc_fw_build", "rpc_schema_version",
        "hmi_arm_profile", "hmi_hv_armed",
    )
    return {key: status.get(key) for key in keys}


def verify_unpowered_preflash(status: dict[str, Any]) -> None:
    if (str(status.get("state", "")).upper() != "SAFE"
            or int(status.get("pwm", 1)) != 0
            or int(status.get("hmi_hv_armed", 1)) != 0
            or int(status.get("bp_vbus_valid", 0)) != 1
            or float(status.get("bp_age_ms", 999999.0)) > 500.0
            or not 0.0 <= float(status.get("vdc", 999999.0)) <= 2.0):
        raise RuntimeError("Production telemetry is not SAFE, disarmed, fresh, and below 2 V on J1")


def capture(manager: Any, device_id: str, folder: Path, duration_s: float,
            sample_rate_hz: int = SAMPLE_RATE_HZ) -> Path:
    from saleae import automation

    folder.mkdir(parents=True, exist_ok=False)
    failures = []
    for attempt in range(3):
        target = folder if attempt == 0 else folder / f"retry_{attempt}"
        target.mkdir(parents=True, exist_ok=True)
        try:
            with manager.start_capture(
                device_id=device_id,
                device_configuration=automation.LogicDeviceConfiguration(
                    enabled_digital_channels=CAPTURE_CHANNELS,
                    digital_sample_rate=sample_rate_hz,
                ),
                capture_configuration=automation.CaptureConfiguration(
                    capture_mode=automation.TimedCaptureMode(duration_seconds=duration_s),
                ),
            ) as session:
                session.wait()
                session.save_capture(str(target / "capture.sal"))
                session.export_raw_data_csv(directory=str(target / "csv"), digital_channels=CAPTURE_CHANNELS)
            return target / "csv" / "digital.csv"
        except automation.errors.DeviceError as exc:
            failures.append({"attempt": attempt + 1, "error": str(exc)})
            (folder / "capture_errors.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
            if "ReadTimeout" not in str(exc) or attempt == 2:
                raise
            time.sleep(0.15)


def analyze_active(csv_path: Path, require_em_stop: bool = False,
                   sample_rate_hz: int = SAMPLE_RATE_HZ) -> dict[str, Any]:
    analysis = analyze_csv(
        csv_path,
        expect_pwm=True,
        selected_sample_rate_hz=sample_rate_hz,
        max_sample_period_ns=1e9 / sample_rate_hz,
    )
    checks = capture_checks(analysis, True)["checks"]
    checks["carrier_10khz"] = all(
        abs(channel["freq_hz_from_rising"] - PWM_HZ) <= 100.0
        for channel in analysis["channels"].values()
    )
    tolerance = max(0.2e-6, 1.0 / sample_rate_hz)
    checks["deadtime_within_sample_resolution"] = all(
        pair["min_gap_s"] is not None and abs(pair["min_gap_s"] - 2e-6) <= tolerance + 1e-12
        for pair in analysis["pairs"].values()
    )
    times, values = load_csv(csv_path, CAPTURE_CHANNELS)
    em_stop = channel_summary(times, values[6])
    em_stop_held_low_raw = (
        em_stop["initial"] == 0 and em_stop["final"] == 0 and em_stop["edges"] == 0
    )
    active_indices = [index for index in range(len(times))
                      if any(values[channel][index] for channel in PWM_CHANNELS)]
    em_stop_low_during_pwm = bool(active_indices) and all(
        values[6][index] == 0
        for index in range(active_indices[0], active_indices[-1] + 1)
    )
    checks["pa6_em_stop_held_low_raw"] = em_stop_held_low_raw
    checks["pa6_low_during_pwm"] = em_stop_low_during_pwm
    required_checks = {key: value for key, value in checks.items()
                       if key not in ("pa6_em_stop_held_low_raw", "pa6_low_during_pwm")}
    if require_em_stop:
        required_checks["pa6_low_during_pwm"] = em_stop_low_during_pwm
    return {
        "pass": all(required_checks.values()),
        "checks": checks,
        "required_checks": sorted(required_checks),
        "em_stop_required": require_em_stop,
        "em_stop": em_stop,
        "first_pwm_activity_s": times[active_indices[0]] if active_indices else None,
        "sample_rate_hz": sample_rate_hz,
        "deadtime_tolerance_us": tolerance * 1e6,
        "analysis": analysis,
    }


def analyze_static(csv_path: Path, settle_s: float = 0.0,
                   sample_rate_hz: int = SAMPLE_RATE_HZ) -> dict[str, Any]:
    analysis = analyze_csv(
        csv_path,
        selected_sample_rate_hz=sample_rate_hz,
        max_sample_period_ns=1e9 / sample_rate_hz,
    )
    result = capture_checks(analysis, False)
    result["settle_s"] = settle_s
    if settle_s > 0.0:
        times, values = load_csv(csv_path, PWM_CHANNELS)
        settled_indices = [index for index, timestamp in enumerate(times) if timestamp >= settle_s]
        settled_low = bool(settled_indices) and all(
            values[channel][index] == 0
            for channel in PWM_CHANNELS
            for index in settled_indices
        )
        raw_static_low = bool(result["checks"].get("all_six_static_low"))
        result["checks"]["all_six_static_low_raw"] = raw_static_low
        result["checks"]["all_six_static_low"] = settled_low
        result["pass"] = bool(
            result["checks"].get("all_six_channels_present")
            and result["checks"].get("no_overlap")
            and result["checks"].get("timing_resolution")
            and settled_low
        )
    return {**result, "analysis": analysis}


def analyze_software_break(csv_path: Path, sample_rate_hz: int = SAMPLE_RATE_HZ) -> dict[str, Any]:
    active = analyze_active(csv_path, sample_rate_hz=sample_rate_hz)
    times, values = load_csv(csv_path, CAPTURE_CHANNELS)
    edge_times = {
        channel: [times[index] for index in range(1, len(times))
                  if values[channel][index] != values[channel][index - 1]]
        for channel in PWM_CHANNELS
    }
    first = min((edges[0] for edges in edge_times.values() if edges), default=times[-1])
    last = max((edges[-1] for edges in edge_times.values() if edges), default=times[0])
    checks = {
        "six_channel_pwm_valid": active["pass"],
        "break_after_sustained_pwm": 1.0 <= last - first <= 1.6,
        "all_six_stop_together": all(edges and last - edges[-1] <= 0.0002
                                      for edges in edge_times.values()),
        "outputs_stay_low": times[-1] - last >= 0.15
        and all(values[channel][index] == 0 for channel in PWM_CHANNELS
                for index, timestamp in enumerate(times) if timestamp >= last),
        "physical_sd_pin_remained_high": all(value == 1 for value in values[6]),
    }
    return {"pass": all(checks.values()), "checks": checks,
            "first_pwm_edge_s": first, "last_pwm_edge_s": last,
            "quiet_after_break_s": times[-1] - last,
            "pwm_analysis": active}


def analyze_external_break(csv_path: Path, sample_rate_hz: int = SAMPLE_RATE_HZ) -> dict[str, Any]:
    active = analyze_active(csv_path, sample_rate_hz=sample_rate_hz)
    times, values = load_csv(csv_path, CAPTURE_CHANNELS)
    falling = next((i for i in range(1, len(times))
                    if values[6][i - 1] == 1 and values[6][i] == 0), None)
    rising_edges = [i for i in range((falling or 0) + 1, len(times))
                    if values[6][i - 1] == 0 and values[6][i] == 1]
    rising = rising_edges[-1] if rising_edges else None
    sd_low_time_s = sum(times[i + 1] - times[i]
                        for i in range(falling or 0, len(times) - 1)
                        if values[6][i] == 0)
    low_run_s, longest_low_s = 0.0, 0.0
    for i in range(falling or 0, len(times) - 1):
        low_run_s = low_run_s + times[i + 1] - times[i] if values[6][i] == 0 else 0.0
        longest_low_s = max(longest_low_s, low_run_s)
    first_all_low = next((i for i in range(falling, len(times))
                          if all(values[ch][i] == 0 for ch in PWM_CHANNELS)), None) if falling else None
    trip_time = times[falling] if falling else None
    checks = {
        "six_channel_pwm_valid": active["pass"],
        "sd_fell_after_pwm": falling is not None and all(
            any(times[i] - 0.02 <= times[j] < times[i]
                and values[ch][j] != values[ch][j - 1]
                for j in range(1, i + 1))
            for ch in PWM_CHANNELS for i in [falling]
        ),
        "sd_low_confirmed": longest_low_s >= 0.02 - 1.0 / sample_rate_hz,
        "sd_released": rising is not None and values[6][-1] == 1
        and times[-1] - times[rising] >= 0.1,
        "all_six_low_within_100us": first_all_low is not None and trip_time is not None
        and times[first_all_low] - trip_time <= 0.0001,
        "outputs_stay_low_after_sd_release": first_all_low is not None and rising is not None
        and times[-1] - times[rising] >= 0.1
        and all(values[ch][i] == 0 for ch in PWM_CHANNELS
                for i in range(first_all_low, len(times))),
    }
    return {"pass": all(checks.values()), "checks": checks,
            "sd_falling_s": trip_time,
            "sd_rising_s": times[rising] if rising is not None else None,
            "sd_low_total_ms": sd_low_time_s * 1000.0,
            "sd_low_longest_ms": longest_low_s * 1000.0,
            "sd_edge_count": sum(values[6][i] != values[6][i - 1]
                                 for i in range(1, len(times))),
            "trip_to_all_low_us": (times[first_all_low] - trip_time) * 1e6
            if first_all_low is not None and trip_time is not None else None,
            "pwm_analysis": active}


def read_control_token(adb: str, device: str, path: str) -> str:
    result = subprocess.run(
        [adb, "-s", device, "shell", "cat", path],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10.0,
    )
    token = result.stdout.strip()
    if result.returncode or len(token) < 16:
        raise RuntimeError("UNO Q control token is unavailable")
    return token


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-steval-j1-disconnected", action="store_true")
    parser.add_argument("--confirm-j4-off", action="store_true")
    parser.add_argument("--confirm-motor-disconnected", action="store_true")
    parser.add_argument("--confirm-j1-below-2v", action="store_true")
    parser.add_argument("--confirm-hv-off", action="store_true")
    parser.add_argument("--hmi", default="http://192.168.1.138:8080")
    parser.add_argument("--wifi-via-wsl", action="store_true",
                        help="Use WSL NAT to reach the HMI LAN address when Windows VPN blocks local TCP")
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--adb-device", default="3880458060")
    parser.add_argument("--token-file", default="/home/arduino/.config/mic-ai/control_token")
    parser.add_argument("--uno-port", default="COM10")
    parser.add_argument("--stlink", default="003A002C3335510933383531")
    parser.add_argument("--logic-device", default="A7D1BB81883C0092")
    parser.add_argument("--logic-port", type=int, default=10430)
    parser.add_argument("--require-em-stop-channel", action="store_true")
    parser.add_argument("--all-scenarios", action="store_true", help="Repeat starts, ESTOP, auth, run limit and heartbeat-loss checks")
    parser.add_argument("--transition-scenarios", action="store_true", help="Record START and STOP in one continuous capture")
    parser.add_argument("--stop-tail-test", action="store_true",
                        help="Probe capture tails after STOP with disabled TIM1 and halted G431 core")
    parser.add_argument("--software-break-test", action="store_true",
                        help="Use a BKIN-enabled bench image with an automatic TIM1 BG trip")
    parser.add_argument("--external-break-test", action="store_true",
                        help="Wait for an operator to pull STEVAL SD low during BKIN-enabled PWM")
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    if not all((args.confirm_steval_j1_disconnected, args.confirm_j4_off,
                args.confirm_motor_disconnected, args.confirm_j1_below_2v, args.confirm_hv_off)):
        parser.error("active bench requires detached STEVAL J1, J4 off, motor detached, "
                     "measured J1 below 2 V, and HV off; the J2 control ribbon may stay connected")
    if (args.software_break_test or args.external_break_test) and (
            args.all_scenarios or args.transition_scenarios or args.stop_tail_test or
            (args.software_break_test and args.external_break_test)):
        parser.error("break tests cannot be combined with other active scenarios")

    ensure_modules_or_reexec(["saleae"], "MIC_PRACTICE_WIFI_PWM_BENCH_REEXEC")
    from saleae import automation

    root = Path(__file__).resolve().parents[1]
    source = (root / "UNOQ_MOTOR/UNOQ_MOTOR.ino").read_text(encoding="utf-8")
    expected_uno_build = int(re.search(r"FW_BUILD_ID\s*=\s*(\d+)U", source).group(1))
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    logs = out / "logs"
    logs.mkdir()
    bench_build = out / "unoq_logic_bench_build"
    bench_build.mkdir()
    uno_bench = bench_build / "UNOQ_MOTOR.ino.elf-zsk.bin"
    bench_env = ("nucleo_g431_pwm_bkin_external_bench" if args.external_break_test else
                 "nucleo_g431_pwm_bkin_bench" if args.software_break_test else
                 "nucleo_g431_pwm_bench")
    nucleo_bench = root / "nucleo_g431_uart_bridge_pio/.pio/build" / bench_env / "firmware.bin"
    uno_production = root / "firmware/ready_to_flash/uno_q_mcu/UNOQ_MOTOR.ino.elf-zsk.bin"
    nucleo_production = root / "firmware/ready_to_flash/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex"
    programmer = Path("C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe")
    verify_cfg = root / "tools/verify_unoq_sketch.cfg"
    arduino_cli = "arduino-cli"
    report: dict[str, Any] = {
        "schema": "mic_ai.wifi_nucleo_pwm_bench.v1",
        "host_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "logic_pwm_with_unpowered_ipm_and_control_ribbon_attached",
        "break_test_kind": ("external_sd_pin" if args.external_break_test else
                            "timer_software_bg_not_physical_sd" if args.software_break_test else "none"),
        "hmi_url": args.hmi,
        "control_transport": "wsl_nat_wifi_http" if args.wifi_via_wsl else "direct_wifi_http",
        "credential_bootstrap": "ADB read-only token retrieval; no motor command over ADB",
        "uart": "UNO Q D1/TX -> Nucleo PB7/RX; Nucleo PB6/TX -> UNO Q D0/RX; common GND",
        "saleae_channel_map": {**CHANNEL_MAP, 6: {"signal": "EM_STOP", "gpio": "PA6"}},
        "commands": [],
        "restored": {"uno_q": False, "nucleo": False},
        "pass": False,
    }
    hmi: WifiHmi | None = None
    manager: Any = None
    error: str | None = None
    uno_may_be_modified = False
    nucleo_may_be_modified = False

    def program_nucleo(image: Path, log_name: str) -> None:
        run_logged([
            str(programmer), "-c", "port=SWD", "mode=UR", "reset=HWrst", "sn=" + args.stlink,
            "-w", str(image), *( ["0x08000000"] if image.suffix.lower() == ".bin" else [] ), "-v", "-rst",
        ], logs / log_name, timeout=60.0)

    def program_uno(image: Path, log_name: str) -> None:
        # The stock UNO Q recipe performs the actual remoteocd write. The
        # project-specific recipe is deliberately verification-only.
        run_logged([
            arduino_cli, "upload", "-p", args.uno_port, "-b", "arduino:zephyr:unoq", "-i", str(image),
            "--upload-property", f"upload.artifacts.sketch={image}",
            "--upload-property", f"upload.port.properties.serialNumber={args.adb_device}",
        ], logs / ("write_" + log_name), timeout=90.0)
        run_logged([
            arduino_cli, "upload", "-p", args.uno_port, "-b", "arduino:zephyr:unoq", "-i", str(image),
            "--upload-property", f"upload.artifacts.sketch={image}",
            "--upload-property", f"upload.port.properties.serialNumber={args.adb_device}",
            "--upload-property", f"build.variant.path={root / 'tools'}",
            "--upload-property", "openocd_cfg=verify_unoq_sketch.cfg",
        ], logs / log_name, timeout=90.0)

    try:
        required = (programmer, verify_cfg, uno_production, nucleo_production)
        for path in required:
            if not path.is_file():
                raise FileNotFoundError(path)
        run_logged(
            [sys.executable, str(root / "tools/verify_board_flash_package.py"), str(uno_production.parents[1])],
            logs / "verify_production_package.log",
        )
        run_logged(
            ["platformio", "run", "-d", str(root / "nucleo_g431_uart_bridge_pio"), "-e", bench_env],
            logs / "build_nucleo_bench.log",
        )
        run_logged([
            arduino_cli, "compile", "--fqbn", "arduino:zephyr:unoq",
            "--build-property", "compiler.cpp.extra_flags=-DUNOQ_LOGIC_BENCH=1",
            "--output-dir", str(bench_build), str(root / "UNOQ_MOTOR"),
        ], logs / "build_unoq_bench.log", timeout=240.0)
        for path in (uno_bench, nucleo_bench):
            if not path.is_file():
                raise FileNotFoundError(path)
        report["images"] = {
            "uno_bench": {"path": str(uno_bench), "sha256": sha256(uno_bench)},
            "nucleo_bench": {"path": str(nucleo_bench), "sha256": sha256(nucleo_bench)},
            "uno_production": {"path": str(uno_production), "sha256": sha256(uno_production)},
            "nucleo_production": {"path": str(nucleo_production), "sha256": sha256(nucleo_production)},
        }

        token = read_control_token(args.adb, args.adb_device, args.token_file)
        hmi = WifiHmi(args.hmi, token, report["commands"], via_wsl=args.wifi_via_wsl)
        report["hmi_resolved_ip"] = hmi.resolved
        report["before"] = safe_status_projection(hmi.status())
        verify_unpowered_preflash(hmi.status())
        hmi.fail_safe_stop()

        manager = automation.Manager.connect(port=args.logic_port)
        devices = [d for d in manager.get_devices() if d.device_id == args.logic_device and not d.is_simulation]
        if len(devices) != 1:
            raise RuntimeError("exactly one matching physical Saleae is required; no flash changes made")
        report["logic_version"] = manager.get_app_info().app_version

        uno_may_be_modified = True
        program_uno(uno_bench, "flash_unoq_bench.log")
        nucleo_may_be_modified = True
        program_nucleo(nucleo_bench, "flash_nucleo_bench.log")
        time.sleep(UNOQ_ROUTER_BOOT_WAIT_S)
        post_flash_rpc = wait_status(
            hmi,
            lambda s: int(s.get("fw_build", 0)) == expected_uno_build
            and int(s.get("rpc_schema_version", 0)) >= 3,
            8.0,
            "UNO Q RouterBridge registration after bench flash",
        )
        report["post_flash_rpc"] = safe_status_projection(post_flash_rpc)
        hmi.command("CLEAR")
        bench_safe = wait_status(
            hmi,
            lambda s: str(s.get("state", "")).upper() == "SAFE"
            and int(s.get("pwm", 1)) == 0
            and int(s.get("bp_fault", 255)) == 0
            and int(s.get("bp_bad", s.get("bp_bad_cnt", 255))) == 0
            and int(s.get("bp_mcsdk_telemetry", 0)) == 1
            and int(s.get("bp_vbus_valid", 0)) == 1
            and float(s.get("vdc", 999.0)) <= 0.1,
            8.0,
            "bench UART and synthetic zero-bus telemetry",
        )
        report["bench_safe"] = safe_status_projection(bench_safe)
        if args.external_break_test:
            print("EXTERNAL_BKIN_BENCH_READY_WAITING_FOR_START_SIGNAL", flush=True)
            start_signal = out / "start.signal"
            deadline = time.monotonic() + 180.0
            while not start_signal.is_file():
                if time.monotonic() >= deadline:
                    raise RuntimeError("external BKIN start signal timed out")
                time.sleep(0.1)
        hmi.post("/api/arm-profile", {"profile": "lv"}, "ARM PROFILE LV")
        hmi.post("/api/hv-arm", {"action": "arm", "confirm": "ARM LV HV OFF"}, "ARM LV")
        hmi.command("DIAG ON")
        diag_ready = wait_status(hmi, lambda s: str(s.get("mode", "")).upper() == "DIAG", 3.0, "DIAG mode")
        report["diag_ready"] = safe_status_projection(diag_ready)

        if args.external_break_test:
            from wifi_bench_scenarios import operator_keepalive
            with operator_keepalive(hmi) as keepalive, ThreadPoolExecutor(max_workers=1) as pool:
                break_sample_rate_hz = 4_000_000
                future = pool.submit(capture, manager, args.logic_device,
                                     out / "external_break_capture", 18.0,
                                     break_sample_rate_hz)
                time.sleep(0.5)
                report["start_response"] = hmi.command("START")
                hmi.command("SET RUNLIMIT 15")
                (out / "short-now.signal").write_text("PWM START accepted; capture running\n", encoding="ascii")
                print("EXTERNAL_BKIN_PWM_STARTED_SHORT_TP23_TO_J4_MINUS_NOW", flush=True)
                tripped = wait_status(
                    hmi, lambda s: int(s.get("bp_fault", 0)) == 7 and int(s.get("pwm", 1)) == 0,
                    14.0, "latched external SD/BKIN trip",
                )
                report["tripped_status"] = safe_status_projection(tripped)
                rejected_code, rejected_payload = hmi.request("POST", "/api/start-sequence", {})
                report["restart_without_clear"] = {
                    "http_status": rejected_code,
                    "rejected": rejected_code != 200 or rejected_payload.get("ok") is not True,
                }
                active_csv = future.result(timeout=25)
            report["external_break_keepalive"] = keepalive
            report["external_break"] = analyze_external_break(active_csv, break_sample_rate_hz)
            if not report["external_break"]["pass"] or not report["restart_without_clear"]["rejected"]:
                raise RuntimeError("external SD/BKIN waveform or restart latch failed")
        elif args.software_break_test:
            from wifi_bench_scenarios import operator_keepalive
            with operator_keepalive(hmi) as keepalive, ThreadPoolExecutor(max_workers=1) as pool:
                break_sample_rate_hz = 4_000_000
                future = pool.submit(capture, manager, args.logic_device,
                                     out / "software_break_capture", 2.4,
                                     break_sample_rate_hz)
                time.sleep(0.3)
                report["start_response"] = hmi.command("START")
                tripped = wait_status(
                    hmi, lambda s: int(s.get("bp_fault", 0)) == 7 and int(s.get("pwm", 1)) == 0,
                    3.0, "latched TIM1 software break fault",
                )
                report["tripped_status"] = safe_status_projection(tripped)
                rejected_code, rejected_payload = hmi.request("POST", "/api/start-sequence", {})
                report["restart_without_clear"] = {
                    "http_status": rejected_code,
                    "rejected": rejected_code != 200 or rejected_payload.get("ok") is not True,
                }
                active_csv = future.result(timeout=12)
            report["software_break_keepalive"] = keepalive
            report["software_break"] = analyze_software_break(active_csv, break_sample_rate_hz)
            if not report["software_break"]["pass"] or not report["restart_without_clear"]["rejected"]:
                raise RuntimeError("TIM1 break waveform or restart latch failed")
        else:
            start_result = hmi.command("START")
            report["start_response"] = start_result
            active_csv = capture(
                manager, args.logic_device, out / "active_after_wifi_command", CAPTURE_DURATION_S
            )
            report["active_status"] = safe_status_projection(hmi.status())
            report["stop_after_active"] = hmi.fail_safe_stop()[1]
            stopped_status = wait_status(
                hmi,
                lambda s: int(s.get("pwm", 1)) == 0
                and (int(s.get("bp_status", 0x20)) & 0x20) == 0
                and float(s.get("bp_age_ms", 999999.0)) <= 500.0,
                2.0,
                "Nucleo hardware PWM inactive after STOP",
            )
            report["stopped_status"] = safe_status_projection(stopped_status)
            report["active"] = analyze_active(active_csv, args.require_em_stop_channel)

            stopped_csv = capture(manager, args.logic_device, out / "bench_stopped", CAPTURE_DURATION_S)
            report["bench_stopped"] = analyze_static(stopped_csv, settle_s=0.001)
            if not report["active"]["pass"] or not report["bench_stopped"]["pass"]:
                raise RuntimeError("PWM waveform or STOP-state analysis failed")
        if args.transition_scenarios:
            from wifi_bench_scenarios import run_transitions
            run_transitions(hmi, manager, args.logic_device, out, report)
        if args.all_scenarios:
            from wifi_bench_scenarios import run_scenarios
            run_scenarios(hmi, manager, args.logic_device, out, report)
        if args.stop_tail_test:
            from wifi_stop_tail_probe import run_probe
            run_probe(hmi, manager, args.logic_device, out, report, programmer, args.stlink)
        # Return the already-running HMI to its production profile while the
        # fault-free bench telemetry still permits a guarded profile change.
        hmi.command("CLEAR")
        wait_status(
            hmi,
            lambda s: int(s.get("pwm", 1)) == 0
            and int(s.get("estop", 1)) == 0
            and int(s.get("bp_fault", 255)) == 0
            and int(s.get("bp_bad", s.get("bp_bad_cnt", 255))) == 0,
            3.0,
            "fault-free bench state before HV profile restore",
        )
        hmi.post("/api/arm-profile", {"profile": "hv"}, "ARM PROFILE HV BEFORE RESTORE")
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
        report["error"] = error
    finally:
        if hmi is not None:
            code, payload = hmi.fail_safe_stop()
            report["final_stop_before_restore"] = {"http_status": code, "ok": payload.get("ok") is True}
            try:
                if hmi.status().get("hmi_arm_profile") != "hv":
                    hmi.command("CLEAR")
                    wait_status(
                        hmi,
                        lambda s: int(s.get("pwm", 1)) == 0
                        and int(s.get("estop", 1)) == 0
                        and int(s.get("bp_fault", 255)) == 0
                        and int(s.get("bp_bad", s.get("bp_bad_cnt", 255))) == 0,
                        3.0,
                        "fault-free bench recovery state",
                    )
                    hmi.post("/api/arm-profile", {"profile": "hv"}, "ARM PROFILE HV RECOVERY")
            except Exception as exc:
                report["pre_restore_profile_warning"] = f"{type(exc).__name__}: {exc}"
        try:
            if nucleo_may_be_modified and nucleo_production.is_file():
                program_nucleo(nucleo_production, "restore_nucleo_production.log")
                report["restored"]["nucleo"] = True
            elif not nucleo_may_be_modified:
                report["restored"]["nucleo"] = True
        except Exception as exc:
            report["restore_nucleo_error"] = f"{type(exc).__name__}: {exc}"
            error = error or "Nucleo production restore failed; keep the power stage disconnected"
        try:
            if uno_may_be_modified and uno_production.is_file():
                program_uno(uno_production, "restore_unoq_production.log")
                report["restored"]["uno_q"] = True
            elif not uno_may_be_modified:
                report["restored"]["uno_q"] = True
        except Exception as exc:
            report["restore_unoq_error"] = f"{type(exc).__name__}: {exc}"
            error = error or "UNO Q production restore failed"

        if hmi is not None and all(report["restored"].values()):
            try:
                restored = wait_status(
                    hmi,
                    lambda s: str(s.get("state", "")).upper() == "SAFE"
                    and int(s.get("pwm", 1)) == 0
                    and float(s.get("bp_age_ms", 999999.0)) <= 500.0
                    and int(s.get("bp_mcsdk_telemetry", 0)) == 1,
                    10.0,
                    "restored production status",
                )
                report["after_restore"] = safe_status_projection(restored)
                report["after_restore"]["zero_bus_mcsdk_fault_expected"] = bool(
                    float(restored.get("vdc", 999.0)) <= 0.1
                    and int(restored.get("bp_fault", 0)) == 5
                    and int(restored.get("pwm", 1)) == 0
                )
                if restored.get("hmi_arm_profile") != "hv":
                    hmi.command("CLEAR")
                    hmi.post("/api/arm-profile", {"profile": "hv"}, "ARM PROFILE HV AFTER RESTORE")
                    restored = wait_status(
                        hmi,
                        lambda s: s.get("hmi_arm_profile") == "hv"
                        and int(s.get("hmi_hv_armed", 1)) == 0
                        and int(s.get("pwm", 1)) == 0,
                        4.0,
                        "production HV arm profile restored",
                    )
                    report["after_restore"].update(safe_status_projection(restored))
                if manager is not None:
                    final_csv = capture(
                        manager, args.logic_device, out / "production_restored", CAPTURE_DURATION_S
                    )
                    report["production_outputs"] = analyze_static(final_csv)
                    if not report["production_outputs"]["pass"]:
                        error = error or "restored production PWM pins are not all static LOW"
            except Exception as exc:
                report["post_restore_error"] = f"{type(exc).__name__}: {exc}"
                error = error or "post-restore verification failed"
        if manager is not None:
            manager.close()
        if hmi is not None:
            hmi.close()

    report["pass"] = bool(
        error is None
        and (report.get("external_break", {}).get("pass") is True
             and report.get("restart_without_clear", {}).get("rejected") is True
             if args.external_break_test else
             report.get("software_break", {}).get("pass") is True
             and report.get("restart_without_clear", {}).get("rejected") is True
             if args.software_break_test else
             report.get("active", {}).get("pass") is True
             and report.get("bench_stopped", {}).get("pass") is True)
        and report.get("production_outputs", {}).get("pass") is True
        and all(report["restored"].values())
        and report.get("after_restore", {}).get("hmi_arm_profile") == "hv"
    )
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "pass": report["pass"],
        "error": error,
        "control_transport": report["control_transport"],
        "active_checks": report.get("active", {}).get("checks"),
        "software_break_checks": report.get("software_break", {}).get("checks"),
        "external_break_checks": report.get("external_break", {}).get("checks"),
        "restored": report["restored"],
        "report": str(out / "report.json"),
    }, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
