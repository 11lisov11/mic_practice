"""Install only the Nucleo BKIN-DMA timer fix with J1 off and a low DC bus."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "artifacts/live_bench_20261017/bkin_dma_arr_fix_r1"
URL = "http://192.168.1.138:8080"
STLINK_SERIAL = "003A002C3335510933383531"
PAIR = (2026101711, 2026101710)
PROGRAMMER = Path("C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def status() -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(URL + "/api/status", timeout=8) as response:
        payload = json.load(response)
    if payload.get("ok") is not True or not isinstance(payload.get("data"), dict):
        raise RuntimeError("HMI status is unavailable")
    return payload["data"]


def check_safe(s: dict) -> None:
    pair = (s.get("fw_build"), s.get("mc_fw_build"))
    if pair != PAIR:
        raise RuntimeError(f"unexpected running firmware pair: {pair}")
    if s.get("state") != "SAFE" or s.get("pwm") != 0 or s.get("hmi_hv_armed") != 0:
        raise RuntimeError("drive is not SAFE with PWM and HV arm off")
    for key in ("vdc", "bp_vdc"):
        value = s.get(key)
        if type(value) not in (int, float) or not 0 <= value <= 10:
            raise RuntimeError(f"{key} must be fresh and at or below 10 V, got {value}")
    for key in ("bp_vbus_age_ms", "bp_temp_age_ms", "mc_age_ms"):
        value = s.get(key)
        if type(value) not in (int, float) or not 0 <= value < 300:
            raise RuntimeError(f"telemetry is stale: {key}={value}")
    if s.get("bp_vbus_valid") != 1 or s.get("bp_temp_valid") != 1 or s.get("bp_temp_fault") != 0:
        raise RuntimeError("Nucleo bus/temperature telemetry is not valid")
    for key in ("bp_bad_cnt", "mc_bad_cnt", "bp_bad_sequence", "mc_bad_sequence",
                "bp_uart_error_flags", "mc_uart_error_flags", "bp_transport_fault", "mc_transport_fault"):
        if s.get(key) != 0:
            raise RuntimeError(f"UART is not clean: {key}={s.get(key)}")
    reason = s.get("mc_fault_reason")
    current, occurred = s.get("mc_fault_current_mask"), s.get("mc_fault_occurred_mask")
    if s.get("mc_fault") not in (0, 5) or reason not in (0, 8) or current not in (0, 4) or occurred not in (0, 4):
        raise RuntimeError(f"unexpected fault state: reason={reason}, masks={current}/{occurred}")


def stlink_port() -> str:
    data = json.loads(subprocess.check_output(["arduino-cli", "board", "list", "--format", "json"], text=True))
    for entry in data.get("detected_ports", []):
        props = entry.get("port", {}).get("properties", {})
        if props.get("serialNumber") == STLINK_SERIAL:
            return entry["port"]["address"]
    raise RuntimeError("Nucleo ST-Link is not connected to the PC")


def run(command: list[str], label: str, outdir: Path, report: dict, timeout: int = 180) -> str:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    (outdir / f"{label}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    report.setdefault("commands", []).append({"label": label, "exit_code": result.returncode})
    if result.returncode:
        raise RuntimeError(f"{label} failed; see {outdir / (label + '.log')}")
    return result.stdout


def verify_candidate() -> tuple[Path, dict]:
    manifest = json.loads((CANDIDATE / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "mic_ai.bkin_dma_arr_fix_candidate.v1":
        raise RuntimeError("unexpected candidate manifest")
    if manifest.get("pair_compatibility_ids") != list(PAIR) or manifest.get("nucleo_only_update") is not True:
        raise RuntimeError("candidate is not the intended Nucleo-only image")
    if manifest.get("selftest_pass") is not True or manifest.get("built") is not True:
        raise RuntimeError("candidate build and offline checks are incomplete")
    if manifest.get("control_protocol_changed") or manifest.get("pwm_or_motor_control_changed") or manifest.get("calibration_changed"):
        raise RuntimeError("candidate scope includes a prohibited control or calibration change")
    for relative, expected in manifest.get("source_sha256", {}).items():
        path = CANDIDATE / relative
        if not path.is_file() or sha(path) != expected.lower():
            raise RuntimeError(f"source changed after review: {relative}")
    image = CANDIDATE / "nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex"
    item = manifest.get("nucleo_hex", {})
    if not image.is_file() or sha(image) != item.get("sha256") or item.get("build_errors") != 0 or item.get("build_warnings") != 0:
        raise RuntimeError("Nucleo image hash/build verification failed")
    return image, manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-j1-off", action="store_true", help="confirm the mains/DC input at J1 is physically off")
    parser.add_argument("--outdir", type=Path)
    args = parser.parse_args()
    outdir = (args.outdir or ROOT / "artifacts/live_bench_20261017" / ("bkin_dma_arr_fix_install_" + uuid.uuid4().hex)).resolve()
    if outdir.exists():
        parser.error(f"output directory already exists: {outdir}")
    outdir.mkdir(parents=True)
    report = {"pass": False, "mcu_flash_commands": 0, "motor_commands": 0,
              "clear_commands": 0, "uno_flash_commands": 0, "j1_off_user_confirmed": args.confirm_j1_off,
              "pair_compatibility_ids": PAIR, "calibration_changed": False,
              "scope": "Nucleo diagnostic recorder only; no Uno/HMI/calibration/control changes"}
    try:
        if not args.confirm_j1_off:
            raise RuntimeError("J1-off confirmation is required")
        image, manifest = verify_candidate()
        report["image_sha256"] = sha(image)
        report["image_bytes"] = image.stat().st_size
        before = status()
        check_safe(before)
        report["before"] = before
        port = stlink_port()
        report["stlink_port"] = port
        if not PROGRAMMER.is_file():
            raise RuntimeError("STM32CubeProgrammer is unavailable")
        run([str(PROGRAMMER), "-c", "port=SWD", "mode=UR", "sn=" + STLINK_SERIAL,
             "-w", str(image), "-v", "-rst"], "flash_verify_nucleo", outdir, report)
        report["mcu_flash_commands"] = 1
        report["nucleo_readback_verified"] = True

        deadline = time.monotonic() + 40
        latest = None
        last_error = None
        while time.monotonic() < deadline:
            time.sleep(1)
            try:
                latest = status()
                check_safe(latest)
                if (latest.get("fw_build"), latest.get("mc_fw_build")) == PAIR:
                    report["after"] = latest
                    report["pair_live"] = True
                    report["pass"] = True
                    break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
        if not report.get("pair_live"):
            report["after"] = latest
            report["post_flash_error"] = last_error or "fresh pair telemetry did not return"
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        (outdir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in
          ("pass", "mcu_flash_commands", "nucleo_readback_verified", "pair_live", "error", "post_flash_error")}, ensure_ascii=False))
    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
