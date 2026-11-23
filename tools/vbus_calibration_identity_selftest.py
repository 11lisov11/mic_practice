"""Offline regression checks for audited UNO Q bridge compatibility."""
import copy
import json
import tempfile
from pathlib import Path

from web_hmi_command_guard_selftest import load_server_module, safe_status


def main():
    mod = load_server_module(Path(__file__).resolve().parents[1])
    checked = 0

    def check(condition, name):
        nonlocal checked
        if not condition:
            raise AssertionError(name)
        checked += 1

    old = safe_status(fw_build=2026092901, mc_fw_build=2026100601,
                      bp_mcsdk_telemetry=1, bp_vbus_valid=1,
                      bp_vbus_raw=0, vdc=0.0, bp_vdc=0.0)
    new = dict(old, fw_build=2026100612)
    high = dict(new, vdc=325.0, bp_vdc=325.0, bp_vbus_raw=3250)
    old_id = mod._vbus_calibration_identity(old)
    new_id = mod._vbus_calibration_identity(new)
    for left in (old_id, new_id):
        for right in (old_id, new_id):
            check(mod._vbus_calibration_identity_matches(left, right),
                  "known bridge pair retains measurement contract")
    for field, value in (
        ("fw_build", 2026100613), ("mc_fw_build", 2026100602),
        ("rpc_schema_version", 4), ("mc_capabilities", 3),
        ("mc_mcsdk_telemetry", 0), ("fw_build", []),
    ):
        changed = dict(new_id, **{field: value})
        check(not mod._vbus_calibration_identity_matches(old_id, changed),
              f"changed or malformed {field} is rejected")
    missing = dict(new_id)
    missing.pop("rpc_schema_version")
    check(not mod._vbus_calibration_identity_matches(old_id, missing),
          "missing identity field fails closed")
    check(not mod._vbus_calibration_identity_matches(old_id, dict(new_id, extra=1)),
          "unexpected identity field fails closed")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "vbus.json"
        store = mod.VbusCalibrationStore(str(path))
        capture = mod.vbus_capture_summary([old] * 20, 0.0)
        ok, _, snapshot = store.record_capture(capture, old)
        check(ok and not snapshot["valid"], "zero alone never unlocks")
        capture = mod.vbus_capture_summary([high] * 20, 322.7)
        ok, _, snapshot = store.record_capture(capture, high)
        check(ok and snapshot["valid"], "high capture survives audited bridge update")
        original_bytes = path.read_bytes()
        original_record = json.loads(original_bytes)
        check(original_record["identity"] == old_id, "capture identity is not rewritten")
        reloaded = mod.VbusCalibrationStore(str(path))
        check(reloaded.is_valid(high), "saved points survive reload and audited update")
        check(path.read_bytes() == original_bytes, "validity check does not alter evidence")
        check(reloaded.is_valid(old), "audited bridge rollback retains calibration")
        diagnostic = dict(high, fw_build=2026100701, mc_fw_build=2026100701)
        check(reloaded.is_valid(diagnostic), "diagnostic-only pair retains Vbus contract")
        check(reloaded.is_valid(dict(high, fw_build=2026100702, mc_fw_build=2026100702)),
              "first and last-cause update preserves measurement contract")
        check(reloaded.is_valid(dict(high, fw_build=2026100703, mc_fw_build=2026100703)),
              "interrupt RX update preserves measurement contract")
        check(reloaded.is_valid(dict(high, fw_build=2026100705, mc_fw_build=2026100705)),
              "ramp owner update preserves unchanged Vbus measurement fields")
        check(reloaded.is_valid(dict(high, fw_build=2026100706, mc_fw_build=2026100705)),
              "stop/run deadline update preserves unchanged Vbus measurement fields")
        check(reloaded.is_valid(dict(high, fw_build=2026100707, mc_fw_build=2026100707)),
              "break IRQ rearm update preserves unchanged Vbus measurement fields")
        for nucleo_build in (2026100707, 2026100708):
            check(reloaded.is_valid(dict(high, fw_build=2026100708, mc_fw_build=nucleo_build)),
                  "async CLEAR diagnostic update preserves unchanged Vbus measurement fields")
        check(not reloaded.is_valid(dict(high, fw_build=2026100707, mc_fw_build=2026100708)),
              "old decoder cannot authorize new diagnostic build")
        check(reloaded.is_valid(dict(high, fw_build=2026100709, mc_fw_build=2026100708)),
              "matrix-only update preserves unchanged Vbus measurement fields")
        check(not reloaded.is_valid(dict(high, fw_build=2026100709, mc_fw_build=2026100709)),
              "unreviewed motor-controller identity remains rejected")
        check(reloaded.is_valid(dict(high, fw_build=2026100709, mc_fw_build=2026100710)),
              "RX fault guards preserve unchanged Vbus measurement fields")
        check(reloaded.is_valid(dict(high, fw_build=2026100709, mc_fw_build=2026100801)),
              "atomic UART command publication preserves unchanged Vbus measurement fields")
        check(reloaded.is_valid(dict(high, fw_build=2026100802, mc_fw_build=2026100801)),
              "diagnostic decoder identity update preserves Vbus measurement fields")
        check(reloaded.is_valid(dict(high, fw_build=2026100803, mc_fw_build=2026100801)),
              "passive sender timing counters preserve Vbus measurement fields")
        check(reloaded.is_valid(dict(high, fw_build=2026101001, mc_fw_build=2026100801)),
              "serialized control ownership preserves unchanged Vbus measurement fields")
        check(reloaded.is_valid(dict(high, fw_build=2026101002, mc_fw_build=2026100801)),
              "runtime mutex initialization preserves unchanged Vbus measurement fields")
        v3 = dict(high, fw_build=2026101004, mc_fw_build=2026101003)
        check(reloaded.is_valid(v3), "paired CRC32C transport retains unchanged Vbus scaling")
        pending_gate = mod.HvArmConfig(enabled=True, ttl_sec=30.0, min_vdc=250.0, max_vdc=385.0)
        ok, reason = mod.hv_arm_precheck(v3, pending_gate, vbus_calibrated=True)
        check(not ok and "explicitly prepared bounded powered trial" in reason,
              "retained calibration does not authorize unqualified v3 powered start")
        v3_timing = dict(high, fw_build=2026101005, mc_fw_build=2026101003)
        check(reloaded.is_valid(v3_timing), "length-aware UART diagnostic update keeps calibration")
        ok, reason = mod.hv_arm_precheck(v3_timing, pending_gate, vbus_calibrated=True)
        check(not ok and "explicitly prepared bounded powered trial" in reason, "v3 timing correction cannot bypass HV gate")
        v3_estop = dict(high, fw_build=2026101007, mc_fw_build=2026101006)
        check(reloaded.is_valid(v3_estop), "latched-ESTOP watchdog fix preserves Vbus scaling")
        ok, reason = mod.hv_arm_precheck(v3_estop, pending_gate, vbus_calibrated=True)
        check(not ok and "explicitly prepared bounded powered trial" in reason, "v3 ESTOP fix keeps powered start blocked")
        sender_fix = dict(high, fw_build=2026101008, mc_fw_build=2026101006)
        check(reloaded.is_valid(sender_fix), "sender-only fix preserves Vbus measurement contract")
        ok, reason = mod.hv_arm_precheck(sender_fix, pending_gate, vbus_calibrated=True)
        check(not ok and "explicitly prepared bounded powered trial" in reason,
              "sender-only fix does not grant general powered-start permission")
        check(not reloaded.is_valid(dict(sender_fix, mc_fw_build=2026101007)),
              "sender fix cannot authorize an unknown motor-controller image")
        for uno, nucleo in ((2026101004, 2026100801), (2026101002, 2026101003),
                            (2026101006, 2026101003), (2026101004, 2026101099)):
            check(not reloaded.is_valid(dict(high, fw_build=uno, mc_fw_build=nucleo)),
                  "mixed, future and diagnostic v3 peers remain rejected")
        check(path.read_bytes() == original_bytes,
              "ownership update compatibility never rewrites stored measurements")
        check(not reloaded.is_valid(dict(high, fw_build=2026101003, mc_fw_build=2026100801)),
              "future supervisory firmware is not implicitly approved")
        check(not reloaded.is_valid(dict(high, fw_build=2026101001, mc_fw_build=2026100899)),
              "ownership update cannot authorize logic fixture calibration")
        check(not reloaded.is_valid(dict(high, fw_build=2026101002, mc_fw_build=2026100899)),
              "runtime mutex update cannot authorize fixture calibration")
        check(not reloaded.is_valid(dict(high, fw_build=2026100802, mc_fw_build=2026100899)),
              "logic-only fixture never inherits HV calibration approval")
        check(not reloaded.is_valid(dict(high, fw_build=2026100709, mc_fw_build=2026100802)),
              "next unreviewed controller remains rejected")
        check(not reloaded.is_valid(dict(high, fw_build=2026100709, mc_fw_build=2026100711)),
              "future unreviewed controller remains rejected")
        check(not reloaded.is_valid(dict(diagnostic, fw_build=2026100612)),
              "old bridge cannot authorize new diagnostic layout")
        for field, value in (("fw_build", 2026100613), ("mc_fw_build", 2026100602),
                             ("rpc_schema_version", 4), ("bp_mcsdk_telemetry", 0)):
            check(not reloaded.is_valid(dict(high, **{field: value})),
                  f"stored points reject changed {field}")
        gate = mod.HvArmConfig(enabled=True, ttl_sec=30.0, min_vdc=250.0, max_vdc=385.0)
        for field, value in (("pwm", 1), ("bp_fault", 5), ("estop", 1),
                             ("bp_rsp_age_ms", 999999), ("bp_temp_fault", 1)):
            ok, _ = mod.hv_arm_precheck(dict(high, **{field: value}), gate,
                                      vbus_calibrated=reloaded.is_valid(high))
            check(not ok, f"retained calibration cannot bypass {field}")
        damaged = copy.deepcopy(original_record)
        damaged["points"]["zero"]["meter_vdc"] = 1.0
        path.write_text(json.dumps(damaged), encoding="utf-8")
        check(not mod.VbusCalibrationStore(str(path)).is_valid(high),
              "tampered saved zero is rejected")
    print(json.dumps({"pass": True, "cases": checked,
                      "scope": "offline; no board commands or calibration changes"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
