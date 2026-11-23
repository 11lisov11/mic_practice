"""Prepare bounded SAFE servicing and remove unqualified blocking ADC work from MCSDK owner."""
import argparse
import json
from pathlib import Path
import shutil

from prepare_unoq_rx_fix import ROOT
from prepare_ipm_break_wifi import patch_function, source_hashes
from prepare_mcsdk_logic_bench import replace_once

BASE=ROOT/'artifacts/live_bench_20261011/uart_rx_fix/candidate_r1'
BUILD=2026101105
HMI_BASE=ROOT/'artifacts/live_bench_20261011/rx_trial_preparation/hmi_candidate_r3'


def hmi(text):
    text=replace_once(text,'          (2026101008, 2026101006), RX_SNAPSHOT_TRIAL_PAIR):',
        '          (2026101008, 2026101006), RX_SNAPSHOT_TRIAL_PAIR, (2026101105, 2026101102)):')
    text=replace_once(text,'data["mc_current_telemetry_source"] = "uno_q_local_adc_unqualified"',
        'data["mc_current_telemetry_source"] = ("not_acquired_mcsdk_backend"\n'
        '            if data.get("uno_local_adc_acquired") == 0 else "uno_q_local_adc_unqualified")')
    return replace_once(text,'                "uno_rx_rejected_hex":',
        '                **{k: int(kv[k]) for k in ("uno_local_adc_acquired", "uno_tx_all_max_gap_us",\n'
        '                    "uno_tx_last_gap_us", "uno_tx_gaps_over_watchdog") if k in kv},\n'
        '                "uno_rx_rejected_hex":')


def attach_hmi(out):
    shutil.copytree(HMI_BASE/'web_hmi',out/'web_hmi',ignore=shutil.ignore_patterns('__pycache__','.venv'))
    p=out/'web_hmi/server.py'; p.write_text(hmi(p.read_text()),encoding='utf-8')
    from hashlib import sha256
    manifest=json.loads((out/'manifest.json').read_text())
    manifest.update(hmi_sha256=sha256(p.read_bytes()).hexdigest(),
        expected_live_hmi_sha256=sha256((HMI_BASE/'web_hmi/server.py').read_bytes()).hexdigest(),
        new_pair_powered_gate_qualified=False)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


def sketch(text):
    text=replace_once(text,'FW_BUILD_ID = 2026101104U',f'FW_BUILD_ID = {BUILD}U')
    def control(code):
        a=code.index('  // ADC offsets calibration in SAFE')
        b=code.index('  if (unoq_local_current_trip(',a)
        old=code[a:b]
        return code[:a]+('  if (!NUCLEO_MCSDK_ACIM_BACKEND) {\n'+old+
            '  } else {\n'
            '    // No local current acquisition: MCSDK owns current control/protection.\n'
            '    g_last_ia = g_last_ib = g_last_ic = g_last_i_rms = 0.0f;\n'
            '  }\n'
            '  const float ia = g_last_ia, ib = g_last_ib, ic = g_last_ic;\n')+code[b:]
    text=patch_function(text,'control_step',control)
    text=replace_once(text,'static float read_vdc() {',
        'static float read_vdc() {\n'
        '  // Never block the UART owner on an unrelated local ADC. Age gates still apply.\n'
        '  if (NUCLEO_MCSDK_ACIM_BACKEND) return g_bp_vdc;')
    text=replace_once(text,'  handle_button();',
        '  // Service SAFE before optional display/control work, not only after it.\n'
        '  if (NUCLEO_MCSDK_ACIM_BACKEND && USE_EXTERNAL_PWM && !USE_NUCLEO_SPI && !g_pwm_enabled) {\n'
        '    nucleo_uart_poll();\n'
        '    nucleo_send_stop(false);\n'
        '  }\n'
        '  handle_button();')
    text=replace_once(text,'(uint32_t)(now - g_nucleo_keepalive_ms) >= 100)',
        '(uint32_t)(now - g_nucleo_keepalive_ms) >=\n'
        '          (NUCLEO_MCSDK_ACIM_BACKEND ? NUCLEO_HEARTBEAT_MS : 100U))')
    text=replace_once(text,'  s += " uno_tx_count=";',
        '  s += " uno_local_adc_acquired="; s += String(NUCLEO_MCSDK_ACIM_BACKEND ? 0 : 1);\n'
        '  s += " uno_tx_all_max_gap_us="; s += String((unsigned long)timing.tx_all_max_gap_us);\n'
        '  s += " uno_tx_last_gap_us="; s += String((unsigned long)timing.tx_last_gap_us);\n'
        '  s += " uno_tx_gaps_over_watchdog="; s += String((unsigned long)timing.tx_gaps_over_watchdog);\n'
        '  s += " uno_tx_count=";')
    return text


def timing(text):
    text=replace_once(text,'  uint32_t tx_count = 0;',
        '  uint32_t tx_all_max_gap_us = 0;\n'
        '  uint32_t tx_last_gap_us = 0;\n'
        '  uint32_t tx_gaps_over_watchdog = 0;\n'
        '  uint32_t tx_count = 0;')
    return replace_once(text,'    if (tx_seen && (active || tx_active)) maximum(tx_active_max_gap_us, now - last_tx);',
        '    if (tx_seen) {\n'
        '      tx_last_gap_us = now - last_tx;\n'
        '      maximum(tx_all_max_gap_us, tx_last_gap_us);\n'
        '      if (tx_last_gap_us > UV3_WATCHDOG_MS * 1000U) increment(tx_gaps_over_watchdog);\n'
        '    }\n'
        '    if (tx_seen && (active || tx_active)) maximum(tx_active_max_gap_us, now - last_tx);')


def prepare(out):
    before=source_hashes(BASE/'UNOQ_MOTOR')
    out.mkdir(parents=True,exist_ok=False)
    shutil.copytree(BASE/'UNOQ_MOTOR',out/'UNOQ_MOTOR')
    for name,transform in (('UNOQ_MOTOR.ino',sketch),('link_timing.h',timing)):
        p=out/'UNOQ_MOTOR'/name; p.write_text(transform(p.read_text()),encoding='utf-8')
    if source_hashes(BASE/'UNOQ_MOTOR')!=before: raise RuntimeError('Baseline changed')
    result=dict(uno_build=BUILD,nucleo_build=2026101102,source_sha256=source_hashes(out/'UNOQ_MOTOR'),
        baseline_source_sha256=before,installed=False,hv_release_approved=False,
        watchdog_ms=300,crc_checks_changed=False,pwm_backend_changed=False,
        local_current_adc_acquired=False,
        note='Scheduling/measurement-path repair candidate; live timeout cause not yet exclusively proven')
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args(); print(json.dumps(prepare(a.outdir.resolve())))
