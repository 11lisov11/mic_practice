"""Read-only deenergized USB test: pause, serial web polling, concurrent web polling."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading
import time
import urllib.request

def idle(s,build,mode=4):
    return ((s.get('fw_build'),s.get('mc_fw_build'))==(build,2026102510)
        and s.get('state')=='SAFE' and s.get('pwm')==0 and s.get('hmi_hv_armed')==0
        and not(s.get('bp_status',0x22)&0x22) and 0<=s.get('vdc',9999)<=20
        and 0<=s.get('mc_age_ms',9999)<300 and s.get('enc_diag_mode')==mode)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--confirm-j1-off-usb',action='store_true');p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--uno-build',type=int,choices=(2026102516,2026102517,2026102518),default=2026102517)
    p.add_argument('--sensor-mode',choices=('POLL100','FILTER100'),default='POLL100')
    a=p.parse_args()
    if not a.confirm_j1_off_usb:p.error('Existing physical J1-OFF/USB preparation must be confirmed')
    out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    r=dict(passed=False,read_only=True,motor_commands=0,clear_commands=0,flash_commands=0,
        other_clients_controlled=False,phases=[],http_errors=[],samples=[])
    lock=threading.Lock()
    def sample(label):
        op=urllib.request.build_opener(urllib.request.ProxyHandler({}));began=time.monotonic()
        with op.open('http://127.0.0.1:18080/api/status',timeout=6) as response:payload=json.load(response)
        if not payload.get('ok'):raise RuntimeError('Status unavailable')
        s=payload['data']
        if not idle(s,a.uno_build,5 if a.sensor_mode=='FILTER100' else 4):raise RuntimeError('Expected deenergized fresh SAFE status changed')
        row={'monotonic_s':time.monotonic(),'phase':label,'request_s':time.monotonic()-began,'status':s}
        with lock:
            r['samples'].append(row)
            with (out/'status.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
        return s
    def phase(label,duration,workers):
        before=sample(label+'_before');began=time.monotonic();end=began+duration
        def worker():
            while time.monotonic()<end:
                try:sample(label)
                except Exception as exc:
                    with lock:r['http_errors'].append({'phase':label,'error':str(exc)})
                    break
        if workers:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures=[pool.submit(worker) for _ in range(workers)]
                for f in futures:f.result()
        else:time.sleep(duration)
        after=sample(label+'_after')
        info={'name':label,'workers':workers,'elapsed_s':round(time.monotonic()-began,3),
            'reads':after['enc_reads']-before['enc_reads'],'errors':after['enc_errors']-before['enc_errors'],
            'timeouts':after['enc_diag_timeout_count']-before['enc_diag_timeout_count'],
            'nacks':after['enc_diag_nack_count']-before['enc_diag_nack_count'],
            'resets':after['enc_diag_controller_resets']-before['enc_diag_controller_resets'],
            'raw_berr_events':after.get('enc_diag_berr_count',0)-before.get('enc_diag_berr_count',0),
            'arlo_errors':after.get('enc_diag_arlo_count',0)-before.get('enc_diag_arlo_count',0),
            'busy_errors':after.get('enc_diag_busy_count',0)-before.get('enc_diag_busy_count',0),
            'max_sched_hold_us':after.get('enc_diag_sched_max_hold_us'),
            'mc_good_delta':after.get('mc_good_cnt',0)-before.get('mc_good_cnt',0),
            'mc_bad_delta':after.get('mc_bad_cnt',0)-before.get('mc_bad_cnt',0),
            'uno_rx_dropped_delta':after.get('uno_rx_dropped',0)-before.get('uno_rx_dropped',0)}
        r['phases'].append(info);print(json.dumps(info),flush=True)
    try:
        r['before']=sample('initial')
        for args in [('pause',5,0),('serial_status',10,1),('concurrent_status',30,3),('after_pause',5,0)]:phase(*args)
        s=sample('final');r['final']=s
        r['successful_reads']=s['enc_reads']-r['before']['enc_reads'];r['new_errors']=s['enc_errors']-r['before']['enc_errors']
        r['passed']=(r['successful_reads']>1000 and r['new_errors']==0 and not r['http_errors']
            and all(x['mc_bad_delta']==0 and x['uno_rx_dropped_delta']==0 and x['mc_good_delta']>0 for x in r['phases'])
            and all(row['status'].get('enc_bus_ok')==1 and row['status'].get('enc_io_error')==0
                    and row['status'].get('enc_diag_cfg_match')==1 and row['status'].get('enc_init_error')==0
                    and row['status'].get('enc_age_ms',9999)<100 for row in r['samples']))
        r['max_http_s']=max(x['request_s'] for x in r['samples'])
        r['rotation_qualified']=False;r['pwm_error_fix_proven']=False
    except Exception as exc:r['error']=str(exc)
    (out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:r.get(k) for k in ('passed','error','successful_reads','new_errors','max_http_s')}),flush=True)
    return 0 if r['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
