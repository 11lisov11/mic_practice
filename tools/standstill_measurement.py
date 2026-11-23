"""Plan or execute one current-limited identification point. Default: OFFLINE PLAN.

Explicit powered execution uses the original guarded bounded START, never CLEAR.
The native point auto-stops; a separate host timer is backup only. Captures are
fsynced and CRC checked before the ACK releasing this NEW measurement buffer.
"""
import argparse,hashlib,json,math,os,secrets,struct,sys,threading,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
PAIR=(2026102937,2026102938)
from configure_multi_algorithm import crc32c
SIZE=1664

def configuration(kind,freq,axis,current,rs,cal=None,run_id=None):
    if kind not in ('dc','ac') or not math.isfinite(axis) or not 0<=axis<2*math.pi:raise ValueError('invalid excitation')
    if not math.isfinite(current) or not .025<=abs(current)<=.3 or not math.isfinite(rs) or not 0<rs<=100:raise ValueError('invalid current/Rs')
    if kind=='ac':
        if not 1<=freq<=200 or current<0 or not cal or not cal.get('accepted'):raise ValueError('AC requires accepted inverter calibration')
        coefficients=bytes.fromhex(cal['coefficient_bytes_hex']);assert len(coefficients)==28
        duration=math.ceil((max(3,math.ceil(freq))+5)/freq*1000)+1;calcrc=crc32c(coefficients)
    else:freq=0.;duration=3000;coefficients=struct.pack('<7f',1,0,0,0,.025,0,0);calcrc=0
    run=run_id or secrets.randbelow(2**32-1)+1
    raw=struct.pack('<IIffffI',run,1 if kind=='dc' else 2,freq,axis,current,rs,duration)+coefficients+struct.pack('<I',calcrc)
    assert len(raw)==60 and duration<=10000
    return dict(kind=kind,run_id=run,frequency_hz=freq,axis_rad=axis,current_reference_a=current,rs_star_ohm=rs,
        native_duration_ms=duration,uno_backup_limit_s=(duration+2000)/1000,config_crc=crc32c(raw),
        configuration_hex=raw.hex(),source_calibration=cal,starts_without_execute=False,
        commands=[f'IDENT SET {i} {struct.unpack_from("<I",raw,4*i)[0]:08x}' for i in range(15)]+[f'IDENT COMMIT {crc32c(raw):08x}'])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kind',choices=('dc','ac'),default='dc')
    p.add_argument('--frequency',type=float,default=5);p.add_argument('--axis-deg',type=float,default=0)
    p.add_argument('--current-a',type=float,default=.06);p.add_argument('--rs-ohm',type=float,default=12.23)
    p.add_argument('--calibration',type=Path);p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--url',default='http://192.168.1.138:8080');p.add_argument('--execute',action='store_true')
    p.add_argument('--confirm-powered-autonomous',action='store_true');p.add_argument('--confirm-rotor-stationary',action='store_true')
    a=p.parse_args();cal=json.loads(a.calibration.read_text(encoding='utf-8')) if a.calibration else None
    cfg=configuration(a.kind,a.frequency,math.radians(a.axis_deg),a.current_a,a.rs_ohm,cal)
    out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    (out/'plan.json').write_text(json.dumps(dict(pair=PAIR,**cfg),indent=2),encoding='utf-8')
    if not a.execute:print(json.dumps(dict(plan=str(out/'plan.json'),hardware_commands=0,start_commands=0)));return 0
    if not a.confirm_powered_autonomous or not a.confirm_rotor_stationary:p.error('Explicit powered and stationary-rotor confirmation required')
    if cal and cal.get('source_kind')!='hardware':p.error('Synthetic inverter calibration cannot drive a physical identification test')
    token=(ROOT/'.unoq_ssh/control_token').read_text(encoding='utf-8').strip()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    report=dict(passed=False,commands=[],start_commands=0,clear_commands=0,source_kind='hardware',rotor_stationary_verified=True,point=cfg)
    def request(path,body=None):
        headers={'X-UNOQ-Control-Token':token,'Content-Type':'application/json'}
        r=urllib.request.Request(a.url.rstrip('/')+path,data=None if body is None else json.dumps(body).encode(),headers=headers,method='GET' if body is None else 'POST')
        with opener.open(r,timeout=12) as response:data=json.load(response)
        if data.get('ok') is not True:raise RuntimeError(str(data.get('error','request rejected')))
        return data
    def status():
        s=request('/api/status')['data']
        with (out/'status.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(s,ensure_ascii=False)+'\n')
        if (s.get('fw_build'),s.get('mc_fw_build'))!=PAIR or not 0<=s.get('mc_age_ms',9999)<300:raise RuntimeError('wrong/stale native peer')
        if s.get('id_valid')!=1 or not 0<s.get('id_timing_cycles',0)<=4800:raise RuntimeError('native OFF-only IRQ timing qualification missing')
        return s
    def command(cmd):
        report['commands'].append(cmd);request('/api/cmd',{'cmd':cmd})
    def stopped(s):return s.get('state')=='SAFE' and s.get('pwm')==0 and not(s.get('bp_status',0x22)&0x22)
    def healthy(s):
        sd=s.get('mc_sd_live') or {}
        return (all(s.get(k)==0 for k in ('mc_fault_current_mask','mc_fault_occurred_mask','mc_transport_fault','estop')) and
          s.get('mc_current_zero_ready')==1 and sd.get('level')=='HIGH' and sd.get('break_irq_enabled') is True and sd.get('config_ok') is True)
    timer=None;started=False
    def backup_stop():
        try:request('/api/stop-sequence',{'emergency':False})
        except Exception:pass
    try:
        before=status()
        if not stopped(before) or not healthy(before) or not 250<=before.get('vdc',0)<=350 or before.get('id_flags',0)&14:
            raise RuntimeError('Powered preflight not ready; no CLEAR or START')
        for cmd in cfg['commands']:command(cmd);time.sleep(.10)
        deadline=time.monotonic()+4
        while True:
            s=status()
            if s.get('id_config_crc')==cfg['config_crc'] and s.get('id_flags')==1:break
            if time.monotonic()>deadline:raise RuntimeError('native configuration CRC acknowledgement missing')
            time.sleep(.1)
        request('/api/algorithm',{'algorithm':4})
        deadline=time.monotonic()+3
        while True:
            s=status()
            if s.get('algorithm_selected')==s.get('algorithm_requested')==4:break
            if time.monotonic()>deadline:raise RuntimeError('native identification mode not selected')
            time.sleep(.1)
        command('MODE VF');command('SET FREQ 5')
        command(f'IDENT EXECUTE {cfg["config_crc"]:08x}')
        request('/api/hv-arm',{'action':'arm','confirm':'ARM 310V'})
        timer=threading.Timer(cfg['uno_backup_limit_s']+3,backup_stop);timer.daemon=True;timer.start()
        report['start_commands']=1;started=True
        request('/api/start-sequence',{'manual':False,'runlimit_s':cfg['uno_backup_limit_s']})
        deadline=time.monotonic()+cfg['uno_backup_limit_s']+12
        while True:
            s=status()
            if not healthy(s) or s.get('id_fault'):raise RuntimeError('Protection/measurement fault; no retry')
            if stopped(s) and s.get('id_complete')==1 and s.get('id_run_id')==cfg['run_id']:break
            if time.monotonic()>deadline:raise RuntimeError('native auto-stop or complete data missing')
            time.sleep(.12)
        crc=s['id_result_crc'];raw=bytearray()
        for page in range(13):
            reply=request('/api/identification?page='+str(page))
            if reply.get('crc32c')!=crc or reply.get('run_id')!=cfg['run_id']:raise RuntimeError('capture changed during retrieval')
            block=bytes.fromhex(reply['hex'])
            if len(block)!=128:raise RuntimeError('truncated capture page')
            raw.extend(block)
        if len(raw)!=SIZE or crc32c(raw)!=crc:raise RuntimeError('whole native capture CRC mismatch')
        path=out/'capture.bin'
        with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        assert path.read_bytes()==raw
        report.update(capture_saved=True,capture_crc=crc,capture_sha256=hashlib.sha256(raw).hexdigest(),native_result_complete=True)
        # ACK releases only this newly fsynced ID buffer. It is not a fault CLEAR.
        command(f'IDENT ACK {crc:08x}')
        deadline=time.monotonic()+3
        while True:
            s=status()
            if s.get('id_valid')==1 and not(s.get('id_flags',14)&14) and s.get('id_config_crc')==0:break
            if time.monotonic()>deadline:raise RuntimeError('Saved capture retained; native ACK not confirmed')
            time.sleep(.1)
        request('/api/algorithm',{'algorithm':1})
        report.update(passed=True,native_buffer_release_confirmed=True)
    except Exception as exc:report['passed']=False;report['error']=str(exc)
    finally:
        if started:backup_stop()
        if timer:timer.cancel()
        try:report['after']=status()
        except Exception as exc:report['last_status_error']=str(exc)
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ('passed','error','start_commands','clear_commands','capture_crc')}));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
