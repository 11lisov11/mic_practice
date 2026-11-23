"""Offline C-kernel/independent-plant sensitivity test with saved OFF ADC noise.

Does not contact boards, qualify hardware, stage profiles or change firmware.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from compare_idle_adc_noise import load

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'artifacts/live_bench_20261029/adc_noise_rpc_fix_r1'
SOURCES = ['idle_noise_hardware_r1', 'idle_noise_15v_off_r1']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    captures = [load(PACKAGE / name) for name in SOURCES]
    header = ['#pragma once', 'struct NoiseRecord {double a,b;};',
              'static const NoiseRecord noise_data[2][2][128]={']
    for capture in captures:
        header.append('{')
        for case in capture['decoded']['cases'][1:3]:
            rows = case['raw']
            a_mean = sum(row['a'] for row in rows) / len(rows)
            b_mean = sum(row['b'] for row in rows) / len(rows)
            header.append('{')
            header.extend(f"{{{row['a']-a_mean:.10f},{row['b']-b_mean:.10f}}}," for row in rows)
            header.append('},')
        header.append('},')
    header.append('};')
    (out / 'recorded_noise_data.h').write_text('\n'.join(header) + '\n', encoding='utf-8')
    source = ROOT / 'tools/multi_algorithm/recorded_noise_test.cpp'
    exe = out / 'model.exe'
    command = [shutil.which('g++'), '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
               '-Wno-misleading-indentation', '-I', str(PACKAGE / 'nucleo/Inc'),
               '-I', str(out), str(source), '-o', str(exe)]
    build = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (out / 'build.log').write_text(build.stdout + build.stderr, encoding='utf-8')
    build.check_returncode()
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
    (out / 'run.jsonl').write_text(result.stdout, encoding='utf-8')
    (out / 'run.log').write_text(result.stderr, encoding='utf-8')
    if result.returncode not in (0, 1):
        result.check_returncode()
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert len(rows) == 70
    inputs = {str(p.relative_to(ROOT)): sha(p) for p in [
        source, ROOT / 'tools/multi_algorithm/model_test.cpp',
        PACKAGE / 'nucleo/Inc/motor_control.h', PACKAGE / 'nucleo/Inc/current_core.h',
        PACKAGE / 'nucleo/Inc/current_adc_window_plan.h']}
    report = dict(
        study_completed=True, all_scenarios_passed=result.returncode == 0,
        source_kind='independent synthetic plant with recorded OFF ADC error injection',
        hardware_commands=0, start_commands=0, clear_commands=0,
        firmware_changed=False, protection_thresholds_changed=False,
        hardware_foc_qualified=False, inductance_identified=False,
        nominal_amp_per_adc_count=3.3 / (4095 * .04 * 2.1),
        simulation_motor_parameters=dict(rs=12.23, rr=10, ls=.9, lr=.9, lm=.84,
            j=.0003, b=.00015, pole_pairs=1, flux=.35, current_limit=1.1, trip_current=1.35,
            current_bw=400, speed_bw=12),
        plant='Independent double-precision flux-state RK4; estimator receives currents/applied voltage only.',
        controller='Actual unchanged motor_control.h from installed Nucleo2940; current reconstruction also actual C.',
        scenarios=rows, source_hashes=inputs,
        trajectories={'0': 'Legacy abrupt plateaus 0,5,20,35,50,25,5 Hz,14s',
                      '1': '5Hz constant target from rest,5s',
                      '2': '0to50Hz at5Hz/s, then hold;14s'},
        captures=[dict(label=name, sha256=c['sha256'], crc32c=c['crc32c'])
                  for name, c in zip(SOURCES, captures)],
        assumptions=[
            'Rr, Ls, Lr, Lm, J and B are simulation priors, not identified AIR values.',
            'Noise is nominal amperes from unqualified .04ohm/2.1 conversion.',
            'Each recorded converter pair is centered about its own case mean: ideal zero, not physical offset qualification.',
            'Fixed U1/V2 and V1/W2 errors are transferred to simulated selected phases; U1/W2 lacks a simultaneous capture and uses U1/V2 error pairs.',
            '128-sample blocks repeated or resampled whole rows; not exact physical temporal/phase replay or full spectrum.',
            'OFF capture uses different trigger than active PWM; switching noise is not represented.',
            'A recorded0.604A vector is injected additively once; its physical original cause remains unknown.',
            'Float C on host does not qualify STM32 WCET, main-loop scheduling, electrical scale or hardware startup.',
        ])
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(completed=True, scenarios=len(rows),
        passed=sum(row['passed'] for row in rows),
        failed=sum(not row['passed'] for row in rows), hardware_commands=0,
        report=str(out / 'report.json'))))


if __name__ == '__main__':
    main()
