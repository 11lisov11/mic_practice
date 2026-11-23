"""Prepare the official MCSDK LSO example with the existing AIR56B2 profile."""

import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

import install_foc_handover_feedback_release as previous
import run_foc_handover_feedback_trial as archives
from prepare_air56_lso_profile import set_ioc


NAME = 'ACIM-AIR56B2-LSO_FOC'
ROOT = previous.ROOT
ST = previous.OUT.parent/'st_lso_reference_PC_only_r3'
OUT = previous.OUT.parent/'air56_st_lso_reference_r1'
WORKBENCH = Path('C:/Program Files (x86)/STMicroelectronics/MC_SDK_6.4.2/Utilities/PC_Software/STMCWB')
ST_EXAMPLE = WORKBENCH/'assets/examples/ACIM-NUCLEOG431RB-IPM15B-LSO_FOC.ioc'


def vendor_values(motor, board, frequency, current_bw, speed_bw):
    """Run the motor and automatic PI conversions from installed ST Workbench."""
    source_path = next(p for p in (WORKBENCH/'assets/www/static/js_css').glob('index-*.js')
                       if 'const S1n=' in p.read_text(encoding='utf8'))
    source = source_path.read_text(encoding='utf8')
    motor_start = source.index('const S1n=')
    pi_start = source.index('const ew=e=>')
    selected = [source[start:source.index(';globalThis.', start)]+';'
                for start in (motor_start,pi_start)]
    stubs = r"""
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const hT=(e,t)=>t.motor;
const Xo=e=>(name,prefix=false)=>prefix?'M1_'+name:name;
const me=(fallback,value)=>value??fallback;
const Icn=e=>e*Math.sqrt(2);
const Acn=(e,t)=>65536*e*Math.sqrt(2)*t.rsh*t.oagain/t.vdd;
const $e=(value,places=0)=>Number(value.toFixed(places));
const wl=$e;
const Wr=value=>typeof value==='number'&&Number.isFinite(value);
const En=value=>value===undefined;
const Xc=(fn,count)=>Array.from({length:count},(_,index)=>fn(index));
"""
    compute = r"""
const {motor:m,board:b,frequency:f,current_bw:cbw,speed_bw:sbw}=input;
const motorValues=S1n(0,{motor:m,originalIOC:{MotorControl:b}});
const data={llr:m.Llr,lls:m.Lls,lms:m.Lms,rr:m.Rr,rs:m.Rs,Im:m.Im,
    polesPairs:m.polesPairs,bw:300,curr_bw:cbw,rsh:+b.M1_RSHUNT,
    oagain:+b.M1_AMPLIFICATION_GAIN,vdd:+b.ADC_REFERENCE_VOLTAGE,DCbus:325,
    pwmFreq:f,speedFreq:500};
process.stdout.write(JSON.stringify({motorValues,currentPI:T1n(E1n(data),data),
    speedPI:w1n(_1n(m.inertia,m.friction,sbw),data),lsoPI:A1n(data)}));
"""
    data = dict(motor=motor,board=board,frequency=frequency,current_bw=current_bw,speed_bw=speed_bw)
    run = subprocess.run(['node','-e',stubs+'\n'.join(selected)+compute],input=json.dumps(data),
                         text=True,capture_output=True,check=True,timeout=20)
    return json.loads(run.stdout),source_path


