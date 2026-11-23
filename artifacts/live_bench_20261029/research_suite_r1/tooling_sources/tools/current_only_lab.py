"""Passive current-window recorder and offline, shadow-only learning experiment.

Never sends motor commands. Missing/stale measurements are not zero-filled.
The learning target is next-window phase RMS, never rotor speed or torque.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
import urllib.request
import uuid

PAIR = (2026102901, 2026102902)
SCHEMA = 'mic_ai.current_only.dataset.v1'


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def vector(value):
    return (isinstance(value, list) and len(value) == 3
            and all(finite(v) for v in value))


def sample(status, run_id, now=None):
    """Keep rejected windows too; only qualified, fresh, live windows train a model."""
    s = status
    problems = []
    if (s.get('fw_build'), s.get('mc_fw_build')) not in (PAIR, (2026102911, 2026102912)):
        problems.append('firmware_pair')
    if s.get('research_profile') != 'air56b2_current_only': problems.append('profile')
    for key, limit in (('mc_age_ms', 300), ('mc_current_age_ms', 750)):
        value = s.get(key)
        if not finite(value) or not 0 <= value < limit: problems.append(key)
    if s.get('mc_current_telemetry_valid') != 1: problems.append('current_invalid')
    if s.get('mc_current_zero_ready') != 1: problems.append('zero_not_ready')
    if s.get('mc_current_frozen') != 0: problems.append('frozen')
    if s.get('pwm') != 1: problems.append('pwm_off')
    if s.get('enc_source') != 'disabled': problems.append('unexpected_encoder')
    for key in ('mc_current_rms_a', 'mc_current_peak_a', 'mc_current_instant_a'):
        if not vector(s.get(key)): problems.append(key)
    if not finite(s.get('mc_current_coverage_pct')) or not 95 <= s['mc_current_coverage_pct'] <= 100:
        problems.append('coverage')
    if not finite(s.get('mc_current_window_ms')) or s['mc_current_window_ms'] <= 0: problems.append('window_length')
    if type(s.get('mc_current_window_tick_ms')) is not int or not 0<=s['mc_current_window_tick_ms']<2**32: problems.append('window_tick')
    if any(type(s.get(k)) is not int or not 0<=s[k]<2**32 for k in ('run_id','run_start_ms')):
        problems.append('native_run_identity')
    if s.get('mc_frequency_reference_valid') != 1 or not finite(s.get('mc_frequency_reference_hz')):
        problems.append('field_frequency')
    if not finite(s.get('freq_cmd')) or not finite(s.get('vdc')): problems.append('features')
    if any(s.get(key) != 0 for key in ('mc_fault_current_mask', 'mc_fault_occurred_mask', 'estop')):
        problems.append('protection_or_missing_status')
    # Preserve all native state (including ADC peak / SD snapshots) in raw JSONL.
    row = dict(schema=SCHEMA, run_id=run_id, host_utc=now or datetime.now(timezone.utc).isoformat(),
               host_monotonic_ns=time.monotonic_ns(), valid_for_learning=not problems,
               invalid_reasons=problems, current_scale_qualified=s.get('mc_current_scale_qualified') == 1,
               rotor_speed_rpm=None, rotor_speed_label_available=False,
               window_tick_ms=s.get('mc_current_window_tick_ms'),
               native_run_key=[s.get('fw_build'),s.get('run_id'),s.get('run_start_ms')],
               field_frequency_hz=s.get('mc_frequency_reference_hz'),
               command_frequency_hz=s.get('freq_cmd'), bus_voltage_v=s.get('vdc'),
               phase_rms_a=s.get('mc_current_rms_a'), status=s)
    return row


def get_status(url):
    req = urllib.request.Request(url.rstrip('/')+'/api/status', headers={'Cache-Control': 'no-cache'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=3) as reply: payload = json.load(reply)
    if payload.get('ok') is not True or not isinstance(payload.get('data'), dict):
        raise ValueError('Invalid status envelope')
    return payload['data']


def record(args):
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    run_id = uuid.uuid4().hex
    metadata = dict(schema=SCHEMA, run_id=run_id, load_condition=args.load,
                    load_condition_source='operator', motor='AIR56B2_250W',
                    rotor_speed_ground_truth=False, continuous_raw_adc=False,
                    ai_control_enabled=False, motor_commands_sent=0,
                    current_scale='nominal_shunts_not_externally_qualified',
                    samples=0, accepted=0, duplicate_windows=0, errors=[], completed=False)
    dump(out/'manifest.json', metadata)
    start = time.monotonic()
    previous_tick = None
    evidence_seen = set()
    try:
        with (out/'windows.jsonl').open('x', encoding='utf-8') as stream:
            while time.monotonic()-start < args.seconds:
                try:
                    s = get_status(args.url)
                    row = sample(s, run_id)
                    for key in ('mc_adc_peak_hex', 'mc_break_wave_hex', 'mc_zero_history_hex'):
                        raw = s.get(key)
                        if not isinstance(raw, str) or raw in ('', '-'): continue
                        digest = hashlib.sha256(raw.encode('ascii')).hexdigest()
                        if (key, digest) not in evidence_seen:
                            capture = out/'captures'/(key+'_'+digest+'.json')
                            capture.parent.mkdir(exist_ok=True)
                            dump(capture, dict(field=key, sha256_ascii=digest, raw_hex=raw,
                                               status=s, run_id=run_id))
                            evidence_seen.add((key, digest))
                    tick = row['window_tick_ms']
                    # Packet arrival/polling is not a new ADC window. No synthetic upsampling.
                    if tick is not None and tick == previous_tick:
                        metadata['duplicate_windows'] += 1
                    else:
                        previous_tick = tick
                        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')
                        stream.flush()
                        metadata['samples'] += 1
                        metadata['accepted'] += int(row['valid_for_learning'])
                    # Save startup/final state even if no live current window exists.
                    if not (out/'initial_status.json').exists(): dump(out/'initial_status.json', s)
                    dump(out/'last_status.json', s)
                except (OSError, ValueError, TypeError) as exc:
                    metadata['errors'].append(dict(elapsed_s=round(time.monotonic()-start, 3), error=str(exc)))
                    if len(metadata['errors']) >= 10: raise RuntimeError('Ten acquisition errors; recorder stopped') from exc
                time.sleep(args.period)
        metadata['completed'] = True
    finally:
        metadata['elapsed_s'] = round(time.monotonic()-start, 3)
        metadata['windows_sha256'] = hashlib.sha256((out/'windows.jsonl').read_bytes()).hexdigest()
        dump(out/'manifest.json', metadata)
    print(json.dumps(metadata, ensure_ascii=False))


def load_examples(paths):
    import numpy as np
    examples = []
    runs = []
    native_owners = {}
    for path in paths:
        manifest = json.loads((path.parent/'manifest.json').read_text(encoding='utf-8'))
        if manifest.get('schema') != SCHEMA or not manifest.get('completed'):
            raise ValueError('Incomplete/foreign dataset: '+str(path))
        if manifest.get('load_condition') != 'unloaded': raise ValueError('This experiment requires unloaded runs')
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        if {r['run_id'] for r in rows} != {manifest['run_id']}:
            raise ValueError('Mixed run identities')
        if manifest['run_id'] in runs: raise ValueError('Repeated run (would leak across holdout)')
        runs.append(manifest['run_id'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['windows_sha256']:
            raise ValueError('Dataset hash mismatch: '+str(path))
        for row in rows:
            if not sample(row['status'],row['run_id'])['valid_for_learning']:continue
            key=tuple(row['native_run_key'])
            if key in native_owners and native_owners[key]!=manifest['run_id']:
                raise ValueError('One physical MCU run was split across recording sessions')
            native_owners[key]=manifest['run_id']
        for a,b in zip(rows, rows[1:]):
            # Re-validate native status rather than trusting an edited derived valid flag.
            if not sample(a['status'], a['run_id'])['valid_for_learning'] or not sample(b['status'], b['run_id'])['valid_for_learning']: continue
            if a['native_run_key']!=b['native_run_key']:continue
            dt = (b['window_tick_ms']-a['window_tick_ms']) & 0xffffffff
            if not 0 < dt <= 1500: continue
            x = [a['command_frequency_hz'], a['field_frequency_hz'], a['bus_voltage_v'], dt/1000, *a['phase_rms_a']]
            y = b['phase_rms_a']
            if all(finite(v) for v in (*x,*y)): examples.append((a['run_id'], x, y))
    return runs, examples


def train(args):
    import numpy as np
    runs, examples = load_examples(args.inputs)
    if len(runs) < 3: raise ValueError('At least three independent runs are required; no shuffled-row split')
    holdout = set(runs[-max(1, len(runs)//4):])
    tr = [e for e in examples if e[0] not in holdout]
    te = [e for e in examples if e[0] in holdout]
    if min(len(tr), len(te)) < 30: raise ValueError('Need >=30 valid consecutive windows in each split')
    x,y = np.asarray([e[1] for e in tr]),np.asarray([e[2] for e in tr])
    xt,yt = np.asarray([e[1] for e in te]),np.asarray([e[2] for e in te])
    mean,scale = x.mean(0),np.maximum(x.std(0),1e-6)
    ym,ys = y.mean(0),np.maximum(y.std(0),1e-6)
    z,zt = (x-mean)/scale,(xt-mean)/scale
    target = (y-ym)/ys
    design = np.c_[np.ones(len(z)),z]
    penalty = np.eye(design.shape[1])*.01; penalty[0,0] = 0
    ridge = np.linalg.solve(design.T@design+penalty,design.T@target)
    # Small offline neural predictor. Fixed settings, deterministic seed, train-only scaling.
    rng = np.random.default_rng(29)
    weights = [rng.normal(0,.15,(z.shape[1],16)), np.zeros(16), rng.normal(0,.15,(16,3)), np.zeros(3)]
    m = [np.zeros_like(w) for w in weights]; v = [np.zeros_like(w) for w in weights]
    for epoch in range(1,args.epochs+1):
        w1,b1,w2,b2 = weights
        hidden = np.tanh(z@w1+b1)
        error = (hidden@w2+b2-target)*2/(len(z)*3)
        dh = (error@w2.T)*(1-hidden**2)
        gradients = [z.T@dh, dh.sum(0), hidden.T@error, error.sum(0)]
        for i,g in enumerate(gradients):
            g = np.clip(g,-10,10)
            m[i] = .9*m[i]+.1*g; v[i] = .999*v[i]+.001*g*g
            weights[i] -= .01*(m[i]/(1-.9**epoch))/(np.sqrt(v[i]/(1-.999**epoch))+1e-8)
    prediction = (np.tanh(zt@weights[0]+weights[1])@weights[2]+weights[3])*ys+ym
    ridge_prediction = (np.c_[np.ones(len(zt)),zt]@ridge)*ys+ym
    mae = lambda a: np.abs(a-yt).mean(0).tolist()
    result = dict(schema='mic_ai.current_response_model.v1', target='next_window_phase_rms_a',
                  features=['command_hz','field_hz','vbus_v','dt_s','rms_u_a','rms_v_a','rms_w_a'],
                  train_runs=[r for r in runs if r not in holdout], holdout_runs=list(holdout),
                  train_windows=len(tr), holdout_windows=len(te), mlp_mae_a=mae(prediction),
                  ridge_mae_a=mae(ridge_prediction), persistence_mae_a=mae(xt[:,-3:]),
                  rotor_speed_model=False, current_scale_qualified=False,
                  ai_control_enabled=False, deployment='offline_shadow_only',
                  beats_both_baselines=bool(np.abs(prediction-yt).mean() < min(np.abs(ridge_prediction-yt).mean(), np.abs(xt[:,-3:]-yt).mean())))
    out=args.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    np.savez(out/'model.npz', x_mean=mean, x_scale=scale, y_mean=ym, y_scale=ys,
             w1=weights[0], b1=weights[1], w2=weights[2], b2=weights[3], ridge=ridge)
    result['model_sha256']=hashlib.sha256((out/'model.npz').read_bytes()).hexdigest()
    dump(out/'report.json',result)
    print(json.dumps(result,ensure_ascii=False))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='action',required=True)
    r=sub.add_parser('record');r.add_argument('--url',default='http://192.168.1.138:8080')
    r.add_argument('--seconds',type=float,default=60);r.add_argument('--period',type=float,default=.1)
    r.add_argument('--load',choices=['unloaded','unknown'],default='unknown');r.add_argument('--outdir',type=Path,required=True)
    t=sub.add_parser('train');t.add_argument('inputs',nargs='+',type=Path)
    t.add_argument('--outdir',type=Path,required=True);t.add_argument('--epochs',type=int,default=300)
    a=p.parse_args()
    if a.action=='record':
        if not 0<a.seconds<=3600 or not .05<=a.period<=2:p.error('Record duration <=3600s, polling 0.05..2s')
        record(a)
    else:
        if not 1<=a.epochs<=2000:p.error('Epochs must be 1..2000')
        train(a)


if __name__=='__main__':main()
