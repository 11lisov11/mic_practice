"""Fail-closed tests for the Uno ownership installer; no hardware access."""
import hashlib
import json
from pathlib import Path
import tempfile

from install_unoq_control_owner import recoverable_peer_pause, safe_idle, verify_source_checks
from web_hmi_command_guard_selftest import safe_status


def main():
    cases = 0

    def rejected(call):
        nonlocal cases
        try:
            call()
        except (RuntimeError, KeyError, ValueError, TypeError):
            cases += 1
            return
        raise AssertionError("unsafe input accepted")

    status = safe_status(fw_build=2026100804, mc_fw_build=2026100801,
                         hmi_hv_armed=0,
                         rpc_schema_version=3, mc_capabilities=1,
                         bp_mcsdk_telemetry=1, bp_vbus_valid=1,
                         bp_vbus_raw=0, vdc=0.0, bp_vdc=0.0,
                         mc_age_ms=0, bp_vbus_age_ms=0, bp_temp_age_ms=0,
                         bp_temp_valid=1, bp_temp_fault=0, bp_temp_c=25.0,
                         bp_fault=5, precharge=0, pfc=0, brake=0, bp_ext=0,
                         mc_bad_cnt=0, mc_bad_integrity=0, mc_bad_sequence=0)
    assert safe_idle(status)
    assert safe_idle(dict(status, fw_build=2026101001))
    cases += 2
    for key, value in (
        ("pwm", 1), ("hmi_hv_armed", 1), ("state", "VF_RUN"),
        ("estop", 1), ("vdc", 2.01), ("bp_vdc", 3),
        ("bp_vbus_raw", 21), ("mc_age_ms", 300), ("bp_vbus_age_ms", float("nan")),
        ("bp_temp_fault", 1), ("precharge", 1), ("bp_ext", 1),
        ("fw_build", 2026101002), ("mc_fw_build", 2026100899),
        ("mc_bad_cnt", 1), ("mc_bad_integrity", 1), ("mc_bad_sequence", 1),
    ):
        rejected(lambda key=key, value=value: safe_idle(dict(status, **{key: value})))
    missing = dict(status)
    missing.pop("bp_vbus_valid")
    rejected(lambda: safe_idle(missing))
    prior = dict(status, mc_diag_valid=1, mc_fault_detail="first=MCSDK_FAULT", mc_fault_reason=8)
    paused = dict(prior, fw_build=2026101001, bp_fault=2,
                  mc_uart_error_flags=0, mc_last_bad_reason=0)
    assert recoverable_peer_pause(prior, paused)
    assert recoverable_peer_pause(prior, dict(paused, mc_fault_reason=13, mc_fault_detail="first=LINK_TIMEOUT"))
    cases += 2
    for key, value in (("pwm", 1), ("hmi_hv_armed", 1), ("vdc", 3),
                       ("mc_fault_detail", "first=CRC"), ("mc_bad_cnt", 1),
                       ("mc_uart_error_flags", 4), ("mc_last_bad_reason", 1)):
        assert not recoverable_peer_pause(prior, dict(paused, **{key: value}))
        cases += 1
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        path = root / "source.txt"
        path.write_text("reviewed", encoding="ascii")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        regression = {"pass": True, "sources_unchanged_during_tests": True,
                      "source_sha256": {"source.txt": digest}}
        ownership = {"pass": True, "removed_callback_guard_detected": True,
                     "sources": {"source.txt": digest}}
        verify_source_checks(root, regression, ownership)
        cases += 1
        for invalid in (
            dict(regression, **{"pass": False}),
            dict(regression, sources_unchanged_during_tests=False),
        ):
            rejected(lambda invalid=invalid: verify_source_checks(root, invalid, ownership))
        rejected(lambda: verify_source_checks(root, regression, dict(ownership, removed_callback_guard_detected=False)))
        path.write_text("changed", encoding="ascii")
        rejected(lambda: verify_source_checks(root, regression, ownership))
    print(json.dumps({"pass": True, "cases": cases, "hardware_commands": 0}))


if __name__ == "__main__":
    main()
