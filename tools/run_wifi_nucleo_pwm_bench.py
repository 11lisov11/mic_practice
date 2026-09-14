#!/usr/bin/env python3
"""Prove Wi-Fi -> UNO Q -> UART -> Nucleo PWM, then restore production images."""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from nucleo_logic_capture import CHANNEL_MAP, capture_checks
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
    def __init__(self, base_url: str, token: str, report_commands: list[dict[str, Any]]) -> None:
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
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if method != "GET":
            headers["X-UNOQ-Control-Token"] = self.token
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
            "transport": "direct_wifi_http",
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


def capture(manager: Any, device_id: str, folder: Path, duration_s: float) -> Path:
    from saleae import automation

    folder.mkdir(parents=True, exist_ok=False)
    with manager.start_capture(
        device_id=device_id,
        device_configuration=automation.LogicDeviceConfiguration(
            enabled_digital_channels=CAPTURE_CHANNELS,
            digital_sample_rate=SAMPLE_RATE_HZ,
        ),
        capture_configuration=automation.CaptureConfiguration(
            capture_mode=automation.TimedCaptureMode(duration_seconds=duration_s),
        ),
    ) as session:
        session.wait()
        session.save_capture(str(folder / "capture.sal"))
        session.export_raw_data_csv(directory=str(folder / "csv"), digital_channels=CAPTURE_CHANNELS)
    return folder / "csv" / "digital.csv"


def analyze_active(csv_path: Path, require_em_stop: bool = False) -> dict[str, Any]:
    analysis = analyze_csv(
        csv_path,
        expect_pwm=True,
        selected_sample_rate_hz=SAMPLE_RATE_HZ,
        max_sample_period_ns=100.0,
    )
    checks = capture_checks(analysis, True)["checks"]
    checks["carrier_10khz"] = all(
        abs(channel["freq_hz_from_rising"] - PWM_HZ) <= 100.0
        for channel in analysis["channels"].values()
    )
    checks["deadtime_1_8_to_2_2_us"] = all(
        pair["min_gap_s"] is not None and 1.8e-6 <= pair["min_gap_s"] <= 2.2e-6
        for pair in analysis["pairs"].values()
    )
    times, values = load_csv(csv_path, [6])
    em_stop = channel_summary(times, values[6])
    em_stop_held_low = (
        em_stop["initial"] == 0 and em_stop["final"] == 0 and em_stop["edges"] == 0
    )
    checks["pa6_em_stop_held_low"] = em_stop_held_low
    required_checks = {key: value for key, value in checks.items() if key != "pa6_em_stop_held_low"}
    if require_em_stop:
        required_checks["pa6_em_stop_held_low"] = em_stop_held_low
    return {
        "pass": all(required_checks.values()),
        "checks": checks,
        "required_checks": sorted(required_checks),
        "em_stop_required": require_em_stop,
        "em_stop": em_stop,
        "analysis": analysis,
    }


def analyze_static(csv_path: Path, settle_s: float = 0.0) -> dict[str, Any]:
    analysis = analyze_csv(
        csv_path,
        selected_sample_rate_hz=SAMPLE_RATE_HZ,
        max_sample_period_ns=100.0,
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
    parser.add_argument("--confirm-j7-disconnected", action="store_true")
    parser.add_argument("--confirm-hv-off", action="store_true")
    parser.add_argument("--hmi", default="http://192.168.1.138:8080")
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--adb-device", default="3880458060")
    parser.add_argument("--token-file", default="/home/arduino/.config/mic-ai/control_token")
    parser.add_argument("--uno-port", default="COM10")
    parser.add_argument("--stlink", default="003A002C3335510933383531")
    parser.add_argument("--logic-device", default="A7D1BB81883C0092")
    parser.add_argument("--logic-port", type=int, default=10430)
    parser.add_argument("--require-em-stop-channel", action="store_true")
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    if not (args.confirm_j7_disconnected and args.confirm_hv_off):
        parser.error("active bench requires explicit confirmation that J7/IPM is disconnected and HV is off")

    from saleae import automation

    root = Path(__file__).resolve().parents[1]
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    logs = out / "logs"
    logs.mkdir()
    bench_build = out / "unoq_logic_bench_build"
    bench_build.mkdir()
    uno_bench = bench_build / "UNOQ_MOTOR.ino.elf-zsk.bin"
    nucleo_bench = root / "nucleo_g431_uart_bridge_pio/.pio/build/nucleo_g431_pwm_bench/firmware.bin"
    uno_production = root / "firmware/ready_to_flash/uno_q_mcu/UNOQ_MOTOR.ino.elf-zsk.bin"
    nucleo_production = root / "firmware/ready_to_flash/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex"
    programmer = Path("C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe")
    verify_cfg = root / "tools/verify_unoq_sketch.cfg"
    arduino_cli = "arduino-cli"
    report: dict[str, Any] = {
        "schema": "mic_ai.wifi_nucleo_pwm_bench.v1",
        "host_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "logic_only_no_power_stage",
        "hmi_url": args.hmi,
        "control_transport": "direct_wifi_http",
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
        ], logs / ("write_" + log_name), timeout=90.0)
        run_logged([
            arduino_cli, "upload", "-p", args.uno_port, "-b", "arduino:zephyr:unoq", "-i", str(image),
            "--upload-property", f"upload.artifacts.sketch={image}",
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
            ["platformio", "run", "-d", str(root / "nucleo_g431_uart_bridge_pio"), "-e", "nucleo_g431_pwm_bench"],
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
        hmi = WifiHmi(args.hmi, token, report["commands"])
        report["hmi_resolved_ip"] = hmi.resolved
        report["before"] = safe_status_projection(hmi.status())
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
            lambda s: int(s.get("fw_build", 0)) == 2026091401
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
        hmi.post("/api/arm-profile", {"profile": "lv"}, "ARM PROFILE LV")
        hmi.post("/api/hv-arm", {"action": "arm", "confirm": "ARM LV HV OFF"}, "ARM LV")
        hmi.command("DIAG ON")
        diag_ready = wait_status(hmi, lambda s: str(s.get("mode", "")).upper() == "DIAG", 3.0, "DIAG mode")
        report["diag_ready"] = safe_status_projection(diag_ready)

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

    report["pass"] = bool(
        error is None
        and report.get("active", {}).get("pass") is True
        and report.get("bench_stopped", {}).get("pass") is True
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
        "restored": report["restored"],
        "report": str(out / "report.json"),
    }, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
