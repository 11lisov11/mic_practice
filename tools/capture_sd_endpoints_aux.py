"""Passive Saleae CH6/PA6 versus CH7/STEVAL TP23, auxiliary-only.

No control commands, flashing, resetting or supply switching. J1 must be
physically unplugged and bus discharged before connecting any probes/USB.
"""
import argparse
import csv
import io
import json
from pathlib import Path
import urllib.request

RATE=24_000_000
DEVICE='12092652639477301394'
SUPPORTED_PAIRS=((2026101813,2026101812),(2026102001,2026102002))


def status():
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open('http://192.168.1.138:8080/api/status',timeout=8) as f:p=json.load(f)
    if p.get('ok') is not True:raise RuntimeError('HMI status unavailable')
    return p['data']


def passive_ready(s):
    return ((s.get('fw_build'),s.get('mc_fw_build')) in SUPPORTED_PAIRS
        and s.get('state')=='SAFE' and s.get('pwm')==0 and s.get('hmi_hv_armed')==0
        and not(s.get('bp_status',0x22)&0x22) and 0<=s.get('mc_age_ms',99999)<300
        and s.get('bp_vbus_valid')==1 and 0<=s.get('bp_vbus_age_ms',99999)<300
        and 0<=s.get('vdc',999)<20 and 0<=s.get('bp_vdc',999)<20)


def analyze(stream,rate=RATE):
    rows=csv.reader(stream);header=next(rows)
    norm=[''.join(c.lower() for c in x if c.isalnum()) for x in header]
    cols={ch:norm.index('channel'+str(ch)) for ch in (6,7)}
    samples=[]
    for row in rows:
        if not row:continue
        t=float(row[0]);values={ch:int(row[col]) for ch,col in cols.items()}
        if any(x not in (0,1) for x in values.values()):raise ValueError('non-binary level')
        if samples and t<samples[-1][0]:raise ValueError('time moved backwards')
        samples.append((t,values))
    if len(samples)<2:raise ValueError('need start and end observations')
    pulses={}
    for ch in (6,7):
        lows=[];start=samples[0][0] if samples[0][1][ch]==0 else None
        left=start is not None;previous=samples[0][1][ch]
        for t,v in samples[1:]:
            if previous==1 and v[ch]==0:start=t;left=False
            if previous==0 and v[ch]==1:
                lows.append(dict(start_s=start,end_s=t,width_us=None if left else (t-start)*1e6,left_censored=left,right_censored=False));start=None
            previous=v[ch]
        if start is not None:lows.append(dict(start_s=start,end_s=samples[-1][0],width_us=None,left_censored=left,right_censored=True))
        pulses[str(ch)]=lows
    tolerance=2/rate
    paired=[];used=set()
    for i,a in enumerate(pulses['6']):
        matches=[j for j,b in enumerate(pulses['7']) if j not in used and abs(a['start_s']-b['start_s'])<=tolerance and abs(a['end_s']-b['end_s'])<=tolerance]
        if matches:used.add(matches[0]);paired.append([i,matches[0]])
    return dict(sample_rate_hz=rate,sample_period_ns=1e9/rate,low_intervals=pulses,
        matched_low_intervals=paired,unmatched_pa6_intervals=len(pulses['6'])-len(paired),
        unmatched_tp23_intervals=len(pulses['7'])-len(paired),timing_tolerance_ns=tolerance*1e9,
        event_observed=bool(pulses['6'] or pulses['7']),
        physical_cause_proven=False,
        limitations=['Digital threshold crossings, not analog voltages.',
                     'No event under auxiliary-only conditions does not clear the powered 22/25-Hz fault.',
                     'Probe loading and the common ground can change the observed circuit.'])


