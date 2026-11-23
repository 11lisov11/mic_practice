"""Record installed bytes separately from pending long/RUN qualification."""
import json
import prepare_rpc_short_lock as p

def main():
    r=json.loads(p.read(p.OUT/'install_r1/report.json'));assert r['passed'] and r['uno_readback_verified'] and r['calibration_unchanged']
    assert r['nucleo_flash_commands']==r['START']==r['CLEAR']==0
    expected=p.ROOT/'artifacts/live_bench_20261116/clear_recovery_r1/release/nucleo_2026111606_expected_readback.bin'
    assert (p.OUT/'install_r1/native_flash_2026111606_before.bin').read_bytes()==expected.read_bytes()
    m=json.loads(p.read(p.OUT/'manifest.json'));m.update(installed=True,
        installation_scope='Uno1609 only; native1606 not flashed/reset; no START/CLEAR',
        uno_readback_verified=True,calibration_unchanged=True,current_RPC_usable=True,
        long_idle_qualification_pending=True,FOC_start_ready=False,FOC_five_seconds_verified=False,
        host_guard_progress_source='uno_rx_count,32-bit accepted native RSPs; native16-bit good count remains checked for decrease',
        host_guard_sha256=p.sha(p.ROOT/'tools/rpc_counter_guard.py'),
        host_guard_tests='rpc_counter_guard_live_count_r1/report.json')
    p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(json.dumps(dict(installed=True,pair=p.NEW,Uno_verified=True,Nucleo_flash=0,START=0,CLEAR=0,long_idle_pending=True)))
if __name__=='__main__':main()
