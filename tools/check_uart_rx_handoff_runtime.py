"""Read-only UART telemetry stress; preserves a known reset watchdog latch.

This is not a motor-start qualification and never sends CLEAR/START/ARM.
The unchanged general idle preflight report is kept separately.
"""
import argparse
import json
from pathlib import Path
import threading
import time
import traceback
import urllib.request
import install_uart_rx_handoff as package
from current_zero_quality import ready


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://192.168.1.138:8080')
    parser.add_argument('--seconds',type=int,default=60)
    parser.add_argument('--outdir',required=True,type=Path)
    a=parser.parse_args();a.outdir.mkdir(parents=True,exist_ok=False)
    r=dict(schema='mic_ai.uart_rx_handoff_runtime.v1',passed=False,transport=a.url,
        motor_commands=0,clear_commands=0,firmware_writes=0,motor_start_qualified=False,
        powered_run_proof=False,samples=[],background_errors=[])
    stop=threading.Event();workers=[]
    def status(opener):
        with opener.open(a.url+'/api/status',timeout=8) as f:response=json.load(f)
        assert response.get('ok') is True and isinstance(response.get('data'),dict)
        return response['data']
    def client():
        op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while not stop.is_set():
            try:status(op)
            except Exception as e:r['background_errors'].append(str(e))
            stop.wait(.1)
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    latch_keys=('mc_transport_fault','bp_transport_fault','mc_fault','bp_fault',
        'mc_fault_current_mask','mc_fault_occurred_mask','estop')
    try:
        first=status(op);r['before']=first
        okay,reason=package.install.precheck(first);assert okay,reason
        r['protection_latches_before']={k:first.get(k) for k in latch_keys}
        r['known_reset_watchdog_present']=first.get('mc_transport_fault')==7
        # bad_cnt is cumulative and includes the already recorded reset
        # watchdog. Permit exactly that one baseline event, never a CRC or
        # sequence error, and reject any increase during this diagnostic.
        assert first['mc_bad_cnt'] in (0,1)
        if first['mc_bad_cnt']:
            assert r['known_reset_watchdog_present'] and first['mc_last_bad_reason']==13
        for _ in range(2):
            t=threading.Thread(target=client,daemon=True);workers.append(t);t.start()
        end=time.monotonic()+a.seconds
        while time.monotonic()<end:
            began=time.monotonic();s=status(op)
            r['samples'].append(dict(duration_s=time.monotonic()-began,status=s))
            okay,reason=package.install.precheck(s);assert okay,reason
            assert (s['fw_build'],s['mc_fw_build'])==package.package.NEW
            assert {k:s.get(k) for k in latch_keys}==r['protection_latches_before'],'Protection state changed'
            assert s['enc_source']=='nucleo_g431_i2c1' and s['enc_diag_mode']==6
            assert s['enc_reads']>=first['enc_reads'] and s['enc_errors']==first['enc_errors']==0
            assert s['enc_peer_bad']==first['enc_peer_bad'],'Encoder telemetry packet rejected'
            assert s['enc_bus_ok']==s['enc_ok']==s['enc_speed_ok']==1 and s['enc_age_ms']<100
            assert s['enc_io_error']==s['enc_init_error']==0 and s['enc_diag_cfg_match']==1
            assert (s['enc_status']&0x38)==0x20 and ready(s)
            assert s['mc_bad_cnt']==first['mc_bad_cnt'],'New cumulative control event'
            for key in ('mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags','bp_bad',
                        'uno_rx_dropped','uno_rx_hw_errors','uno_tx_short_writes'):
                assert s[key]==0,key
            assert s['hmi_vbus_hv_calibrated']==1
            assert s['uno_rx_rescued']>=first['uno_rx_rescued']
            time.sleep(.15)
        r['after']=r['samples'][-1]['status']
        r['read_delta']=r['after']['enc_reads']-first['enc_reads']
        r['accepted_packet_delta']=r['after']['enc_peer_good']-first['enc_peer_good']
        r['peer_bad_delta']=r['after']['enc_peer_bad']-first['enc_peer_bad']
        r['error_delta']=r['after']['enc_errors']-first['enc_errors']
        r['rescued_delta']=r['after']['uno_rx_rescued']-first['uno_rx_rescued']
        r['max_status_duration_s']=max(v['duration_s'] for v in r['samples'])
        r['protection_latches_preserved']=True
        r['passed']=not r['background_errors'] and r['read_delta']>0 and r['accepted_packet_delta']>0
    except Exception as e:
        r['error']=str(e) or type(e).__name__;r['traceback']=traceback.format_exc()
    finally:
        stop.set()
        for t in workers:t.join(9)
        (a.outdir/'report.json').write_text(json.dumps(r,indent=2)+'\n')
        print(json.dumps({k:r.get(k) for k in ('passed','error','read_delta','accepted_packet_delta',
            'peer_bad_delta','error_delta','rescued_delta','max_status_duration_s','background_errors')}))
    return 0 if r['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
