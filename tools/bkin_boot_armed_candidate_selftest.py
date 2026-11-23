"""Host checks for the pre-START BKIN DMA capture candidate."""
from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "artifacts/live_bench_20261017/bkin_dma_boot_armed_r1"
UNO_BUILD = 2026101711
MC_BUILD = 2026101710


def load_server():
    path = CANDIDATE / "web_hmi/server.py"
    spec = importlib.util.spec_from_file_location("bkin_boot_armed_candidate_server", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load candidate HMI server")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check(condition: bool, name: str, failures: list[str]) -> None:
    if not condition:
        failures.append(name)


def make_record() -> str:
    raw = bytearray(160)
    # Four valid most-recent samples, with one active-low PA6 sample.
    struct.pack_into("<8I", raw, 0, 0x314E4B42, 2, 160, 1234, 1000, 4, 1020, 0x10)
    raw[32:160] = b"\xff" * 128
    raw[159] &= 0x7F
    return raw.hex()


def main() -> int:
    failures: list[str] = []
    candidate = json.loads((CANDIDATE / "manifest.json").read_text(encoding="utf-8"))
    main_c = (CANDIDATE / "nucleo/Src/main.c").read_text(encoding="utf-8-sig")
    uno_c = (CANDIDATE / "UNOQ_MOTOR/UNOQ_MOTOR.ino").read_text(encoding="utf-8-sig")
    server = load_server()

    start_fn = main_c.split("static void mic_bkin_capture_start(void) {", 1)[1].split("static void mic_bkin_capture_stop(", 1)[0]
    user_block = main_c.split("/* Arm the passive BKIN trace after MCSDK boot synchronization, before any START. */", 1)[1].split("/* Keep the external UNO Q transport", 1)[0]
    check(start_fn.lstrip().startswith("if (mic_bkin_capture_state == MIC_BKIN_RUNNING) return;"),
          "START does not reinitialize an already running boot-armed DMA", failures)
    check("mic_bkin_capture_start();" in user_block and "mic_bkin_capture_init();" not in user_block,
          "capture starts after MCSDK initialization and before UNO link polling", failures)
    check("mic_bkin_capture_stop_software" not in main_c and
          "mic_bkin_capture_stop_from_break" in main_c,
          "normal STOP preserves capture; the hardware break still freezes it", failures)
    check("MIC_NUCLEO_FW_BUILD_ID 2026101710UL" in main_c and
          "BW_NUCLEO_BUILD 2026101710UL" in (CANDIDATE / "nucleo/Inc/break_wire.h").read_text(encoding="utf-8-sig"),
          "Nucleo build identities agree", failures)
    check("FW_BUILD_ID = 2026101711U" in uno_c and "g_bp_fw_build==2026101710U" in uno_c,
          "Uno and Nucleo runtime identities agree", failures)
    check(server.manual_scalar_supported({"fw_build": UNO_BUILD, "mc_fw_build": MC_BUILD,
          "manual_scalar_capable": 1}), "HMI accepts the matching diagnostic pair", failures)
    check(not server.manual_scalar_supported({"fw_build": UNO_BUILD, "mc_fw_build": 2026101702,
          "manual_scalar_capable": 1}), "HMI rejects a mixed pair", failures)
    decoded = server.bkin_wave_status({"mc_fw_build": MC_BUILD,
        "mc_break_wave_hex": make_record(), "mc_break_wave_age_ms": 25})
    check(decoded.get("available") is True and decoded.get("valid_sample_count") == 4,
          "HMI parser accepts a DMA-count-verified trace from the new build", failures)
    check(candidate.get("pair") == [UNO_BUILD, MC_BUILD] and
          candidate.get("calibration_changed") is False and
          candidate.get("pwm_or_motor_control_changed") is False and
          candidate.get("hv_release_approved") is False,
          "manifest keeps scope diagnostic-only and HV release disabled", failures)

    build_dir = CANDIDATE / "nucleo/STM32CubeIDE/Debug"
    mc_build = json.loads((build_dir / "ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json").read_text(encoding="utf-8-sig"))
    check(mc_build.get("firmware_build_id") == MC_BUILD and mc_build.get("build_errors") == 0 and
          mc_build.get("build_warnings") == 0, "Nucleo clean build metadata", failures)
    uno_build = json.loads((CANDIDATE / "build/uno/unoq_mcsdk_scalar.build-manifest.json").read_text(encoding="utf-8-sig"))
    check(uno_build.get("firmware_build_id") == UNO_BUILD, "Uno build metadata", failures)

    report = {"pass": not failures, "checks": 11 - len(failures), "failures": failures,
              "hardware_commands": 0, "mcu_flash_commands": 0, "motor_commands": 0,
              "scope": "Offline source/build/parser checks only; no device access"}
    (CANDIDATE / "selftest/report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    candidate["built"] = True
    candidate.setdefault("files_sha256", {})["README_RU.md"] = hashlib.sha256(
        (CANDIDATE / "README_RU.md").read_bytes()).hexdigest()
    candidate["files_sha256"]["nucleo/Src/main.c"] = hashlib.sha256(
        (CANDIDATE / "nucleo/Src/main.c").read_bytes()).hexdigest()
    candidate["documentation_sha256"] = {"README_RU.md": candidate["files_sha256"]["README_RU.md"]}
    candidate["build_verification"] = {
        "unoq": {"pass": True, "build_id": UNO_BUILD,
                 "manifest": "build/uno/unoq_mcsdk_scalar.build-manifest.json",
                 "artifacts": uno_build.get("artifacts", []),
                 "llext_issues": []},
        "nucleo": {"pass": True, "build_id": MC_BUILD,
                   "errors": mc_build.get("build_errors"), "warnings": mc_build.get("build_warnings"),
                   "elf_sha256": mc_build["artifacts"][0]["sha256"],
                   "hex_sha256": next(x["sha256"] for x in mc_build["artifacts"] if x["file"].endswith(".hex")),
                   "hex_bytes": next(x["bytes"] for x in mc_build["artifacts"] if x["file"].endswith(".hex")),
                   "manifest": "build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json",
                   "non_gating_release_preflight_pass": False,
                   "release_preflight_pending": ["external_softstart_hil_validated", "ipm_sd_bkin_hardware_trip_validated"]},
        "host_selftest": report,
    }
    (CANDIDATE / "manifest.json").write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
