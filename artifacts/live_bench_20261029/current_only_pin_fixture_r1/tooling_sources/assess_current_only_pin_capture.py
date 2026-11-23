"""Reassess the recorded pin test using hardware deadtime, never another run."""
import csv,hashlib,json,struct
from pathlib import Path
import prepare_current_only_pin_fixture as fixture

def deadtime_counts(dtg):
    if dtg<128:return dtg
    if dtg<192:return (64+(dtg&63))*2
    if dtg<224:return (32+(dtg&31))*8
    return (32+(dtg&31))*16

def main():
    assert [deadtime_counts(x) for x in (0x72,0x80,0xbf,0xc0,0xdf,0xe0,0xff)]==[114,128,254,256,504,512,1008]
    out=fixture.OUT/'capture_r1'
    initial=json.loads((out/'report.json').read_text())
    waveform=json.loads((out/'waveform_analysis.json').read_text())
    raw=(out/'fixture_after0.bin').read_bytes();w=struct.unpack('<64I',raw)
    divider=(1,2,4)[(w[18]>>8)&3]
    dt=deadtime_counts(w[17]&255)*divider/w[11]
    period=2*w[19]*(w[27]+1)/w[11]
    correction=dt/period
    sample_period=1/12_000_000
    tolerance=2*sample_period/period+.0003
    checks={};stats={}
    for ch in range(6):
        phase=ch//2
        raw_duty=w[20+phase]/w[19]
        expected=(raw_duty if ch%2==0 else 1-raw_duty)-correction
        observed=initial['channels'][str(ch)]
        ok=(abs(observed['duty_cycle']-expected)<=tolerance
            and abs(observed['frequency_hz']*period-1)<.005
            and observed['rising_edges']>70000
            and 4.98<observed['active_duration_s']<5.02)
        checks['channel_'+str(ch)]=ok
        stats[ch]=dict(expected_duty=expected,observed_duty=observed['duty_cycle'],frequency_hz=observed['frequency_hz'],rising_edges=observed['rising_edges'])
    checks.update(native_auto_stop=initial.get('native_auto_stop_verified') is True,
       restored_readback=initial.get('restored') is True,production_uart_restored=initial.get('production_live_restored') is True,
       no_digital_pair_overlap=waveform['no_overlap_pass'] is True,
       sd_high=initial.get('sd_high_entire_capture') is True,
       deadtime_matches=all(abs(q['min_gap_s']-dt)<=sample_period*1.1 for q in waveform['pairs'].values()))
    # At fixed 25/50/75% the high pulses nest U within V within W;
    # complementary low pulses nest W within V within U. This also distinguishes
    # VH from VL although both have the same duty, without another hardware run.
    violations=0.
    with (out/'csv/digital.csv').open(newline='') as stream:
        reader=csv.DictReader(stream);previous=None
        for row in reader:
            t=float(row['Time [s]']);bits=[int(row['Channel '+str(i)]) for i in range(6)]
            if previous is not None:
                last,signal=previous
                if ((signal[0] and not(signal[2] and signal[4])) or
                    (signal[2] and not signal[4]) or
                    (signal[5] and not(signal[3] and signal[1])) or
                    (signal[3] and not signal[1])):violations+=t-last
            previous=(t,bits)
    checks['cross_phase_channel_identity']=violations==0
    report=dict(passed=all(checks.values()),checks=checks,channels=stats,
       deadtime_nominal_us=dt*1e6,deadtime_measured_min_us=min(q['min_gap_s'] for q in waveform['pairs'].values())*1e6,
       duty_tolerance=tolerance,sample_rate_hz=12000000,
       correction_reason='Original evaluator compared pin high-time to CCR/ARR without subtracting the unchanged hardware deadtime. Original failed report and raw capture are preserved.',
       additional_hardware_runs=0,motor_application_validated=False,cross_phase_identity_violation_s=violations,
       capture_sha256=hashlib.sha256((out/'pwm_5seconds.sal').read_bytes()).hexdigest())
    dest=out/'assessment_final.json';assert not dest.exists()
    dest.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report));assert report['passed']

if __name__=='__main__':main()
