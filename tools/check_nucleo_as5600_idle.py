"""Read-only idle stress; no commands, ARM, CLEAR, reset or flashing."""
import argparse
import json
from pathlib import Path
import threading
import time
import urllib.request
import traceback
from current_zero_quality import ready

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://192.168.1.138:8080')
    parser.add_argument('--seconds',type=int,default=30)
    parser.add_argument('--uno-build',type=int,choices=(2026102601,2026102603),default=2026102603)
    parser.add_argument('--outdir',type=Path,required=True)
    a=parser.parse_args();a.outdir.mkdir(parents=True,exist_ok=True)
    r=dict(passed=False,motor_commands=0,clear_commands=0,firmware_writes=0,samples=[],background_errors=[],
           transport=a.url,powered_run_proof=False,expected_pair=[a.uno_build,2026102602])
    stop=threading.Event();workers=[]
    def status(opener):
        with opener.open(a.url+'/api/status',timeout=8) as response:p=json.load(response)
        assert p.get('ok') is True and isinstance(p.get('data'),dict)
        return p['data']
    def client():
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while not stop.is_set():
            try:status(opener)
            except Exception as e:r['background_errors'].append(str(e))
            stop.wait(.1)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        first=status(opener);r['before']=first
        for _ in range(2):
            t=threading.Thread(target=client,daemon=True);workers.append(t);t.start()
        end=time.monotonic()+a.seconds
        while time.monotonic()<end:
            began=time.monotonic();s=status(opener)
            r['samples'].append(dict(duration_s=time.monotonic()-began,status=s))
            assert (s['fw_build'],s['mc_fw_build'])==(a.uno_build,2026102602)
            assert s['state']=='SAFE' and s['pwm']==0 and s['hmi_hv_armed']==0
            assert 0<=s['vdc']<20 and s['enc_source']=='nucleo_g431_i2c1' and s['enc_diag_mode']==6
            assert s['enc_reads']>=first['enc_reads'] and s['enc_errors']==first['enc_errors']==0
            assert s['enc_peer_bad']==first['enc_peer_bad']
            assert s['enc_bus_ok']==s['enc_ok']==s['enc_speed_ok']==1 and s['enc_age_ms']<100
            assert s['enc_io_error']==s['enc_init_error']==0 and s['enc_diag_cfg_match']==1
            assert (s['enc_status']&0x38)==0x20 and ready(s)
            assert s['mc_transport_fault']==s['bp_transport_fault']==0
            assert all(s[k]==0 for k in ['mc_bad_cnt','mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags','uno_rx_dropped','uno_tx_short_writes'])
            assert s['hmi_vbus_hv_calibrated']==1
            time.sleep(.15)
        r['after']=r['samples'][-1]['status'];r['passed']=not r['background_errors']
        r['read_delta']=r['after']['enc_reads']-first['enc_reads']
        r['error_delta']=r['after']['enc_errors']-first['enc_errors']
        r['peer_bad_delta']=r['after']['enc_peer_bad']-first['enc_peer_bad']
        r['rescued_delta']=r['after'].get('uno_rx_rescued',0)-first.get('uno_rx_rescued',0)
        r['max_status_duration_s']=max(x['duration_s'] for x in r['samples'])
    except Exception as e:
        r['error']=str(e) or type(e).__name__
        r['traceback']=traceback.format_exc()
    finally:
        stop.set()
        for t in workers:t.join(9)
        (a.outdir/'report.json').write_text(json.dumps(r,indent=2)+'\n')
        print(json.dumps({k:r.get(k) for k in ['passed','error','read_delta','error_delta','peer_bad_delta','rescued_delta','max_status_duration_s','background_errors']}),flush=True)
    return 0 if r['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