def prepare(out):
    root,protected = archives.verify_release()
    run = previous.OUT/'FOC_5Hz_handover_r1'
    for folder,name in ((run,'saved_files_sha256.json'),(run.with_name(run.name+'_analysis'),'sha256.json')):
        seal = previous.read_json(folder/name)
        previous.release.base.verify_inventory(seal,folder)
        protected.update({(folder/file).relative_to(root).as_posix():value for file,value in seal.items()})
    catalog_path = ROOT/'docs/mcsdk_acim_motor_profile.iek_air56b2_catalog_operator_confirmed_vf_candidate.json'
    profile = previous.read_json(catalog_path)
    model_path = previous.OUT/'nucleo/Inc/foc_experiment.h'
    initializer = re.search(r'^#define FE_ESTIMATED_MOTOR \{([^}]+)\}',previous.read(model_path),re.M)
    assert initializer
    rs,rr,ls,lr,lm,j,b,poles,flux,current,trip,current_bw,speed_bw = (
        float(value.strip().removesuffix('f')) for value in initializer[1].split(','))
    assert poles==profile['pole_pairs'] and ls>lm>0 and lr>lm and current<trip
    motor = dict(polesPairs=int(poles), Rr=rr, Rs=rs, Lls=ls-lm, Llr=lr-lm, Lms=lm/1.5,
                 In=profile['rated_current_a'], Im=flux/lm/math.sqrt(2),
                 Vn=profile['controller_equivalent_phase_voltage_v'],Fn=profile['rated_frequency_hz'],
                 maxSpeed=profile['rated_speed_rpm'], inertia=1e6*j, friction=1e6*b,
                 label='IEK_AIR56B2_D_CALCULATED',description='AIR56B2 provisional 2202 parameters')
    reference = previous.read(ST/f'ACIM-NUCLEOG431RB-IPM15B-LSO_FOC.ioc')
    settings = dict(line.split('=',1) for line in reference.splitlines() if '=' in line)
    assert settings['MotorControl.ACIM_CONFIG']=='LSO_FOC'
    board = {name:settings['MotorControl.'+name]
             for name in ('M1_RSHUNT','M1_AMPLIFICATION_GAIN','ADC_REFERENCE_VOLTAGE')}
    assert tuple(map(float,board.values()))==(0.04,2.1,3.3)
    vendor, js = vendor_values(motor,board,16000,current_bw,speed_bw)
    values = dict(vendor['motorValues'])
    scale = 65536*.04*2.1/3.3
    default_id = values['ACIM_DEFAULT_FLUX_COMPONENT']
    limit_counts = math.floor(current*scale)
    assert 0<default_id<limit_counts
    values.update(ACIM_IQMAX=math.isqrt(limit_counts**2-default_id**2),
                  ACIM_MAX_APPLICATION_SPEED=300,M1_MAX_APPLICATION_SPEED=300,
                  ACIM_DEFAULT_TARGET_SPEED_RPM=0,M1_DEFAULT_TARGET_SPEED_RPM=0,
                  CURRENT_CTRL_BANDWIDTH=current_bw,SPEED_CTRL_BANDWIDTH=speed_bw,
                  M1_NOMINAL_BUS_VOLTAGE_V=325,
                  LSO_KP=vendor['lsoPI']['Kp'],LSO_KI=vendor['lsoPI']['Ki'],
                  FLUX_K=motor['Vn']/motor['Fn']*math.sqrt(2)/(2*math.pi),
                  M1_OV_VOLTAGE_THRESHOLD_V=350,M1_UD_VOLTAGE_THRESHOLD_V=250,
                  M1_OCP_BKIN_FILTER=9)
    for name,group,loop,div in (('TORQUE','currentPI','Iq','T'),('FLUX','currentPI','Id','F'),
                                ('SPEED','speedPI',None,'ACIM_SP')):
        pi = vendor[group] if loop is None else vendor[group][loop]
        for suffix,key in (('KP','Kp'),('KI','Ki')):
            parameter = pi[key]
            assert 0<parameter['num']<32767 and parameter['den']>0
            values[f'ACIM_PID_{name}_{suffix}_DEFAULT']=parameter['num']
            values[f'{div}_{suffix}DIV']=parameter['den']
    # The export contains Workbench-only metadata as well as CubeMX keys.
    # Keep the stock key set and adapt all motor/model fields in the project.
    text = reference
    for key,value in values.items():
        if 'MotorControl.'+key in settings:
            text=set_ioc(text,'MotorControl.'+key,value)
    for key,value in {'ProjectManager.ProjectName':NAME,
                      'ProjectManager.ProjectFileName':NAME+'.ioc',
                      'ProjectManager.AskForMigrate':'false'}.items():
        text=set_ioc(text,key,value)
    out.mkdir()
    (out/(NAME+'.ioc')).write_text(text,encoding='utf-8')
    previous.save(out/'AIR56B2_profile.json',dict(
        reference_board='NUCLEO-G431RB + IHM09M2 + STEVAL-IPM15B',
        stock_source_sha256=previous.sha(ST_EXAMPLE),motor=motor,profile='estimated, source 2202 except catalog ratings',
        catalog_sha256=previous.sha(catalog_path),model_sha256=previous.sha(model_path),
        vendor_calculator_sha256=hashlib.sha256(js.read_bytes()).hexdigest(),vendor=vendor,applied=values,
        raw_trip_A=trip,reference_limit_A_peak=current,reference_limit_counts=limit_counts,
        raw_trip_counts=math.floor(trip*scale),software_bus_range_V=[250,350],
        limits=dict(fast_cycles=4000,adc_age_us=2000,run_limit_ms=5000),
        installed=False,hardware_commands=0))
    previous.save(out/'preserved_inputs_sha256.json',protected)
    print(out)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUT)
    prepare(parser.parse_args().output.resolve())
