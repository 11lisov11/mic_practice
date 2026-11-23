"""Prepare HMI-only short-trial support and audit exact motor/measurement source deltas."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from prepare_unoq_rx_fix import ROOT, BASE, ASSETS, sketch, hmi as rx_hmi
from prepare_ipm_break_wifi import REFERENCE, UNO, nucleo_main, patched_irq, uno_sketch, source_hashes
from prepare_mcsdk_logic_bench import replace_once
from run_mcsdk_logic_bench import compare_code_sections

RX = ROOT/'artifacts/live_bench_20261011/uart_rx_fix/candidate_r1'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def server(text):
    text=replace_once(text, 'def validate_powered_trial_qualification(proof: object)',
        (ASSETS/'short_trial_gate.py').read_text()+'\n\ndef validate_powered_trial_qualification(proof: object)')
    text=replace_once(text, '\n    coast30 = proof.get("schema") == "mic_ai.powered_trial.coast30.v1"',
        '\n'
        '    if proof.get("schema") == RX_SNAPSHOT_SCHEMA:\n'
        '        return validate_rx_snapshot_trial(proof)\n'
        '    coast30 = proof.get("schema") == "mic_ai.powered_trial.coast30.v1"')
    text=text.replace('(UART_V3_TRIAL_PAIR, UART_V3_SENDER_TRIAL_PAIR)',
                      '(UART_V3_TRIAL_PAIR, UART_V3_SENDER_TRIAL_PAIR, RX_SNAPSHOT_TRIAL_PAIR)')
    text=replace_once(text, '        self.max_freq_hz = 50 if profile==COAST30_PROFILE else 10',
        '        self.max_freq_hz = 5 if pair==RX_SNAPSHOT_TRIAL_PAIR else (50 if profile==COAST30_PROFILE else 10)')
    text=replace_once(text, '0 < freq <= 10) or stopped_zero',
        '0 < freq <= (5 if pair==RX_SNAPSHOT_TRIAL_PAIR else 10)) or stopped_zero')
    text=replace_once(text, '        (2026101008, 2026101006),',
        '        (2026101008, 2026101006),\n        RX_SNAPSHOT_TRIAL_PAIR,')
    text=replace_once(text, '          (2026101008, 2026101006)):',
        '          (2026101008, 2026101006), RX_SNAPSHOT_TRIAL_PAIR):')
    a=text.index('    def live_check('); b=text.index('    def observe(',a)
    live=replace_once(text[a:b], '        for key in ("mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence",',
        '        if pair == RX_SNAPSHOT_TRIAL_PAIR:\n'
        '            for key in ("uno_rx_dropped", "uno_rx_hw_errors", "uno_rx_hw_flags", "mc_break_rx_bad"):\n'
        '                if type(data.get(key)) is not int or data[key] != 0:\n'
        '                    return False, "RX snapshot trial transport unhealthy: " + key\n'
        '        for key in ("mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence",')
    return text[:a]+live+text[b:]


def audit(out):
    # Reject all differences except the exact previously reviewed instrumentation recipe.
    old=source_hashes(REFERENCE); new=source_hashes(BASE/'nucleo')
    changed=sorted(k for k in set(old)|set(new) if old.get(k)!=new.get(k))
    expected=['Inc/break_wire.h','Inc/first_break_snapshot.h','Src/main.c','Src/stm32g4xx_mc_it.c']
    if changed!=expected: raise RuntimeError('Unexpected motor-component changes: '+str(changed))
    for relative,transform in (('Src/main.c',nucleo_main),('Src/stm32g4xx_mc_it.c',patched_irq)):
        if (BASE/'nucleo'/relative).read_text()!=transform((REFERENCE/relative).read_text(encoding='utf-8-sig')):
            raise RuntimeError('Unexpected instrumented source: '+relative)
    for name in ('break_wire.h','first_break_snapshot.h'):
        if sha(BASE/'nucleo/Inc'/name)!=sha(ROOT/'research/ipm_break'/name):
            raise RuntimeError('Unexpected diagnostic header: '+name)
    if sha(RX/'UNOQ_MOTOR/uart_v3_transport.h')!=sha(UNO/'uart_v3_transport.h'):
        raise RuntimeError('Control frame/CRC contract changed')
    if (RX/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text()!=sketch(uno_sketch((UNO/'UNOQ_MOTOR.ino').read_text())):
        raise RuntimeError('Unexpected Uno control-path changes')
    if (RX/'web_hmi/server.py').read_text()!=rx_hmi((BASE/'web_hmi/server.py').read_text()):
        raise RuntimeError('Unexpected installed HMI baseline')
    sections=compare_code_sections(REFERENCE/'STM32CubeIDE/Debug',BASE/'nucleo/STM32CubeIDE/Debug',out/'code_sections')
    core={k:v for k,v in sections['functions'].items() if k!='TIM1_BRK_TIM15_IRQHandler'}
    if not core or not all(v['equal'] for v in core.values()) or not sections['timer_initializer_source_identical']:
        raise RuntimeError('Motor PWM/timer machine code changed')
    result=dict(pass_=True,pwm_core_equivalence_pass=True,break_irq_delta_audited=True,
        new_break_irq_machine_code_identical=False,new_pair_active_pwm_measured=False,
        calibration_contract_pass=True,changed_nucleo_files=changed,pwm_functions=core,
        timer_initializer_source_identical=True,
        note='Only source-audited recorder added to break ISR; immediate BKE hardware shutdown unchanged. Not a new active-PWM measurement.',
        source_nucleo_sha256=new,source_uno_sha256=source_hashes(RX/'UNOQ_MOTOR'),
        source_vbus_contract='Unchanged MCSDK BusVoltageSensor config and VBS_GetAvBusVoltage_V; same reply slots, 0.1 V/LSB',
        images=dict(production_uno=sha(RX/'uno_build/UNOQ_MOTOR.ino.elf-zsk.bin'),
            production_nucleo=sha(BASE/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin')))
    result['pass']=result.pop('pass_')
    (out/'delta_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    result=audit(out)
    shutil.copytree(RX/'web_hmi',out/'web_hmi',ignore=shutil.ignore_patterns('__pycache__','.venv'))
    p=out/'web_hmi/server.py'; p.write_text(server(p.read_text()),encoding='utf-8')
    manifest=dict(hmi_sha256=sha(p),previous_hmi_sha256=sha(RX/'web_hmi/server.py'),
        images=result['images'],pair=[2026101104,2026101102],max_run_s=3,max_frequency_hz=5,
        calibration_file_modified=False,mcu_firmware_changed=False,hardware_commands=0)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args(); print(json.dumps(prepare(a.outdir.resolve())))
