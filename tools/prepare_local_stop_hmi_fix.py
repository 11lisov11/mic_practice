"""Prepare the observational LOCAL STOP HMI fix from the installed frozen source."""
import argparse
import hashlib
import json
from pathlib import Path

from prepare_mcsdk_logic_bench import replace_once

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/live_bench_20261012/local_button/wait_candidate_r6/web_hmi/server.py"
BASE_SHA = "5b9a25097b8d590db98ddcd37b121f30f573f4465fea67c512231a2f0dc40d15"
UI_SHA = "8ccce782140e81758f7e49681b57bfcba275e11613384404e837f582b0748373"


def patch_server(text: str) -> str:
    # arm_snapshot contains only ARM metadata; raw status is its argument.
    broken = ('        snapshot["hmi_local_stop_latched"] = int(bool(_as_int(snapshot, "bp_status", 0) & 0x80))\n'
              '        if snapshot["hmi_local_stop_latched"]:\n'
              '            snapshot["mc_fault_detail"] = "LOCAL_STOP_PC13; " + str(snapshot.get("mc_fault_detail", ""))\n')
    if broken in text:
        text = replace_once(text, broken, '')
    text = replace_once(text, '        snapshot["hmi_powered_trial_supported"] = 1',
                        '        snapshot["hmi_local_stop_latched"] = local_stop_latched(status)\n'
                        '        snapshot["hmi_powered_trial_supported"] = 1')
    text = replace_once(text, 'def with_motor_controller_aliases(data: dict) -> dict:',
                        'def local_stop_latched(data: Optional[dict]) -> int:\n'
                        '    """Derive the current latch from controller telemetry, independently of first fault."""\n'
                        '    return int(bool(_as_int(data or {}, "bp_status", 0) & 0x80))\n\n\n'
                        'def with_motor_controller_aliases(data: dict) -> dict:')
    text = replace_once(text, '    data["mc_fault_detail"] = motor_fault_detail(data)',
                        '    data["hmi_local_stop_latched"] = local_stop_latched(data)\n'
                        '    data["mc_fault_detail"] = motor_fault_detail(data)')
    text = replace_once(text, 'def motor_fault_detail(data: dict) -> str:\n',
                        'def motor_fault_detail(data: dict) -> str:\n'
                        '    current = "current=LOCAL_STOP_PC13; " if local_stop_latched(data) else ""\n')
    text = replace_once(text, '        return "cause unavailable in installed firmware"',
                        '        return current + "cause unavailable in installed firmware"')
    text = replace_once(text, '    return (f"first={label} UART=',
                        '    return (current + f"first={label} UART=')
    text = replace_once(text, '        "enc_status", "hmi_hv_armed", "hmi_operator_heartbeat_age_s",',
                        '        "enc_status", "hmi_hv_armed", "hmi_operator_heartbeat_age_s",\n'
                        '        "hmi_local_stop_latched",')
    text = replace_once(text, '    KEY_FIELDS = (\n',
                        '    KEY_FIELDS = (\n        "mc_fault", "hmi_local_stop_latched",\n')
    text = replace_once(text, '        return sample\n',
                        '        sample["hmi_local_stop_latched"] = local_stop_latched(data)\n'
                        '        return sample\n')
    text = replace_once(text, '        has_cause = bool(first_reason or active)',
                        '        has_cause = bool(first_reason or active or local_stop_latched(data))')
    text = replace_once(text, '                self._event_summary = f"{label}; UART=',
                        '                current = "current=LOCAL_STOP_PC13; first=" if local_stop_latched(data) else ""\n'
                        '                self._event_summary = current + f"{label}; UART=')
    text = replace_once(text, '    def maybe_log_fault_diagnostics(self, data: dict) -> None:\n',
                        '    def maybe_log_fault_diagnostics(self, data: dict) -> None:\n'
                        '        data["hmi_local_stop_latched"] = local_stop_latched(data)\n'
                        '        data["mc_fault_detail"] = motor_fault_detail(data)\n')
    text = replace_once(text, '        if reason or active:\n',
                        '        if reason or active or local_stop_latched(data):\n')
    text = replace_once(text, '            if _as_int(data, "mc_diag_valid", 0) != 1:\n                key += (active,)',
                        '            key += (active, local_stop_latched(data))')
    text = replace_once(text, '            f" mc_diag_valid={data.get(\'mc_diag_valid\', 0)} mc_fault_reason={data.get(\'mc_fault_reason\', 0)}"',
                        '            f" mc_diag_valid={data.get(\'mc_diag_valid\', 0)} mc_fault_reason={data.get(\'mc_fault_reason\', 0)}"\n'
                        '            f" hmi_local_stop_latched={local_stop_latched(data)}"')
    return text


def patch_ui(text: str) -> str:
    text = replace_once(text, 'function mcFaultSummary(data, code) {\n',
                        'function mcLocalStopLatched(data) {\n'
                        '  return (Number(mcField(data, "status", 0)) & 0x80) !== 0;\n'
                        '}\n\n'
                        'function mcFaultSummary(data, code) {\n'
                        '  if (mcLocalStopLatched(data)) return "ЛОКАЛЬНЫЙ STOP B1 (PC13)";\n')
    return replace_once(text, 'const linkState = mcFault !== 0 ? mcFaultSummary(data, mcFault)',
                        'const linkState = mcFault !== 0 || mcLocalStopLatched(data) ? mcFaultSummary(data, mcFault)')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(out: Path) -> dict:
    if sha(BASE) != BASE_SHA:
        raise RuntimeError("Frozen installed HMI changed")
    # UI is separately pinned; do not fold unrelated local UI changes into a refresh.
    ui = ROOT / "artifacts/live_bench_20261012/local_button/hmi_stop_remote_before_r1/app.js"
    if sha(ui) != UI_SHA:
        raise RuntimeError("Installed UI baseline changed")
    out.mkdir(parents=True, exist_ok=False)
    target = out / "web_hmi/server.py"
    target.parent.mkdir()
    target.write_text(patch_server(BASE.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    js = out / "web_hmi/static/app.js"
    js.parent.mkdir()
    js.write_text(patch_ui(ui.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    report = dict(schema="mic_ai.local_stop_hmi_fix.v1", installed=False,
                  base_sha256=BASE_SHA, base_ui_sha256=UI_SHA,
                  hmi_sha256=sha(target), ui_sha256=sha(js),
                  pair=[2026101205, 2026101204], hardware_commands=0,
                  mcu_firmware_changed=False, first_fault_snapshot_modified=False,
                  calibration_file_modified=False, control_guards_changed=False,
                  active_pwm_stop_timing_measured=False, hv_release_approved=False)
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.outdir.resolve()), indent=2))
