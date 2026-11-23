"""One explicit visual repeat, retaining original OFF64 and immutable captures."""
import argparse,json,sys,hashlib
from pathlib import Path
import run_exact_nis_input_FOC_trial as package
import run_foc_visual_repeat as visual
from run_foc_boot_capture_trial import decode_boot

visual.PAIR=package.p.NEW
visual.motor.PAIR=package.p.NEW


def chain_proof(original,folder):
    folder=Path(folder).resolve()
    for rel,h in json.loads((folder/'saved_files_sha256.json').read_text(encoding='utf8')).items():
        f=(folder/rel).resolve();assert f.parent==folder
        assert hashlib.sha256(f.read_bytes()).hexdigest()==h,rel
    r=json.loads((folder/'report.json').read_text(encoding='utf8'))
    after=json.loads((folder/'final_status.json').read_text(encoding='utf8'))
    assert r['passed'] and r['START']==1 and r['CLEAR']==r['RESET']==r['flash']==0
    assert r['auto_stop_ms']==5000 and r['prior_SD_retained']
    assert r['limits_unchanged'] and r['OFF_fast_cycles']==original['before']['algorithm_fast_cycles']
    assert r['RPC_guard']['ready'] and r['RPC_guard']['failure'] is None
    assert visual.motor.off(after) and after['hmi_hv_armed']==0
    assert after['run_id']==r['run_id'] and after['run_reason']==1 and after['run_elapsed_ms']==5000
    assert after['run_id']>original['after']['run_id']
    assert all(after[k]==0 for k in ('algorithm_fault','mc_fault','bp_fault','mc_fault_current_mask','mc_fault_occurred_mask'))
    boot=decode_boot(after,package.p.NEW,require_fresh=False)
    assert boot['identity']==original['boot']['identity'] and boot['Linux_boot_id']==original['boot']['Linux_boot_id']
    assert boot['native_tick_ms']>=original['boot']['native_tick_ms']
    for k in ('mc_break_wave_hex','mc_adc_peak_hex','mc_observer_trace_hex'):
        assert after[k]==original['after'][k],'Original capture changed: '+k
    assert after['foc_runtime']['first_fault'] is None and after['foc_runtime']['meter_errors']==0
    assert after['foc_runtime']['max_result_age_us']<2000
    return dict(before=original['before'],after=after,boot=original['boot'],previous=folder.as_posix())


def main():
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--original',type=Path,required=True)
    args,rest=parser.parse_known_args()
    package.package_check()
    original=visual.saved_proof(args.original)
    visual.saved_proof=lambda folder:chain_proof(original,folder)
    sys.argv=[sys.argv[0]]+rest
    return visual.main()


if __name__=='__main__':raise SystemExit(main())
