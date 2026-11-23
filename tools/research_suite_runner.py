"""Ordered research plan. Execute only a completely admitted selection; no auto CLEAR.

The full requested plan is deliberately blocked while vector/adaptive backends
are absent. Selecting VF_FIXED runs the existing MCU-timed scalar trial.
"""
import argparse,json,sys,time,uuid
from pathlib import Path
import current_only_lab as lab
import run_current_only_trial as trial
from research_suite.catalog import RESEARCH_ORDER,research_catalog

PAIR=(2026102911,2026102912)
lab.PAIR=PAIR;trial.checks.PAIR=PAIR


def plan(catalog,algorithms,cycles=3):
    by_id={a['id']:a for a in catalog}
    rows=[]
    for order,name in enumerate(algorithms,1):
        item=by_id[name]
        rows.append(dict(order=order,algorithm=name,label=item['label'],
            status='ready' if item['hardware_ready'] else 'blocked',
            reason_code=item['reason_code'],reason=item['reason'],
            cycles=cycles,target_hz=5,native_runlimit_s=5,off_dwell_s=10,
            rotation_measurement_available=False))
    return dict(schema='mic_ai.research_plan.v1',pair=list(PAIR),steps=rows,
        executable=all(r['status']=='ready' for r in rows),
        incomplete_stage_policy='stop_before_any_start_no_silent_skip',
        autonomous_boot_or_reset_start=False,protection_threshold_changes=False)


def export_dataset(run,out,run_id):
    source=run/'status.jsonl';rows=[];previous=None
    for line in source.read_text(encoding='utf-8').splitlines():
        s=json.loads(line);key=(s.get('run_id'),s.get('mc_current_window_tick_ms'))
        if key==previous:continue
        previous=key;rows.append(lab.sample(s,run_id))
    out.mkdir(exist_ok=False)
    p=out/'windows.jsonl';p.write_text(''.join(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n' for row in rows),encoding='utf-8')
    import hashlib
    lab.dump(out/'manifest.json',dict(schema=lab.SCHEMA,run_id=run_id,completed=True,
        load_condition='unloaded',load_condition_source='operator',rotor_speed_ground_truth=False,
        current_scale='nominal_shunts_not_externally_qualified',motor_commands_sent=0,
        samples=len(rows),accepted=sum(r['valid_for_learning'] for r in rows),
        windows_sha256=hashlib.sha256(p.read_bytes()).hexdigest()))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--algorithms',default=','.join(RESEARCH_ORDER))
    p.add_argument('--cycles',type=int,choices=range(1,4),default=3)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--confirm-powered-unloaded-autonomous',action='store_true')
    p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args();names=a.algorithms.split(',')
    if not names or len(set(names))!=len(names) or any(n not in RESEARCH_ORDER for n in names):p.error('Choose unique declared algorithm IDs')
    if names!=sorted(names,key=RESEARCH_ORDER.index):p.error('Keep the declared scalar/vector/adaptive research order')
    # Offline plan describes compiled capabilities only; it is never a start permit.
    status=dict(fw_build=PAIR[0],mc_fw_build=PAIR[1],research_native_valid=1,research_native_caps=1)
    if a.execute:
        if not a.confirm_powered_unloaded_autonomous:p.error('Fresh powered unloaded autonomous bench authorization required')
        status=lab.get_status('http://192.168.1.138:8080')
        if status.get('research_native_bad')!=0:raise RuntimeError('Capability transport has rejected frames; no START')
    program=plan(research_catalog(status),names,a.cycles)
    out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False);lab.dump(out/'plan.json',program)
    if not a.execute:
        print(json.dumps(program,ensure_ascii=False));return 0
    if not program['executable']:
        lab.dump(out/'report.json',dict(status='blocked',start_commands=0,clear_commands=0,reason='Requested selection contains unqualified backends',plan=program))
        print('BLOCKED: requested plan contains unavailable algorithms; zero START commands');return 2
    original=sys.argv
    result=dict(status='running',passed=False,cycles=[],clear_commands=0,ai_control_enabled=False)
    try:
        for step in program['steps']:
            if step['algorithm']!='VF_FIXED':raise RuntimeError('No actuator adapter for this algorithm')
            for cycle in range(1,a.cycles+1):
                status=lab.get_status('http://192.168.1.138:8080')
                if not next(r for r in research_catalog(status) if r['id']=='VF_FIXED')['hardware_ready']:raise RuntimeError('Native capability expired')
                dest=out/f'vf_cycle_{cycle:02}'
                sys.argv=['current_only_trial','--target-hz','5','--seconds','5','--confirm-powered-unloaded-autonomous','--outdir',str(dest)]
                code=trial.main();entry=json.loads((dest/'report.json').read_text(encoding='utf-8'))
                result['cycles'].append(dict(cycle=cycle,passed=entry['passed'],native_auto_stop_verified=entry.get('native_auto_stop_verified'),outputs_off_confirmed=entry.get('outputs_off_confirmed')))
                if (dest/'status.jsonl').exists():export_dataset(dest,out/f'dataset_{cycle:02}',uuid.uuid4().hex)
                lab.dump(out/'report.json',result)
                if code or not entry['passed']:raise RuntimeError('Trial failed; no repeat or CLEAR')
                if cycle<a.cycles:
                    until=time.monotonic()+10
                    while time.monotonic()<until:
                        s=lab.get_status('http://192.168.1.138:8080')
                        if s.get('pwm')!=0 or s.get('state')!='SAFE' or not 0<=s.get('mc_age_ms',99999)<300:raise RuntimeError('OFF dwell not confirmed')
                        time.sleep(.3)
        result.update(status='completed',passed=True)
    except BaseException as exc:
        result.update(status='aborted',error=type(exc).__name__+': '+str(exc))
    finally:
        sys.argv=original
        if result['status']=='aborted':
            from run_wifi_nucleo_pwm_bench import WifiHmi
            from collect_wifi_telemetry import read_token
            h=WifiHmi('http://192.168.1.138:8080',read_token(str(Path(__file__).resolve().parents[1]/'.unoq_ssh/control_token')),[],False)
            try:
                code,body=h.fail_safe_stop();result['abort_stop']=dict(http=code,ok=body.get('ok'))
            except Exception as exc:result['abort_stop_error']=str(exc)
            finally:h.close()
        lab.dump(out/'report.json',result)
    print(json.dumps(result,ensure_ascii=False));return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
