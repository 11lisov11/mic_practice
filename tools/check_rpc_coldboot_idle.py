"""Read-only RPC/encoder stability test, J1 OFF; no CLEAR/ARM/START/reset."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time
import urllib.request
import install_rpc_coldboot_fix as package
import sys
if '--boot-retry' in sys.argv:
    import install_rpc_boot_retry as boot
    package=boot.wrapper
if '--i2c-idle' in sys.argv:
    import install_nucleo_i2c_idle as package

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',default='http://127.0.0.1:18080')
    p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--seconds',type=int,default=40)
    p.add_argument('--powerbank',action='store_true')
    p.add_argument('--boot-retry',action='store_true')
    p.add_argument('--i2c-idle',action='store_true')
    a=p.parse_args();a.outdir.mkdir(parents=True,exist_ok=False)
    report=dict(passed=False,read_only=True,transport=a.url,powerbank_operator_confirmed=a.powerbank,
        motor_commands=0,clear_commands=0,arm_commands=0,flash_commands=0,samples=[],errors=[])
    def get():
        began=time.monotonic();op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open(a.url+'/api/status',timeout=7) as f:r=json.load(f)
        assert r.get('ok') is True and isinstance(r.get('data'),dict),'RPC status unavailable'
        return dict(duration_s=time.monotonic()-began,status=r['data'])
    counters=('rpc_response_timeouts','rpc_send_timeouts','rpc_late_responses','rpc_unknown_methods',
        'mc_bad_cnt','mc_bad_integrity','mc_bad_sequence','enc_errors','enc_peer_bad',
        'uno_rx_dropped','uno_rx_hw_errors','uno_tx_short_writes','enc_diag_controller_resets')
    captures=('mc_break_wave_hex','enc_fault_first_hex','enc_fault_pwm_hex')
    try:
        first=get()['status'];report['before']=first
        okay,why=package.install.precheck(first);assert okay,why
        assert (first['fw_build'],first['mc_fw_build'])==package.p.NEW
        assert first['enc_source']=='nucleo_g431_i2c1'
        start=time.monotonic()
        with ThreadPoolExecutor(max_workers=3) as pool:
            while time.monotonic()-start<a.seconds:
                for row in pool.map(lambda _:get(),range(3)):
                    s=row['status'];report['samples'].append(row)
                    okay,why=package.install.precheck(s);assert okay,why
                    assert (s['fw_build'],s['mc_fw_build'])==package.p.NEW
                    assert all(s[k]==first[k] for k in counters),'New communication or sensor event'
                    assert s['enc_reads']>=first['enc_reads'] and s['enc_age_ms']<100,'Stale sensor'
                    assert s['hmi_vbus_hv_calibrated']==1,'Calibration unavailable'
                time.sleep(.3)
        last=report['samples'][-1]['status'];report['after']=last
        report['read_delta']=last['enc_reads']-first['enc_reads']
        report['counter_deltas']={k:last[k]-first[k] for k in counters}
        report['capture_changes']={k:last.get(k)!=first.get(k) for k in captures}
        report['max_http_s']=max(r['duration_s'] for r in report['samples'])
        assert report['read_delta']>0
        report['passed']=True
    except Exception as exc:report['errors'].append(str(exc))
    (a.outdir/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ('passed','errors','read_delta','counter_deltas','capture_changes','max_http_s')}))
    return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
