"""One ordinary pre-trial ACK for the sole startup-UV latch. Never START."""
import argparse,json,time
import run_i2c_wire_openload_5hz as w
p=w.package
def eligible(s,proof,m):
    return (m.t.startup_uv_only(s) and m.t.sd_high(s,True) and m.setup_ok(s) and w.wire_empty(s)
      and s.get('enc_errors')==0 and s.get('enc_bus_ok')==s.get('enc_ok')==1
      and s.get('enc_age_ms',9999)<100 and s.get('enc_peer_epoch')==proof['enc_peer_epoch']
      and all(s.get(k)==proof[k]==0 for k in w.RUN_FIELDS))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--one-startup-uv-ack-for-authorized-trial',action='store_true')
    ap.add_argument('--preflight',required=True);ap.add_argument('--boot-proof',required=True);a=ap.parse_args()
    from pathlib import Path
    out=Path(a.preflight).resolve();proof=w.boot_proof(Path(a.boot_proof));m=w.load_trial()
    initial=json.loads(p.read(out/'initial_response.json'))['data'];assert eligible(initial,proof,m)
    checks=1
    for change in ({'pwm':1},{'hmi_hv_armed':1},{'vdc':240},{'vdc':360},{'mc_age_ms':300},{'bp_temp_fault':1},
      {'mc_fault_current_mask':4},{'mc_fault_occurred_mask':1028},{'mc_fault_reason':12},{'mc_transport_fault':7},
      {'enc_errors':1},{'enc_wire_valid':1},{'run_id':1},{'mc_sd_live':dict(initial['mc_sd_live'],level='LOW')},
      {'mc_sd_live':dict(initial['mc_sd_live'],break_irq_enabled=False)}):
        assert not eligible(dict(initial,**change),proof,m),change;checks+=1
    p.write(out/'startup_uv_ack_gate_selftest.json',json.dumps(dict(passed=True,checks=checks,hardware_commands=0),indent=2)+'\n')
    if not a.one_startup_uv_ack_for_authorized_trial:
        print(json.dumps(dict(passed=True,checks=checks,hardware_commands=0)));return 0
    assert not (out/'ack_report.json').exists(),'No repeated acknowledgement'
    commands=[];h=m.WifiHmi('http://192.168.1.138:8080',m.read_token(str(p.ROOT/'.unoq_ssh/control_token')),commands,False)
    r=dict(passed=False,CLEAR_commands=0,START_commands=0,reset_commands=0,flash_commands=0,snapshots_erased=False,commands=commands,used_source_sha256=p.sha(Path(__file__)))
    try:
        previous=None;deadline=time.monotonic()+5
        while True:
            s=h.status()
            with (out/'before_ack_samples.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(s)+'\n')
            if eligible(s,proof,m):
                if previous and s['enc_reads']>previous['enc_reads']:break
                previous=s
            else:
                assert m.t.checks.off(s) and m.t.checks.transport_clean(s) and s['enc_errors']==0,'State changed before ACK'
            assert time.monotonic()<deadline,'No two fresh startup-UV-only snapshots'
            time.sleep(.3)
        p.write(out/'saved_before_CLEAR.json',json.dumps(s,indent=2)+'\n')
        r['CLEAR_commands']=1;h.command('CLEAR');deadline=time.monotonic()+5
        while True:
            s=h.status()
            with (out/'after_ack_samples.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(s)+'\n')
            if m.t.ready(s) and m.setup_ok(s):break
            assert m.t.checks.off(s) and time.monotonic()<deadline,'Single ACK did not establish protected ready OFF'
            time.sleep(.2)
        p.write(out/'saved_after_CLEAR.json',json.dumps(s,indent=2)+'\n')
        r.update(passed=True,state=s['state'],pwm=s['pwm'],vdc=s['vdc'],mc_fault=s['mc_fault'],
          mc_fault_current_mask=s['mc_fault_current_mask'],mc_fault_occurred_mask=s['mc_fault_occurred_mask'],
          enc_errors=s['enc_errors'],wire_state=s['enc_wire_state'])
    except Exception as exc:r['error']=str(exc) or type(exc).__name__
    finally:h.close()
    p.write(out/'ack_report.json',json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='commands'}))
    return 0 if r['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
