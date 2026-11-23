"""Remove only the accepted preparation wait deadline; retain active deadlines."""
import argparse
import hashlib
import json
from pathlib import Path

from prepare_mcsdk_logic_bench import replace_once

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/live_bench_20261012/boot_trial/candidate_r1/web_hmi/server.py"
CANDIDATE = ROOT / "artifacts/live_bench_20261012/local_button/candidate_r5"
UNO_CANDIDATE = ROOT / "artifacts/live_bench_20261012/local_button/uno_peer_r2"


def server(text):
    from prepare_ipm_break_wifi import source_hashes
    sources = json.loads((CANDIDATE / 'manifest.json').read_text())
    if source_hashes(CANDIDATE / 'nucleo') != sources['candidate_sha256']:
        raise RuntimeError('Local STOP sources changed after preparation')
    unchanged = set(sources['baseline_sha256']) - set(sources['changed_files'])
    if any(sources['baseline_sha256'][k] != sources['candidate_sha256'][k] for k in unchanged):
        raise RuntimeError('Local STOP measurement/PWM configuration changed')
    build = CANDIDATE / "nucleo/STM32CubeIDE/Debug"
    manifest = json.loads(next(build.glob('*.build-manifest.json')).read_text(encoding='utf-8-sig'))
    if manifest['firmware_build_id'] != 2026101204 or manifest['build_errors'] != 0:
        raise RuntimeError('Local STOP target build required')
    binary = next(build.glob('*.bin'))
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    if not any(x['file'] == binary.name and x['sha256'].lower() == digest for x in manifest['artifacts']):
        raise RuntimeError('Local STOP image changed')
    text = replace_once(text, 'BOOT_TRIAL_PAIR = (2026101108, 2026101102)',
                        'BOOT_TRIAL_PAIR = (2026101205, 2026101204)')
    text = replace_once(text, "'production_nucleo': 'd17b1ed8313b7e355e66681f90beaf84e7535e22504212f79ef44ce2bad5d37c'",
                        "'production_nucleo': '" + digest + "'")
    text = replace_once(text, 'BOOT_TRIAL_SCHEMA = "mic_ai.powered_trial.unoq1108.v1"',
                        'BOOT_TRIAL_SCHEMA = "mic_ai.powered_trial.local_stop1204.v1"')
    uno_build = UNO_CANDIDATE / 'uno_build'
    uno_manifest = json.loads((uno_build / 'unoq_mcsdk_scalar.build-manifest.json').read_text(encoding='utf-8-sig'))
    if uno_manifest['firmware_build_id'] != 2026101205:
        raise RuntimeError('Uno diagnostic peer build required')
    uno_digest = hashlib.sha256((uno_build / uno_manifest['flash_artifact']).read_bytes()).hexdigest()
    if not any(x['file'] == uno_manifest['flash_artifact'] and x['sha256'].lower() == uno_digest for x in uno_manifest['artifacts']):
        raise RuntimeError('Uno diagnostic peer image changed')
    text = replace_once(text, "'production_uno': '2d981c66e978be9cf2bc2b36a98f493b8350758ce0a36814867dfc510f8bffc8'",
                        "'production_uno': '" + uno_digest + "'")
    text = replace_once(text, '"idle_wifi", "autonomous", "sd_sample", "calibration",',
                        '"idle_wifi", "autonomous", "sd_sample", "calibration", "local_stop",')
    text = replace_once(text, '"unchanged_nucleo_pwm_with_supervisory_boot_fix"',
                        '"local_stop_with_hardware_pwm_validation"')
    text = replace_once(text, 'for key in ("nucleo_pwm_equivalence_pass", "calibration_contract_pass",',
                        'for key in ("nucleo_local_stop_source_audit_pass", "local_stop_hardware_validated",\n'
                        '                "new_pair_active_pwm_measured", "physical_idle_registers_current", "calibration_contract_pass",')
    text = replace_once(text, 'for key in ("new_pair_active_pwm_measured", "physical_idle_registers_current",\n                "hv_release_approved", "current_telemetry_qualified"):',
                        'for key in ("hv_release_approved", "current_telemetry_qualified"):')
    # Measurement configuration is unchanged; retain the old reviewed pair too.
    text = replace_once(text, '        BOOT_TRIAL_PAIR,\n    }',
                        '        BOOT_TRIAL_PAIR,\n        (2026101108, 2026101102),\n    }')
    # The signed-in authenticated preparation still validates proof freshness
    # before acceptance. It stores a non-actuating request, not an ARM lease.
    text = replace_once(text, 'profile="short") -> None:\n        if (type(valid_for_sec)',
                        'profile="short", wait_without_deadline: bool = False) -> None:\n'
                        '        if type(wait_without_deadline) is not bool:\n'
                        '            raise ValueError("invalid wait policy")\n'
                        '        if wait_without_deadline and (pair != BOOT_TRIAL_PAIR or profile != "short"):\n'
                        '            raise ValueError("unreviewed unlimited preparation wait")\n'
                        '        if (type(valid_for_sec)')
    text = replace_once(text, '        self.expires_at = self.created + valid_for_sec',
                        '        self.expires_at = None if wait_without_deadline else self.created + valid_for_sec\n'
                        '        self.invalidated_reason = None')
    text = replace_once(text, '        if self.consumed:\n            return\n        ok, reason = self.live_check',
                        '        if self.consumed or self.invalidated_reason:\n            return\n'
                        '        if self.expires_at is None and isinstance(data, dict) and (data.get("fw_build"), data.get("mc_fw_build")) != self.pair:\n'
                        '            self.invalidated_reason = "prepared peer identity changed"\n'
                        '            self.reset_observation(self.invalidated_reason)\n            return\n'
                        '        ok, reason = self.live_check')
    text = replace_once(text, '        if (self.last_seen is not None and (now - self.last_seen > 2',
                        '        if self.expires_at is None and self.last_good is not None and good < self.last_good:\n'
                        '            self.invalidated_reason = "prepared controller restarted"\n'
                        '            self.reset_observation(self.invalidated_reason)\n            return\n'
                        '        if (self.last_seen is not None and (now - self.last_seen > 2')
    text = replace_once(text, '        if time.monotonic() >= self.expires_at:',
                        '        if self.invalidated_reason:\n            return False, self.invalidated_reason\n'
                        '        if self.expires_at is not None and time.monotonic() >= self.expires_at:')
    text = replace_once(text, '"hmi_powered_trial_remaining_s": round(max(0, self.expires_at-time.monotonic()), 1),',
                        '"hmi_powered_trial_wait_limited": int(self.expires_at is not None),\n'
                        '                "hmi_powered_trial_remaining_s": None if self.expires_at is None else round(max(0, self.expires_at-time.monotonic()), 1),')
    text = replace_once(text, 'gate = PoweredTrialGate(remaining, pair=tuple(proof["pair"]),profile=COAST30_PROFILE if coast30 else "short")',
                        'gate = PoweredTrialGate(remaining, pair=tuple(proof["pair"]),profile=COAST30_PROFILE if coast30 else "short",\n'
                        '                                wait_without_deadline=tuple(proof["pair"]) == BOOT_TRIAL_PAIR)')
    # New local-stop image must not inherit an old-pair physical qualification.
    begin = text.index('def hv_arm_precheck(')
    end = text.index('\ndef arm_profile_switch_precheck(', begin)
    check = replace_once(text[begin:end], '    state = str(data.get("state", "")).upper()\n    state_code = _as_int(data, "state_code", STATE_CODES.get(state, -1))',
                        '    if cfg.profile == ARM_PROFILE_HV and _as_int(data, "mc_fw_build", -1) in (2026101201, 2026101203, 2026101204) and cfg.trial_gate is None:\n'
                        '        return False, "local STOP image awaits physical qualification"\n'
                        '    if _as_int(data, "bp_status", 0) & 0x80:\n'
                        '        return False, "local Nucleo STOP is latched; release button and explicitly CLEAR"\n'
                        '    state = str(data.get("state", "")).upper()\n    state_code = _as_int(data, "state_code", STATE_CODES.get(state, -1))')
    text = text[:begin] + check + text[end:]
    from prepare_local_stop_hmi_fix import patch_server
    return patch_server(text)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--outdir", type=Path, required=True)
    a = p.parse_args(); out = a.outdir.resolve(); out.mkdir(parents=True, exist_ok=False)
    target = out / "web_hmi/server.py"; target.parent.mkdir()
    target.write_text(server(BASE.read_text()), encoding="utf-8")
    report = dict(schema="mic_ai.trial_wait_fix.v1", prepared=True, installed=False,
                  hardware_commands=0, hv_release_approved=False,
                  preparation_wait_expiry_removed=True, active_run_limit_s=3,
                  active_arm_expiry_retained=True, proof_freshness_at_acceptance_retained=True,
                  process_restart_discards_preparation=True,
                  pair=[2026101205,2026101204], new_pair_hardware_evidence_required=True,
                  base_sha256=hashlib.sha256(BASE.read_bytes()).hexdigest(),
                  hmi_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
