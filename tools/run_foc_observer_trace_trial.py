"""One3015/3016 FOC5Hz/5s trial + OFF-only observer/boot/ADC collection."""
import argparse,hashlib,json,shutil,time,urllib.request
from pathlib import Path
import prepare_observer_trace as package
import run_foc_boot_capture_trial as base
from observer_trace.web_status import decode_observer_trace_hex

base.package=package
base.trial.PAIR=package.NEW
base.trial.__doc__=__doc__


def observer_record(s,before):
    """Pure validation of the new immutable observer record."""
    assert base.trial.off(s),'Outputs not confirmed OFF during observer collection'
    now=base.decode_boot(s,package.NEW);old=base.decode_boot(before,package.NEW)
    assert now['identity']==old['identity'],'Native boot changed'
    assert now['Linux_boot_id']==old['Linux_boot_id'],'Linux boot changed'
    assert now['native_tick_ms']>=old['native_tick_ms'],'Native uptime decreased'
    assert s.get('mc_observer_trace_complete')==1,'Observer pages incomplete'
    assert s.get('mc_observer_trace_bad')==0,'Observer page reassembly error'
    raw=bytes.fromhex(s.get('mc_observer_trace_hex',''))
    decoded=decode_observer_trace_hex(raw.hex(),package.NEW[1])
    assert decoded['available'] and decoded['count']>0 and decoded['total_observer_samples']>0
    return raw,decoded,now


def collect_observer(out,fetch,before,limit_s=12):
    """Fetch is GET-only; this function cannot issue a motor command."""
    report=json.loads((out/'report.json').read_text(encoding='utf-8'))
    shutil.copy2(out/'report.json',out/'report_before_observer_collection.json')
    result=dict(passed=False,collection_is_GET_only=True,motor_commands=0)
    if report.get('start_commands'):
        try:
            until=time.monotonic()+limit_s
            while True:
                r=fetch();assert r['ok'];s=r['data']
                with (out/'observer_collection_status.jsonl').open('a',encoding='utf-8') as f:
                    f.write(json.dumps(r,ensure_ascii=False)+'\n')
                assert base.trial.off(s),'Outputs not confirmed OFF'
                if s.get('mc_observer_trace_complete')==1 and s.get('native_boot',{}).get('fresh'):
                    raw,decoded,boot=observer_record(s,before)
                    (out/'observer_trace.bin').write_bytes(raw)
                    package.write(out/'observer_trace_decoded.json',json.dumps(decoded,ensure_ascii=False,indent=2)+'\n')
                    package.write(out/'observer_final_status.json',json.dumps(r,ensure_ascii=False,indent=2)+'\n')
                    result.update(passed=True,bytes=len(raw),SHA256=hashlib.sha256(raw).hexdigest(),
                        samples=decoded['count'],total_observer_samples=decoded['total_observer_samples'],
                        valid_samples=decoded['valid_samples'],invalid_samples=decoded['invalid_samples'],
                        first_loss=decoded['first_loss'],control_fault=decoded['control_fault'],
                        boot_after_collection=boot)
                    break
                if time.monotonic()>=until:raise RuntimeError('Observer trace did not arrive completely; no automatic repeat')
                time.sleep(.2)
        except Exception as error:result['error']=str(error);report['passed']=False
    else:result.update(not_required=True,reason='No START sent')
    report['observer_record_audit']=result
    package.write(out/'observer_record_audit.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    package.write(out/'report.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in out.iterdir()
        if f.is_file() and f.name!='saved_files_sha256.json'}
    package.write(out/'saved_files_sha256.json',json.dumps(hashes,indent=2)+'\n')
    return bool(report.get('passed'))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--confirm-autonomous-powered',action='store_true',required=True)
    ap.add_argument('--clear-once',action='store_true');ap.add_argument('--outdir',type=Path,required=True)
    a=ap.parse_args();out=a.outdir.resolve();assert not out.exists()
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}));token=package.read(package.ROOT/'.unoq_ssh/control_token').strip()
    def fetch():
        q=urllib.request.Request('http://192.168.1.138:8080/api/status',
            headers={'X-UNOQ-Control-Token':token},method='GET')
        with op.open(q,timeout=8) as f:return json.load(f)
    r=fetch();assert r['ok'];before=r['data']
    assert base.trial.off(before) and base.trial.profile(before) and base.trial.link_power(before)
    assert base.trial.off_timing_ready(before)
    base.decode_boot(before,package.NEW)
    assert before['run_id']==before['run_start_ms']==0
    assert before['mc_adc_peak_complete']==before['mc_observer_trace_complete']==0
    assert before['mc_observer_trace_bad']==0 and before['mc_observer_trace_hex']=='-'
    rc=base.main()
    package.write(out/'observer_preflight.json',json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    done=collect_observer(out,fetch,before)
    print(json.dumps(dict(passed=rc==0 and done,observer_audit=json.loads(package.read(out/'observer_record_audit.json')).get('passed'),additional_motor_commands=0)))
    return 0 if rc==0 and done else 1


if __name__=='__main__':raise SystemExit(main())
