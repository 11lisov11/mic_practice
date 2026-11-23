"""One bounded 5-Hz V/f trial observing AS5600; no FOC, CLEAR, reset or flash."""
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import run_current_shunt_5hz as trial
from current_zero_quality import ready as zero_ready


def sensor_healthy(s):
    try:
        return (s['enc_source']=='uno_q_i2c2' and s['enc_bus_ok']==s['enc_ok']==1
            and s['enc_init_error']==s['enc_io_error']==0
            and 0<=s['enc_age_ms']<100 and s['enc_reads']>0
            and type(s['enc_status']) is int and s['enc_status']&0x38==0x20
            and type(s['enc_raw']) is int and 0<=s['enc_raw']<=4095
            and type(s['enc_rpm']) in (int,float) and math.isfinite(s['enc_rpm'])
            and abs(s['enc_rpm'])<600)
    except (KeyError,TypeError,ValueError):
        return False


class EncoderPolicy:
    def __init__(self):
        self.baseline=None
        self.active_since=None
        self.maximum_rpm=0.0
        self.saved_wave=None

    def same_sensor(self,s):
        return (sensor_healthy(s) and self.baseline is not None
            and s['enc_errors']==self.baseline['enc_errors']
            and s['enc_reads']>=self.baseline['enc_reads']
            and s.get('mc_break_wave_hex','-')==self.saved_wave)

    def ready(self,s):
        if not (trial.checks.ready(s) and zero_ready(s) and trial.sd_high(s,True)
                and trial.archive_before_start(s) and sensor_healthy(s)):
            return False
        if self.baseline is None:
            self.baseline=dict(enc_errors=s['enc_errors'],enc_reads=s['enc_reads'])
            self.saved_wave=s.get('mc_break_wave_hex','-')
        return self.same_sensor(s)

    def active(self,s,base_active):
        if not base_active(s) or not self.same_sensor(s):
            return False
        now=time.monotonic()
        if self.active_since is None:self.active_since=now
        if s.get('enc_speed_ok')==1:self.maximum_rpm=max(self.maximum_rpm,abs(s['enc_rpm']))
        # Detect a disconnected shaft/magnet or a stalled drive, without retry.
        return now-self.active_since<2.5 or self.maximum_rpm>10


def summarize(rows):
    active=[r['status'] for r in rows if r.get('status',{}).get('pwm')==1]
    valid=[s for s in active if sensor_healthy(s) and s.get('enc_speed_ok')==1]
    moving=[s for s in valid if abs(s['enc_rpm'])>10]
    rpm=[s['enc_rpm'] for s in moving]
    reads=[s['enc_reads'] for s in valid]
    errors=[s['enc_errors'] for s in active if 'enc_errors' in s]
    distinct=len({s['enc_raw'] for s in moving})
    return dict(passed=bool(len(moving)>=3 and len(valid)==len(active) and reads
        and max(reads)>min(reads) and distinct>=3 and errors and max(errors)==min(errors)),
        active_samples=len(active),valid_samples=len(valid),moving_samples=len(moving),
        distinct_moving_angles=distinct,rpm_min=min(rpm) if rpm else None,
        rpm_max=max(rpm) if rpm else None,rpm_mean=sum(rpm)/len(rpm) if rpm else None,
        sensor_errors_delta=max(errors)-min(errors) if errors else None,
        control_mode='scalar_Vf',sensor_used_for_motor_feedback=False,
        absolute_speed_accuracy_qualified=False,
        limitation='HTTP angle samples are too sparse to unwrap multiple turns; RPM is the MCU AS5600 estimate, not an independent speed calibration.')


def main():
    # The existing runner owns authorization flag, preflight, host/MCU deadlines,
    # operator watchdog, one START, protection checks, recording and final STOP.
    if '--outdir' not in sys.argv:raise SystemExit('--outdir is required')
    out=Path(sys.argv[sys.argv.index('--outdir')+1]).resolve()
    policy=EncoderPolicy()
    trial.checks.PAIR=(2026102509,2026102510)
    base_active=trial.checks.active
    trial.zero_ok=zero_ready
    trial.ready=policy.ready
    trial.startup_uv_only=lambda s:False  # no automatic fault acknowledgement
    trial.checks.active=lambda s:policy.active(s,base_active)
    code=trial.main()
    path=out/'report.json'
    if path.is_file():
        r=json.loads(path.read_text(encoding='utf-8'))
        result=summarize(r.get('samples',[]))
        wave=policy.saved_wave
        result['retained_sd_sha256']=(hashlib.sha256(bytes.fromhex(wave)).hexdigest()
                                     if wave and wave!='-' else None)
        r['encoder_result']=result
        r['passed']=bool(r.get('passed') and result['passed'])
        path.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
        (out/'encoder_result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(dict(passed=r['passed'],encoder=result),indent=2),flush=True)
        return 0 if r['passed'] else 1
    return code


if __name__=='__main__':raise SystemExit(main())
