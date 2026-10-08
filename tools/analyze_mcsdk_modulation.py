"""Recover V/f modulation frequency and phase spacing from captured PWM duties."""
from __future__ import annotations

import argparse
from bisect import bisect_right
import hashlib
import json
from pathlib import Path

import numpy as np

from saleae_pwm_analyze import load_csv, transitions


def pulse_duties(times, values):
    events=transitions(times,values)
    rising=np.array([e["time"] for e in events if e["to"]==1])
    falling=[e["time"] for e in events if e["to"]==0]
    if len(rising)<20:
        raise ValueError("Insufficient PWM pulses")
    period=float(np.median(np.diff(rising)))
    centers=[]; duties=[]
    for start in rising:
        index=bisect_right(falling,start)
        if index<len(falling) and falling[index]-start<period:
            width=falling[index]-start
            centers.append(start+width/2)
            duties.append(width/period)
    return np.array(centers),np.array(duties)


def analyze(csv: Path, sample_rate: int, expected_hz: float) -> dict:
    times,values=load_csv(csv,[0,2,4])
    cutoff=times[0]+4096/sample_rate
    selected=[i for i,t in enumerate(times) if t>=cutoff]
    times=[times[i] for i in selected]
    values={ch:[values[ch][i] for i in selected] for ch in values}
    pulses=[pulse_duties(times,values[ch]) for ch in (0,2,4)]
    begin=max(p[0][0] for p in pulses); end=min(p[0][-1] for p in pulses)
    common=pulses[0][0][(pulses[0][0]>=begin)&(pulses[0][0]<=end)]
    if len(common)<100: raise ValueError("Insufficient common PWM periods")
    duties=np.array([np.interp(common,centers,duty) for centers,duty in pulses])
    alpha=(2/3)*(duties[0]-.5*duties[1]-.5*duties[2])
    beta=(duties[1]-duties[2])/np.sqrt(3)
    if not np.all(np.isfinite(alpha)) or not np.all(np.isfinite(beta)) or np.median(np.hypot(alpha,beta))<1e-5:
        raise ValueError("No valid three-phase modulation vector")
    angles=np.unwrap(np.arctan2(beta,alpha))
    relative_time=common-common[0]
    slope,offset=np.linalg.lstsq(np.column_stack((relative_time,np.ones(len(common)))),angles,rcond=None)[0]
    measured_hz=float(slope/(2*np.pi))
    angle_error=angles-(slope*relative_time+offset)
    design=np.column_stack((np.ones(len(common)),np.cos(slope*relative_time),np.sin(slope*relative_time)))
    fits=[]
    for duty in duties:
        coefficients=np.linalg.lstsq(design,duty,rcond=None)[0]
        predicted=design@coefficients
        amplitude=float(np.hypot(coefficients[1],coefficients[2]))
        phase=float(np.arctan2(-coefficients[2],coefficients[1])*180/np.pi)
        r2=float(1-np.sum((duty-predicted)**2)/np.sum((duty-duty.mean())**2))
        fits.append({"offset":float(coefficients[0]),"amplitude":amplitude,"phase_deg":phase,"r_squared":r2})
    phases=[float((f["phase_deg"]-fits[0]["phase_deg"]+180)%360-180) for f in fits]
    amplitudes=[f["amplitude"] for f in fits]
    checks={
        "frequency_from_waveform_matches_command":abs(measured_hz-expected_hz)<=max(.1,expected_hz*.02),
        "positive_phase_rotation":measured_hz>0,
        "V_phase_minus_120_degrees":abs(phases[1]+120)<3,
        "W_phase_plus_120_degrees":abs(phases[2]-120)<3,
        "balanced_phase_amplitudes":max(amplitudes)/min(amplitudes)<1.05,
        "sinusoidal_duty_envelopes":all(f["r_squared"]>.98 for f in fits),
    }
    return {"pass":all(checks.values()),"checks":checks,"csv":str(csv),
        "csv_sha256":hashlib.sha256(csv.read_bytes()).hexdigest(),
        "expected_hz":expected_hz,"measured_frequency_hz":measured_hz,
        "PWM_periods":len(common),"phase_relative_to_U_deg":phases,
        "angle_fit_RMS_deg":float(np.sqrt(np.mean(angle_error**2))*180/np.pi),
        "duty_fits":fits,"scope":"logical PWM modulation; not rotor speed, flux or phase voltage measurement"}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report",type=Path,required=True)
    parser.add_argument("--outdir",type=Path,required=True)
    args=parser.parse_args()
    source=json.loads(args.source_report.read_text())
    out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    results={}
    for frequency in (5,20):
        evidence=source[f"pwm_{frequency}hz"]
        if evidence.get("pass") is not True:
            raise ValueError("Only passed PWM evidence can qualify modulation")
        results[str(frequency)]=analyze(Path(evidence["raw_analysis"]["csv"]),24_000_000,frequency)
    report={"pass":all(r["pass"] for r in results.values()),"results":results,
            "hardware_validated":False,"source_report_sha256":hashlib.sha256(args.source_report.read_bytes()).hexdigest()}
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    return 0 if report["pass"] else 1


if __name__=="__main__":
    raise SystemExit(main())
