"""Finalize evidence without overstating the initiating stream-failure cause."""
import json
import prepare_rpc_short_lock as p

def main():
    long=json.loads(p.read(p.OUT/'long_idle_r4/report.json'))
    install=json.loads(p.read(p.OUT/'install_r1/report.json'))
    tests=json.loads(p.read(p.OUT/'verification/report.json'))
    guard=json.loads(p.read(p.ROOT/'artifacts/live_bench_20261116/rpc_counter_guard_live_count_r1/report.json'))
    assert install['passed'] and install['uno_readback_verified'] and tests['passed'] and guard['passed']
    history=json.loads(p.read(p.OUT/'preserved_all_hashes.json'))
    for rel,h in history.items():assert p.sha(p.ROOT/rel)==h,rel
    for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert p.sha(p.OUT/rel)==h,rel
    result=dict(pair=list(p.NEW),installed=True,Uno_readback_verified=True,Nucleo_flash=0,Nucleo_reset=0,
        START=0,CLEAR=0,calibration_unchanged=install['calibration_unchanged'],
        captured_updater_lock_starvation_corrected=True,host_header_cases=18,host_guard_cases=13,
        long_RPC_idle_passed=long['passed'],long_RPC_elapsed_s=long['elapsed_s'],samples=long['samples'],
        original_stream_failure_first_byte_identified=False,
        FOC_five_seconds_verified=False,FOC_start_ready=False,
        protection_limits=dict(OFF_fast_cycles=4000,estimate_ms=2,trip_A=1.35,ADC_ticks=2048),
        thresholds_changed=False,protected_native_image_unchanged=True,
        preserved_files=len(history),long_report='long_idle_r4/report.json')
    p.write(p.OUT/'acceptance.json',json.dumps(result,indent=2)+'\n')
    manifest=json.loads(p.read(p.OUT/'manifest.json'))
    manifest.update(long_idle_qualification_pending=False,current_RPC_usable=long['passed'],
        long_idle_RPC_verified=long['passed'],FOC_start_ready=False,
        acceptance_sha256=p.sha(p.OUT/'acceptance.json'),qualification='Captured updater lock starvation corrected. Long idle result in acceptance; initiating stream failure and FOC RUN not fully qualified.')
    p.write(p.OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__':main()
