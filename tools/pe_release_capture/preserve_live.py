"""Read-only archival predicate; no control commands, service changes or resets."""
import json,time
def complete(s):
    try:
        if s.get('enc_fault_decode_valid')!=1:return False
        if s.get('enc_errors',0)>0 and s.get('enc_fault_first_hex','-')=='-':return False
        first=next((r for r in s.get('enc_fault_records',[]) if r.get('kind')=='first_since_boot'),None)
        if first and first.get('pwm_moe') and s.get('enc_fault_pwm_hex','-')=='-':return False
        q=s.get('mc_sd_live',{})
        if not q.get('available') or not q.get('config_ok'):return False
        if q.get('first_record_ready'):
            if s.get('mc_break_wave_hex','-')=='-':return False
            records=s.get('mc_break_snapshots',[])
            if not any(r.get('available') and r.get('captured') and r.get('kind')=='first_since_boot' for r in records):return False
        return True
    except (TypeError,ValueError):return False
def preserve(read_status,guard,out):
    out.mkdir(parents=True,exist_ok=False);deadline=time.monotonic()+20;stable=0
    while True:
        s=read_status()
        with (out/'samples.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(s)+'\n')
        okay,why=guard(s)
        if not okay:raise RuntimeError('Unsafe archival state: '+why)
        # Snapshot age fields naturally change. Require complete decoded data,
        # then save multiple readings, retaining every earlier version above.
        stable=stable+1 if complete(s) else 0
        if stable>=3:
            (out/'saved_status.json').write_text(json.dumps(s,indent=2)+'\n',encoding='utf-8')
            return s
        if time.monotonic()>deadline:raise RuntimeError('Saved captures still incomplete; no flash allowed')
        time.sleep(.3)
