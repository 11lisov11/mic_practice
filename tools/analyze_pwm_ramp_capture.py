"""Fit the three-second MCSDK frequency ramp, rather than assuming a constant 5 Hz."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from saleae_pwm_analyze import load_csv
from analyze_mcsdk_modulation import pulse_duties

def analyze(csv):
    times,values=load_csv(csv,[0,2,4])
    pulses=[pulse_duties(times,values[ch]) for ch in (0,2,4)]
    begin=max(p[0][0] for p in pulses);end=min(p[0][-1] for p in pulses)
    common=pulses[0][0][(pulses[0][0]>=begin)&(pulses[0][0]<=end)]
    duties=np.array([np.interp(common,t,d) for t,d in pulses]);time=common-common[0]
    alpha=(2/3)*(duties[0]-.5*duties[1]-.5*duties[2]);beta=(duties[1]-duties[2])/np.sqrt(3)
    angles=np.unwrap(np.arctan2(beta,alpha))
    # Exclude only the boundary PWM cycles and the first 50 ms of startup.
    selected=(time>=.05)&(time<=time[-1]-.005)
    t=time[selected];a=angles[selected];ds=duties[:,selected]
    coeff=np.linalg.lstsq(np.column_stack((t*t,t,np.ones(len(t)))),a,rcond=None)[0]
    predicted=coeff[0]*t*t+coeff[1]*t+coeff[2]
    accel=float(coeff[0]/np.pi);start=float(coeff[1]/(2*np.pi));final=start+accel*float(time[-1])
    rms=float(np.sqrt(np.mean((a-predicted)**2))*180/np.pi)
    design=np.column_stack((np.ones(len(t)),np.cos(predicted),np.sin(predicted)))
    fits=[]
    for d in ds:
        c=np.linalg.lstsq(design,d,rcond=None)[0];estimate=design@c
        fits.append({'offset':float(c[0]),'amplitude':float(np.hypot(c[1],c[2])),
          'phase_deg':float(np.arctan2(-c[2],c[1])*180/np.pi),
          'r_squared':float(1-np.sum((d-estimate)**2)/np.sum((d-d.mean())**2))})
    phases=[float((f['phase_deg']-fits[0]['phase_deg']+180)%360-180) for f in fits]
    amplitudes=[f['amplitude'] for f in fits]
    checks=dict(ramp_0_to_5_over_3s=abs(accel-5/3)<.05 and abs(start)<.1 and abs(final-5)<.15,
       V_minus_120=abs(phases[1]+120)<3,W_plus_120=abs(phases[2]-120)<3,
       balanced=max(amplitudes)/min(amplitudes)<1.05,sinusoidal=all(f['r_squared']>.98 for f in fits),
       angle_quadratic_residual_under_3deg=rms<3)
    return dict(pass_=all(checks.values()),checks=checks,csv_sha256=hashlib.sha256(csv.read_bytes()).hexdigest(),
       expected_ramp_hz_s=5/3,measured_ramp_hz_s=accel,initial_frequency_hz=start,final_frequency_hz=final,
       phase_relative_to_U_deg=phases,angle_fit_RMS_deg=rms,span_s=float(time[-1]),PWM_periods=len(t),duty_fits=fits,
       limitations='Logical duty waveform, not phase voltage or measured rotor speed; 4 MHz timing quantization.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--csv',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();r=analyze(a.csv.resolve());r['pass']=r.pop('pass_');a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
