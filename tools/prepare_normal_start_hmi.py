"""Prepare ordinary repeatable START for the retained 1411/1410 MCU images."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'artifacts/live_bench_20261014/pwm_filter_pair_r7/production/web_hmi/server.py'
OUT = ROOT / 'artifacts/live_bench_20261014/normal_start_hmi_r1'
CAL_SHA = 'a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    original = SOURCE.read_text(encoding='utf-8')
    assert sha(SOURCE) == '93d21c9381dc0e93613f3a638497ccb6b6525c4051f7c117068382a82ebcf0c4'
    comparison = ROOT / 'artifacts/live_bench_20261014/snapshot_stop_sync_hil_r1/working_bus_on_1791997952551152700/independent_comparison/report.json'
    proof = json.loads(comparison.read_text())
    assert proof['measurement_comparison_pass'] and proof['samples'] == 20
    assert proof['meter_vdc'] == 316 and proof['reported_mean_v'] == 319
    assert proof['original_calibration_unchanged'] and proof['uart_errors_zero']
    assert proof['error_percent'] < 3 and proof['reported_std_v'] < proof['allowed_std_v']
    zero = ROOT / 'artifacts/live_bench_20261014/snapshot_stop_sync_hil_r1/vbus_preservation_review_1791995033559009700/report.json'
    zp = json.loads(zero.read_text()); assert zp['zero_check_pass'] and zp['original_calibration_unchanged']
    assert zp['current_identity']['fw_build'] == 2026101411 and zp['current_identity']['mc_fw_build'] == 2026101410
    assert zp['original_calibration_sha256'] == CAL_SHA
    pwm = ROOT / 'artifacts/live_bench_20261014/snapshot_stop_sync_hil_r1/FINAL_RESULT.json'
    pp = json.loads(pwm.read_text()); assert pp['pass'] and pp['strict_detached_capture_pass'] and pp['working_firmware_verified']
    assert pp['installed_pair'] == [2026101411,2026101410]
    text = original
    old = '        (2026101108, 2026101102),\n    }'
    new = '''        (2026101108, 2026101102),
        # Retained measurement scale/divider; corrected IIR bias was audited.
        # Same stand: zero check0.32/0 V and working check316/319 V (20 samples).
        # Keep original capture identities and points. Unknown/fixture pairs fail.
        (2026101411, 2026101410),
    }'''
    assert text.count(old) == 1; text = text.replace(old,new)
    old = '''    if cfg.profile == ARM_PROFILE_HV and _as_int(data or {}, "mc_fw_build", -1) in (2026101404, 2026101499, 2026101406, 2026101497, 2026101408, 2026101495, 2026101410, 2026101493):
        return False, "PWM/filter update awaits new calibration and physical qualification"'''
    new = '''    if cfg.profile == ARM_PROFILE_HV and _as_int(data or {}, "mc_fw_build", -1) == 2026101410 and _as_int(data or {}, "fw_build", -1) != 2026101411:
        return False, "working motor-controller image requires its matching supervisory firmware"
    if cfg.profile == ARM_PROFILE_HV and _as_int(data or {}, "mc_fw_build", -1) in (2026101404, 2026101499, 2026101406, 2026101497, 2026101408, 2026101495, 2026101493):
        return False, "PWM/filter update awaits new calibration and physical qualification"'''
    assert text.count(old) == 1; text = text.replace(old,new)
    compile(text,str(OUT / 'web_hmi/server.py'),'exec')
    left,right = ast.parse(original),ast.parse(text)
    changed=[]
    assert len(left.body)==len(right.body)
    for before,after in zip(left.body,right.body):
        if ast.dump(before,include_attributes=False)!=ast.dump(after,include_attributes=False):
            changed.append(getattr(before,'name',type(before).__name__))
    assert changed==['_vbus_calibration_identity_matches','hv_arm_precheck'],changed
    (OUT / 'web_hmi').mkdir(parents=True,exist_ok=False)
    target=OUT / 'web_hmi/server.py'; target.write_text(text,encoding='utf-8',newline='\n')
    manifest=dict(schema='mic_ai.normal_start_hmi.v1',pair=[2026101411,2026101410],base_hmi_sha256=sha(SOURCE),
                  hmi_sha256=sha(target),changed_functions=changed,ordinary_repeatable_start=True,
                  mcu_images_unchanged=True,calibration_points_unchanged=True,one_shot_required=False,
                  safety_checks_preserved=True,arm_start_stop_runtime_and_auth_functions_unchanged=True,
                  qualification_evidence_sha256={str(p.relative_to(ROOT)):sha(p) for p in (comparison,zero,pwm)})
    (OUT / 'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    prepare()
