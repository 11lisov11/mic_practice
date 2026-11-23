"""Decode bounded stationary-axis captures and calibrate inverter reconstruction.

This module has no network or board-control code. A fitted electrical model does
not qualify rotor-speed feedback, mechanical parameters, or powered FOC.
"""
from __future__ import annotations
import math,struct
from pathlib import Path
import numpy as np
from scipy.optimize import minimize_scalar
from motor_identification.standstill import SCHEMA,identify

BINS=64;SIZE=128+BINS*24
def crc32c(data):
    v=0xffffffff
    for b in data:
        v^=b
        for _ in range(8):v=(v>>1)^(0x82f63b78 if v&1 else 0)
    return v^0xffffffff
def decode(raw:bytes,*,source_kind:str,expected_crc:int|None=None):
    if len(raw)!=SIZE or source_kind not in ('synthetic','hardware'):raise ValueError('capture size/source')
    if source_kind=='hardware' and expected_crc is None:raise ValueError('native capture CRC required')
    if expected_crc is not None and crc32c(raw)!=expected_crc:raise ValueError('native capture CRC mismatch')
    u=lambda pos:struct.unpack_from('<I',raw,pos)[0]
    f=lambda pos:struct.unpack_from('<f',raw,pos)[0]
    if u(0)!=0x3144494D or u(4)!=1 or u(36)!=BINS or u(40)!=16000 or u(16) not in (1,2):raise ValueError('capture identity')
    if u(20) or u(24)!=1 or u(100)!=1 or u(104)!=1:raise ValueError('aborted or wrong-axis capture')
    floats=[f(k) for k in (48,52,56,60,72,76,80)]
    if not all(math.isfinite(v) for v in floats):raise ValueError('nonfinite capture')
    if not 30<=f(72)<=f(76)<=350 or not 0<=f(80)<=.45:raise ValueError('capture operating limits')
    points=[]
    for k in range(BINS):
        a=struct.unpack_from('<H8hHI',raw,128+k*24)
        # count, six physical values, mean sin/cos, reserved, mean timestamp.
        n,*rest=a
        if not n:raise ValueError('missing phase/time bin')
        points.append([n,rest[0]*.001,rest[1]*.001,*[x*.01 for x in rest[2:6]],rest[6]/32767,rest[7]/32767,rest[9]*1e-6])
    data=np.asarray(points,dtype=float)
    expected=(.5 if u(16)==1 else 5/f(48))*16000
    coverage=100*u(28)/expected
    if not 95<=coverage<=100.5 or int(data[:,0].sum())!=u(28):raise ValueError('insufficient ADC coverage')
    return dict(schema='mic_ai.commissioning.point.v1',source_kind=source_kind,build=u(8),run_id=u(12),kind=u(16),
      frequency_hz=f(48),axis=f(52),reference_a=f(56),rs=f(60),duration_ms=u(64),cycles=u(68),
      peak_a=f(80),config_crc=u(84),calibration_crc=u(88),coverage_pct=min(100,coverage),
      current_scale='nominal_datasheet',points=data,physical_amp_scale_qualified=False,eligible_for_foc_start=False)
