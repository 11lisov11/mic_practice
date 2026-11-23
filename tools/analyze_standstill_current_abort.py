"""Offline replay of the preserved ID overcurrent abort; never accesses a board."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from collect_current_peak import decoder
from standstill_measurement import crc32c


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--point', type=Path, required=True)
    parser.add_argument('--outdir', type=Path)
    args = parser.parse_args()
    candidate, point = args.candidate.resolve(), args.point.resolve()
    out = args.outdir.resolve() if args.outdir else point/'current_abort_analysis'
    out.mkdir(exist_ok=False)
    status = json.loads((point/'report.json').read_text(encoding='utf-8'))['after']
    build = status['mc_fw_build']
    raw = (point/'adc_abort/trace.bin').read_bytes()
    trace = decoder(candidate).decode_adc_peak_hex(raw.hex(), expected_build=build)
    result_raw = (point/'raw_abort/capture.bin').read_bytes()
    result_meta = json.loads((point/'raw_abort/report.json').read_text(encoding='utf-8'))
    assert crc32c(result_raw) == result_meta['crc'] == status['id_result_crc']
    assert struct.unpack_from('<I', result_raw, 20)[0] == 2
    start = struct.unpack_from('<I', result_raw, 92)[0]
    scale = 3.3/(4095*.04*2.1)
    rows = []
    for x in trace['samples']:
        u, v, w = [n*scale for n in x['counts_uvw']]
        beta = (u+2*v)/(3**.5)
        arr, bus = x['timer_arr'], x['bus_v']
        cu, cv, cw, _ = x['ccr_at_update']
        rows.append(dict(index=x['index'], cycles=x['cycles'], epoch=x['epoch_before'],
            accepted=x['accepted_by_monitor'], current_u_a=u, current_v_a=v,
            current_w_a=w, current_beta_a=beta, vector_a=(u*u+beta*beta)**.5,
            ideal_alpha_v=(2*cu-cv-cw)*bus/(3*arr),
            raw_adc=x['raw_adc'], ccr=x['ccr_at_update'],
            elapsed_s=((x['cycles']-start)&0xffffffff)/trace['cpu_hz']))
    # Replay the EXACT installed pure C kernel. The guard runs before PI/control
    # and is independent of unavailable prehistory of the integrator. Rejected
    # post-STOP samples are never relabelled as accepted motor measurements.
    source = '''#include <cstdio>\n#include <identify_core.h>\nint main(){
mi_state state{};mi_config config{};config.run_id=4184657600U;config.kind=MI_DC;
config.amplitude=.06f;config.rs=12.23f;config.duration_ms=3000;
ma_geometry geometry{5312,5184,771,112,240,228};
if(!mi_begin(&state,&config,START))return 1;
mi_sample sample{};sample.bus=320;sample.arr=5312;sample.valid=1;
ma_output output{};int fault=0;unsigned calls=0;
'''.replace('START', str(start)+'U')
    for row, x in zip(rows, trace['samples']):
        if not row['accepted']:
            continue
        source += ('sample.cycles=%dU;sample.epoch=%dU;sample.ia=%.10ff;sample.ib=%.10ff;'
                   'sample.ccr[0]=%d;sample.ccr[1]=%d;sample.ccr[2]=%d;'
                   'if(!fault){++calls;fault=mi_step(&state,&geometry,&sample,sample.cycles+100U,170000000U,&output);}\n'
                   % (row['cycles'], row['epoch'], row['current_u_a'], row['current_beta_a'],
                      *x['ccr_at_update'][:3]))
    source += '''if(fault!=MI_BAD_CURRENT||state.active||!state.done||calls!=11)return 2;
printf("{\\"fault\\":%u,\\"calls\\":%u,\\"done\\":%u,\\"active\\":%u}\\n",fault,calls,state.done,state.active);
}\n'''
    unit = out/'replay.cpp'
    unit.write_text(source, encoding='utf-8')
    with tempfile.TemporaryDirectory() as temp:
        exe = Path(temp)/'replay.exe'
        build_result = subprocess.run([shutil.which('g++'), '-std=c++17', '-O2',
            '-I', str(candidate/'nucleo/Inc'), str(unit), '-o', str(exe)],
            capture_output=True, text=True, timeout=60)
        (out/'build.log').write_text(build_result.stdout+build_result.stderr, encoding='utf-8')
        build_result.check_returncode()
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
        (out/'run.log').write_text(run.stdout+run.stderr, encoding='utf-8')
        run.check_returncode()
        replay = json.loads(run.stdout)
    trips = [r for r in rows if r['accepted'] and r['vector_a'] > .45]
    assert len(trips) == 1
    trip = trips[0]
    assert trip['index'] == 10 and all(x['epoch_consistent'] for x in trace['samples'])
    assert not any(x['three_leg_window_rejected'] or x['publish_deadline_missed']
                   or x['pending_epoch_mismatch'] or x['queue_overflow_observed']
                   for x in trace['samples'])
    with (out/'samples.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    # Mean uncertainty was measured during OFF calibration. Its published value
    # is the MAXIMUM across paths and two estimators. Multiplying it by sqrt(N)
    # is only a noise indication, not a measured per-phase standard deviation.
    history = status['mc_zero_history']
    report = dict(passed=True, hardware_commands=0, start_commands=0, clear_commands=0,
        physical_parameter_measurement_valid=False, physical_current_scale_qualified=False,
        inductance_identified=False, result_crc=result_meta['crc'],
        raw_trace_sha256=hashlib.sha256(raw).hexdigest(),
        raw_result_sha256=hashlib.sha256(result_raw).hexdigest(),
        pair=[status['fw_build'],build], c_kernel_replay=replay,
        accepted_raw_frames=sum(r['accepted'] for r in rows),
        trip_frame=trip, next_post_stop_frame=rows[11],
        native_cpu_qualification_cycles=status['id_timing_cycles'],
        physical_fast_adapter_max_cycles=status['algorithm_fast_cycles'],
        original_fast_deadline_cycles=5312, additional_raw_current_limit_a=.45,
        adc_counts_per_target_alpha=.06/scale,
        adc_counts_per_target_v_w=.03/scale,
        nominal_a_per_adc_count=scale,
        off_zero_history=history,
        all_recorded_epochs_consistent=True, recorded_window_or_deadline_failures=0,
        inference='An isolated raw excursion stopped the point. This capture does not establish whether it was physical current or analog measurement interference. Correct window geometry is necessary but does not certify analog accuracy.',
        measurement_plan_limitation='The 0.06 A target is only 6.25 ADC counts in alpha and 3.13 counts in the two measured phases; recorded OFF noise spans are larger. Synthetic noiseless plant validation did not qualify that hardware signal-to-noise ratio.',
        protection_thresholds_changed=False)
    (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('passed','c_kernel_replay','trip_frame','adc_counts_per_target_alpha','hardware_commands')}))


if __name__ == '__main__':
    main()
