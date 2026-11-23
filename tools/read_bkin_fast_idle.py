"""Read-only Wi-Fi archive of the new BKIN recorder; never sends control requests."""
import argparse
import importlib.util
import json
from pathlib import Path
import time
import urllib.request
from collect_wifi_telemetry import read_token,get_logs

ROOT=Path(__file__).resolve().parents[1]
PAIR=(2026101805,2026101804)
BASE='http://192.168.1.138:8080'
C=ROOT/'artifacts/live_bench_20261018/bkin_fast_capture_r1'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir',type=Path,required=True)
    args=p.parse_args()
    out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    r={'pass':False,'read_only':True,'start_commands':0,'clear_commands':0,'reset_commands':0,
        'flash_commands':0,'calibration_writes':0,'samples':[],'read_errors':[]}
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token=read_token(str(ROOT/'.unoq_ssh/control_token'))
    def get(path):
        req=urllib.request.Request(BASE+path,headers={'X-UNOQ-Control-Token':token})
        with opener.open(req,timeout=8) as response:body=json.load(response)
        if not body.get('ok') or not isinstance(body.get('data'),dict):raise RuntimeError('unavailable GET '+path)
        return body
    def save(name,data):
        (out/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    try:
        deadline=time.monotonic()+55
        while len(r['samples'])<6 and time.monotonic()<deadline:
            try:
                s=get('/api/status')['data'];r['samples'].append(s)
                with (out/'status.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(s)+'\n')
                if (s.get('fw_build'),s.get('mc_fw_build'))!=PAIR:raise RuntimeError('unexpected pair')
                if s.get('state')!='SAFE' or s.get('pwm')!=0 or s.get('hmi_hv_armed')!=0:
                    raise RuntimeError('outputs not confirmed off')
                time.sleep(.35)
            except (urllib.error.URLError,TimeoutError) as exc:
                r['read_errors'].append(str(exc));time.sleep(.5)
        if len(r['samples'])<6:raise RuntimeError('insufficient fresh statuses')
        # Final status after page assembly; diagnostic packets arrive only OFF.
        s=get('/api/status')['data'];r['samples'].append(s);save('final_status.json',s)
        snapshot=get('/api/break-snapshot');save('break_snapshot.json',snapshot)
        wave=get('/api/bkin-trace');save('bkin_trace.json',wave)
        raw_hex=s.get('mc_break_wave_hex','-')
        if raw_hex!='-':
            raw=bytes.fromhex(raw_hex);(out/'bkin_wave.bin').write_bytes(raw)
            spec=importlib.util.spec_from_file_location('fast_idle_hmi',C/'web_hmi/server.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            decoded=module.bkin_wave_status(s);save('decoded_wave.json',decoded)
            # Separate GETs observe different delivery/live ages; compare the
            # immutable record, not time-varying HTTP observation metadata.
            immutable=lambda d:{k:v for k,v in d.items() if k not in
                ('age_since_delivery_ms','live_peer_fresh')}
            r['independent_decode_matches']=immutable(decoded)==immutable(wave['data'])
            if not r['independent_decode_matches']:raise RuntimeError('HMI and raw independent decode differ')
        else:r['independent_decode_matches']=None
        last=r['samples'][-1];first=r['samples'][0]
        r['summary']={k:last.get(k) for k in ('fw_build','mc_fw_build','state','pwm','vdc',
            'bp_temp_c','mc_age_ms','mc_good','mc_bad','mc_bad_integrity','mc_bad_sequence',
            'mc_uart_error_flags','mc_transport_fault','uno_rx_dropped','mc_fault','mc_fault_reason',
            'mc_fault_current_mask','mc_fault_occurred_mask','mc_break_wave_good_pages',
            'mc_break_wave_bad_pages','estop')}
        r['wave']=wave['data'];r['snapshots']=snapshot['data']
        captured=[x for x in snapshot['data'].get('mc_break_snapshots',[]) if x.get('captured')]
        r['wave_tick_matches_first_snapshot']=(wave['data'].get('event_tick_ms')==captured[0]['raw']['tick_ms']) if captured and wave['data'].get('available') else None
        if r['wave_tick_matches_first_snapshot'] is False:raise RuntimeError('wave/snapshot event mismatch')
        (out/'logs.txt').write_text(get_logs(opener,BASE,token,.5),encoding='utf-8')
        r['fresh_uart']=all(0<=s.get('mc_age_ms',999999)<300 for s in r['samples'])
        r['reply_progress']=last.get('mc_good',0)>first.get('mc_good',0)
        r['new_uart_errors']={k:last.get(k,0)-first.get(k,0) for k in
            ('mc_bad','mc_bad_integrity','mc_bad_sequence','uno_rx_dropped')}
        r['pass']=r['fresh_uart'] and r['reply_progress'] and all(v==0 for v in r['new_uart_errors'].values())
    except Exception as exc:r['error']=str(exc)
    save('report.json',r)
    print(json.dumps({k:r.get(k) for k in ('pass','summary','wave','snapshots','independent_decode_matches','error')},ensure_ascii=True))
    return 0 if r['pass'] else 1

if __name__=='__main__':raise SystemExit(main())