def self_test():
    def run(text):return analyze(io.StringIO(text))
    same=run('Time [s],Channel 6,Channel 7\n0,1,1\n0.000001,0,0\n0.0000014,1,1\n0.001,1,1\n')
    assert len(same['matched_low_intervals'])==1 and abs(same['low_intervals']['6'][0]['width_us']-.4)<1e-8
    only=run('Time [s],Channel 6,Channel 7\n0,1,1\n0.000001,0,1\n0.0000014,1,1\n0.001,1,1\n')
    assert only['unmatched_pa6_intervals']==1 and not only['matched_low_intervals']
    cut=run('Time [s],Channel 6,Channel 7\n0,0,1\n0.001,1,1\n0.002,0,1\n0.003,0,1\n')
    assert cut['low_intervals']['6'][0]['left_censored'] and cut['low_intervals']['6'][0]['width_us'] is None
    assert cut['low_intervals']['6'][1]['right_censored'] and cut['low_intervals']['6'][1]['width_us'] is None
    empty=run('Time [s],Channel 6,Channel 7\n0,1,1\n1,1,1\n');assert not empty['event_observed']
    try:run('Time [s],Channel 6\n0,1\n1,1\n')
    except ValueError:pass
    else:raise AssertionError('missing TP23 accepted')
    safe=dict(fw_build=2026101813,mc_fw_build=2026101812,state='SAFE',pwm=0,hmi_hv_armed=0,bp_status=0,mc_age_ms=10,bp_vbus_valid=1,bp_vbus_age_ms=10,vdc=12,bp_vdc=12)
    assert passive_ready(safe)
    assert passive_ready(dict(safe,fw_build=2026102001,mc_fw_build=2026102002))
    assert not passive_ready(dict(safe,fw_build=2026102001,mc_fw_build=2026101812))
    for k,v in [('vdc',325),('bp_vdc',325),('pwm',1),('hmi_hv_armed',1),('mc_age_ms',400),('state','VF_RUN')]:assert not passive_ready(dict(safe,**{k:v}))
    print(json.dumps(dict(pass_=True,scope='offline CSV and passive preconditions',hardware_commands=0)))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--self-test',action='store_true')
    p.add_argument('--confirm-j1-physically-unplugged-meter-below-2v-before-probes',action='store_true')
    p.add_argument('--outdir',type=Path)
    p.add_argument('--duration',type=float,default=30)
    p.add_argument('--device',default=DEVICE)
    a=p.parse_args()
    if a.self_test:self_test();return
    if not a.confirm_j1_physically_unplugged_meter_below_2v_before_probes or not a.outdir:p.error('physical isolation/discharge confirmation and output directory required')
    if not 1<=a.duration<=60:p.error('duration must be 1..60 seconds')
    before=status()
    if not passive_ready(before):raise RuntimeError('fresh OFF and auxiliary-only bus required; no capture')
    from runtime_python import ensure_modules_or_reexec
    ensure_modules_or_reexec(['saleae'],'MIC_SD_ENDPOINT_REEXEC')
    from saleae import automation
    out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    (out/'before.json').write_text(json.dumps(before,indent=2)+'\n')
    with automation.Manager.connect(port=10430,connect_timeout_seconds=3) as mgr:
        devices=[d for d in mgr.get_devices() if d.device_id==a.device and not d.is_simulation]
        if len(devices)!=1:raise RuntimeError('expected physical analyzer is not connected')
        with mgr.start_capture(device_id=a.device,
                device_configuration=automation.LogicDeviceConfiguration(enabled_digital_channels=list(range(8)),digital_sample_rate=RATE,glitch_filters=[]),
                capture_configuration=automation.CaptureConfiguration(capture_mode=automation.TimedCaptureMode(duration_seconds=a.duration))) as cap:
            print('CAPTURE STARTED: J1 must stay unplugged; only J4 15 V may be enabled by operator.',flush=True)
            cap.wait();cap.save_capture(str(out/'sd_endpoints.sal'))
            cap.export_raw_data_csv(directory=str(out/'csv'),digital_channels=list(range(8)))
    with (out/'csv/digital.csv').open(newline='') as f:result=analyze(f)
    result.update(motor_commands=0,flash_commands=0,reset_commands=0,clear_commands=0,
        scope='auxiliary-only endpoint comparison; no powered motor qualification',
        channel_map={'6':'Nucleo PA6 CN10-13','7':'STEVAL-IPM15B TP23 SD','GND':'Nucleo CN7-19'})
    try:(out/'after.json').write_text(json.dumps(status(),indent=2)+'\n')
    except Exception as exc:result['after_status_error']=str(exc)
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