def means(d):return np.average(d['points'][:,1:7],axis=0,weights=d['points'][:,0])
def calibrate(dc_points:list[dict]):
    if len(dc_points)<18 or any(d['kind']!=1 for d in dc_points):raise ValueError('bipolar/multiple-axis DC points required')
    if len({round(d['axis'],2) for d in dc_points})<3:raise ValueError('three spatial axes required')
    if len({round(d['reference_a'],3) for d in dc_points})<6:raise ValueError('multiple signed current levels required')
    if len({d['run_id'] for d in dc_points})!=len(dc_points):raise ValueError('DC run reused')
    sources={d['source_kind'] for d in dc_points}
    if len(sources)!=1:raise ValueError('mixed synthetic and hardware provenance')
    fit=[d for d in dc_points if not math.isclose(abs(d['reference_a']),.12,abs_tol=.003)]
    val=[d for d in dc_points if d not in fit]
    if len(val)<6:raise ValueError('independent DC validation levels required')
    for d in dc_points:
        v=d['points'];early=np.average(v[:16,1:3],axis=0,weights=v[:16,0]);late=np.average(v[-16:,1:3],axis=0,weights=v[-16:,0])
        if np.linalg.norm(early-late)>.01:raise ValueError('DC current not settled')
    def matrix(points,knee):
        x=[];y=[]
        for d in points:
            ia,ib,va,vb,*_=means(d)
            ip=np.array([ia,-.5*ia+math.sqrt(3)*.5*ib,-.5*ia-math.sqrt(3)*.5*ib]);shape=ip/(np.abs(ip)+knee)
            x.extend([[va,-2*shape[0]/3,shape[1]/3,shape[2]/3,1,0],
                      [vb,0,-shape[1]/math.sqrt(3),shape[2]/math.sqrt(3),0,1]])
            y.extend([d['rs']*ia,d['rs']*ib])
        return np.asarray(x),np.asarray(y)
    def loss(logk):
        x,y=matrix(fit,math.exp(logk));coef=np.linalg.lstsq(x,y,rcond=None)[0]
        return float(np.mean((x@coef-y)**2))
    best=minimize_scalar(loss,bounds=(math.log(.002),math.log(.15)),method='bounded')
    knee=math.exp(best.x);x,y=matrix(fit,knee);coef,_,rank,singular=np.linalg.lstsq(x,y,rcond=None)
    xv,yv=matrix(val,knee);fit_error=float(np.sqrt(np.mean((x@coef-y)**2)))
    val_error=float(np.sqrt(np.mean((xv@coef-yv)**2)))
    condition=float(singular[0]/singular[-1]);g,d0,d1,d2,oa,ob=coef
    accepted=bool(best.success and rank==6 and condition<1e5 and .95<=g<=1.05 and
      min(d0,d1,d2)>=0 and max(d0,d1,d2)<=15 and max(abs(oa),abs(ob))<=2 and fit_error<.1 and val_error<.1)
    # Force the exact target float representation for the subsequent CRC.
    raw=struct.pack('<7f',g,d0,d1,d2,knee,oa,ob);values=struct.unpack('<7f',raw)
    return dict(schema='mic_ai.inverter_dc_calibration.v1',accepted=accepted,source_kind=next(iter(sources)),
      gain=values[0],drop_v=list(values[1:4]),knee_a=values[4],offset_ab_v=list(values[5:7]),
      coefficient_bytes_hex=raw.hex(),coefficient_crc32c=crc32c(raw),
      fit_rms_error_v=fit_error,validation_rms_error_v=val_error,matrix_condition=condition,
      fit_run_ids=[d['run_id'] for d in fit],validation_run_ids=[d['run_id'] for d in val],
      physical_amp_scale_qualified=False,eligible_for_foc_start=False,
      assumptions=['known cold star-equivalent Rs','bounded rational current-clamping model','nominal shunt scale'],
      not_identified=['independent absolute current scale','mechanics','magnetic saturation'])
def phasor(d,column):
    p=d['points'];basis=np.column_stack([np.ones(BINS),p[:,8],p[:,7]])
    weight=np.sqrt(p[:,0]);coef=np.linalg.lstsq(basis*weight[:,None],p[:,column]*weight,rcond=None)[0]
    return (coef[1]-1j*coef[2])/math.sqrt(2)
def impedance_capture(ac_points:list[dict],cal:dict,*,rotor_stationary_verified:bool):
    if not cal.get('accepted') or not rotor_stationary_verified:raise ValueError('validated DC calibration and verified stationary rotor required')
    result=dict(schema=SCHEMA,source_kind=cal['source_kind'],stator_resistance_ohm=ac_points[0]['rs'],
      stator_resistance_convention='balanced_star_equivalent',voltage_source='calibrated_pwm_reconstruction',
      current_scale='nominal_datasheet',rotating_field=False,rotor_stationary_verified=True,points=[])
    fit_frequencies={1,2,5,10,20,50,100,200}
    for d in ac_points:
        if d['kind']!=2 or d['source_kind']!=cal['source_kind'] or d['calibration_crc']!=cal['coefficient_crc32c']:raise ValueError('AC calibration provenance mismatch')
        ca,sa=math.cos(d['axis']),math.sin(d['axis'])
        i=ca*phasor(d,1)+sa*phasor(d,2);v=ca*phasor(d,5)+sa*phasor(d,6)
        perpendicular=-sa*phasor(d,1)+ca*phasor(d,2)
        if abs(perpendicular)>max(.005,.1*abs(i)):raise ValueError('nonstationary/cross-axis response')
        f=d['frequency_hz'];role='fit' if round(f) in fit_frequencies else 'validation'
        result['points'].append(dict(frequency_hz=f,voltage_rms_phasor_v=[v.real,v.imag],current_rms_phasor_a=[i.real,i.imag],
          role=role,run_id=f"{d['source_kind']}-ac-{d['run_id']}",coverage_pct=d['coverage_pct'],settled_cycles=5,
          samples_per_cycle=16000/f,synchronized_voltage_current=True))
    return result
