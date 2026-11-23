"""Audit unchanged measurement/PWM components and prepare a bounded HMI-only trial."""
import argparse
import hashlib
import json
from pathlib import Path

from prepare_unoq_rx_fix import ROOT
from prepare_mcsdk_logic_bench import replace_once
from prepare_rx_short_trial import audit as baseline_audit
from prepare_ipm_break_wifi import source_hashes

HMI = ROOT / 'artifacts/live_bench_20261012/fault_context_fix/candidate_r2/web_hmi/server.py'
UNO = ROOT / 'artifacts/live_bench_20261012/llext_fix/candidate_r1'
ASSET = ROOT / 'research/uart_rx/boot_trial_gate.py'
NUCLEO = ROOT / 'artifacts/live_bench_20261011/ipm_break_wifi/candidate_r6/nucleo'
IMAGES = {
    'production_uno': '2d981c66e978be9cf2bc2b36a98f493b8350758ce0a36814867dfc510f8bffc8',
    'production_nucleo': 'd17b1ed8313b7e355e66681f90beaf84e7535e22504212f79ef44ce2bad5d37c',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def images():
    manifest = json.loads((UNO / 'uno_build/unoq_mcsdk_scalar.build-manifest.json').read_text(encoding='utf-8-sig'))
    if manifest['firmware_build_id'] != 2026101108:
        raise RuntimeError('Unexpected Uno identity')
    result = dict(IMAGES)
    recorded = next(x['sha256'].lower() for x in manifest['artifacts'] if x['file']==manifest['flash_artifact'])
    if recorded != result['production_uno']:
        raise RuntimeError('Unexpected Uno image hash')
    if sha(UNO / 'uno_build' / manifest['flash_artifact']) != result['production_uno']:
        raise RuntimeError('Uno image changed')
    return result


def server(text):
    embedded = ASSET.read_text().replace('__BOOT_TRIAL_IMAGES__', repr(images()))
    text = replace_once(text, '# Embedded in the prepared HMI; explicit component transfer, not a new PWM capture.',
                        embedded + '\n\n# Embedded in the prepared HMI; explicit component transfer, not a new PWM capture.')
    text = replace_once(text, '    if proof.get("schema") == RX_SNAPSHOT_SCHEMA:',
                        '    if proof.get("schema") == BOOT_TRIAL_SCHEMA:\n'
                        '        return validate_boot_trial(proof)\n'
                        '    if proof.get("schema") == RX_SNAPSHOT_SCHEMA:')
    text = text.replace('(UART_V3_TRIAL_PAIR, UART_V3_SENDER_TRIAL_PAIR, RX_SNAPSHOT_TRIAL_PAIR)',
                        '(UART_V3_TRIAL_PAIR, UART_V3_SENDER_TRIAL_PAIR, RX_SNAPSHOT_TRIAL_PAIR, BOOT_TRIAL_PAIR)')
    text = text.replace('pair==RX_SNAPSHOT_TRIAL_PAIR', 'pair in (RX_SNAPSHOT_TRIAL_PAIR, BOOT_TRIAL_PAIR)')
    text = replace_once(text, '        if pair == RX_SNAPSHOT_TRIAL_PAIR:',
                        '        if pair in (RX_SNAPSHOT_TRIAL_PAIR, BOOT_TRIAL_PAIR):')
    text = replace_once(text, '        RX_SNAPSHOT_TRIAL_PAIR,\n    }',
                        '        RX_SNAPSHOT_TRIAL_PAIR,\n        BOOT_TRIAL_PAIR,\n    }')
    # Only non-actuating preparation accepts the already observed auxiliary bias.
    # ARM/RUN still require the existing 250..360-V fault-free powered window.
    a=text.index('    def prepare_powered_trial(')
    b=text.index('    def cancel_powered_trial(',a)
    prepare=text[a:b]
    prepare = replace_once(prepare, '        for key in ("vdc", "bp_vdc"):\n            value = data.get(key)',
                        '        prepare_max_vdc = 10 if tuple(proof["pair"]) == BOOT_TRIAL_PAIR else 2\n'
                        '        for key in ("vdc", "bp_vdc"):\n            value = data.get(key)')
    prepare = replace_once(prepare, 'not 0 <= value <= 2:\n                return False, "prepare only on a discharged bus"',
                        'not 0 <= value <= prepare_max_vdc:\n                return False, "prepare only on a low-energy bus"')
    prepare = replace_once(prepare, 'not 0 <= _as_int(data, "bp_vbus_raw", 999999) <= 20 or not _status_link_live(data)',
                        'not 0 <= _as_int(data, "bp_vbus_raw", 999999) <= prepare_max_vdc*10 or not _status_link_live(data)')
    return text[:a]+prepare+text[b:]


def prepare(out):
    out.mkdir(parents=True, exist_ok=False)
    old = baseline_audit(out)
    if old['images']['production_nucleo'] != images()['production_nucleo']:
        raise RuntimeError('Nucleo component changed')
    old_manifest = json.loads((UNO / 'manifest.json').read_text())
    if source_hashes(UNO / 'UNOQ_MOTOR') != old_manifest['source_sha256']:
        raise RuntimeError('Uno source changed since build')
    # Measurement decoding and gain/units are preserved, despite different RX plumbing.
    baseline = ROOT / 'artifacts/live_bench_20261011/uart_rx_fix/candidate_r1/UNOQ_MOTOR/UNOQ_MOTOR.ino'
    before, after = baseline.read_text(), (UNO / 'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text()
    begin = before.index('  g_bp_vbus_raw =')
    end = before.index('  g_bp_temp_raw =', begin)
    fragment = before[begin:end]
    if fragment not in after:
        raise RuntimeError('Vbus decoding changed')
    target = out / 'web_hmi/server.py'
    target.parent.mkdir()
    target.write_text(server(HMI.read_text()), encoding='utf-8')
    result = dict(pass_=True, pair=[2026101108,2026101102], images=images(),
                  nucleo_pwm_equivalence_pass=old['pwm_core_equivalence_pass'],
                  calibration_contract_pass=old['calibration_contract_pass'],
                  vbus_decoding_fragment_sha256=hashlib.sha256(fragment.encode()).hexdigest(),
                  previous_hmi_sha256=sha(HMI), hmi_sha256=sha(target),
                  source_nucleo_sha256=source_hashes(NUCLEO), source_uno_sha256=source_hashes(UNO/'UNOQ_MOTOR'),
                  max_run_s=3, max_frequency_hz=5, mcu_firmware_changed=False,
                  calibration_file_modified=False, hv_release_approved=False)
    result['pass'] = result.pop('pass_')
    (out / 'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args()
    result=prepare(a.outdir.resolve())
    print(json.dumps({k:result[k] for k in ('pass','pair','images','hmi_sha256','max_run_s','max_frequency_hz')}))
