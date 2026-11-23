"""Offline tests for the isolated BKIN diagnostic firmware handoff."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import install_bkin_dma_verified_pair as installer  # noqa: E402


def status(pair: tuple[int, int]) -> dict:
    return {
        "fw_build": pair[0], "mc_fw_build": pair[1], "state": "SAFE", "pwm": 0,
        "estop": 0, "hmi_hv_armed": 0, "hmi_hv_started": 0,
        "bp_fault": 0, "mc_fault": 0, "bp_temp_fault": 0,
        "bp_transport_fault": 0, "mc_transport_fault": 0,
        "bp_fault_reason": 0, "mc_fault_reason": 0,
        "bp_status": 1, "mc_status": 1,
        "bp_vbus_valid": 1, "bp_temp_valid": 1,
        "mc_age_ms": 10, "bp_vbus_age_ms": 10, "bp_temp_age_ms": 10,
        "vdc": 10.0, "bp_vdc": 10.0,
        "bp_bad_cnt": 0, "mc_bad_cnt": 0, "bp_uart_error_flags": 0,
        "mc_uart_error_flags": 0, "mc_last_uart_error_flags": 0,
        "bp_bad_sequence": 0, "mc_bad_sequence": 0,
        "bp_bad_integrity": 0, "mc_bad_integrity": 0, "mc_last_bad_reason": 0,
        "mc_fault_current_mask": 0, "mc_fault_occurred_mask": 0,
    }


def run_install(outdir: Path, handoff_statuses: list[dict | None], live_after: bool = True) -> tuple[int, dict, list[str]]:
    labels: list[str] = []
    original = {
        "argv": sys.argv,
        "verify_package": installer.verify_package,
        "live_status": installer.live_status,
        "ports": installer.ports,
        "run": installer.run,
        "calibration_hash": installer.calibration_hash,
        "wait_pair": installer.wait_pair,
        "PROGRAMMER": installer.PROGRAMMER,
    }
    try:
        sys.argv = ["install_bkin_dma_verified_pair.py", "--candidate", str(ROOT),
                    "--outdir", str(outdir), "--confirm-mains-j4-off"]
        fake_uno = outdir.parent / "uno.bin"
        fake_nuc = outdir.parent / "nuc.hex"
        fake_uno.write_bytes(b"uno-image")
        fake_nuc.write_bytes(b"nuc-image")
        installer.verify_package = lambda _candidate: (fake_uno, fake_nuc, {"installed": False})
        states = [status(installer.OLD_PAIR), status(installer.OLD_PAIR), *handoff_statuses]

        def next_status() -> dict:
            if not states:
                raise RuntimeError("mock telemetry unavailable")
            value = states.pop(0)
            if value is None:
                raise RuntimeError("mock telemetry unavailable")
            return value

        installer.live_status = next_status
        installer.ports = lambda: ("COM10", "COM13")

        def fake_run(_command: list[str], label: str, _outdir: Path, report: dict, _timeout: int = 180) -> str:
            labels.append(label)
            report["commands"].append({"label": label, "exit_code": 0})
            return ""

        installer.run = fake_run
        digest = "a" * 64
        installer.calibration_hash = lambda _outdir, _report: digest

        def fake_wait_pair(expected: tuple[int, int], _allowed: tuple[tuple[int, int], ...],
                           _timeout: int = 45, allow_startup_link_timeout: bool = False) -> dict:
            if not live_after:
                raise RuntimeError("mock RPC unavailable after app MCU reset")
            return status(expected)

        installer.wait_pair = fake_wait_pair
        installer.PROGRAMMER = Path(__file__).resolve()
        with contextlib.redirect_stdout(io.StringIO()):
            result = installer.main()
        report = json.loads((outdir / "report.json").read_text(encoding="utf-8"))
        return result, report, labels
    finally:
        sys.argv = original["argv"]
        for name in ("verify_package", "live_status", "ports", "run", "calibration_hash", "wait_pair", "PROGRAMMER"):
            setattr(installer, name, original[name])


def main() -> int:
    checks = 0
    with tempfile.TemporaryDirectory(prefix="bkin-install-selftest-") as tmp:
        root = Path(tmp)
        result, report, labels = run_install(root / "live", [status((installer.OLD_PAIR[0], installer.NEW_PAIR[1])),
                                                               status((installer.OLD_PAIR[0], installer.NEW_PAIR[1]))])
        assert result == 0 and report["pass"] is True
        assert labels == ["flash_verify_nucleo", "flash_uno", "verify_uno"]
        assert report["mcu_flash_commands"] == 2 and report["motor_commands"] == 0
        checks += 1

        boot_timeout = status(installer.NEW_PAIR)
        boot_timeout.update({
            "bp_fault": 2, "mc_fault": 2, "bp_fault_reason": 13, "mc_fault_reason": 13,
            "bp_status": 25, "mc_status": 25, "bp_transport_fault": 7, "mc_transport_fault": 7,
            "bp_bad_cnt": 1, "mc_bad_cnt": 1, "mc_last_bad_reason": 13,
        })
        installer.validate_status(boot_timeout, (installer.NEW_PAIR,), allow_startup_link_timeout=True)
        checks += 1

        invalid_timeout = dict(boot_timeout)
        invalid_timeout["mc_bad_integrity"] = 1
        try:
            installer.validate_status(invalid_timeout, (installer.NEW_PAIR,), allow_startup_link_timeout=True)
        except RuntimeError:
            pass
        else:
            raise AssertionError("startup LINK_TIMEOUT with a bad-integrity frame must be rejected")
        checks += 1

        bus_off = status(installer.NEW_PAIR)
        bus_off.update({"bp_fault": 5, "mc_fault": 5, "bp_fault_reason": 8,
                        "mc_fault_reason": 8, "mc_fault_occurred_mask": 4})
        installer.validate_post_flash_status(bus_off)
        checks += 1

        unsafe_fault = dict(bus_off)
        unsafe_fault["mc_fault_current_mask"] = 0x40
        try:
            installer.validate_post_flash_status(unsafe_fault)
        except RuntimeError:
            pass
        else:
            raise AssertionError("post-flash current fault other than bus-off undervoltage must be rejected")
        checks += 1

        result, report, labels = run_install(root / "recovery", [None, None], live_after=False)
        assert result == 0 and report["recovery_required"] is True
        assert report["flash_pair_verified"] is True and report["pair_live"] is False
        assert labels == ["flash_verify_nucleo", "flash_uno", "verify_uno"]
        checks += 1

    print(json.dumps({"pass": True, "checks": checks, "hardware_commands": 0,
                      "mcu_flash_commands": 0, "motor_commands": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
