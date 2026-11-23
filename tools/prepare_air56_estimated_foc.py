"""Calculate a stopped experimental FOC profile from AIR56B2 ratings.

No motor measurements, board traffic, START, CLEAR, firmware or gate changes.
The already measured terminal DC resistance is used; unknowns remain estimates.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'research/mic_ai_theory/snh_pwm/source'))
from config.env import MotorParams
from models.air56b2_nameplate_ensemble import (
    Air56B2Nameplate, derive_nameplate, evaluate_equivalent_circuit,
)

PACKAGE = ROOT / 'artifacts/live_bench_20261029/adc_noise_rpc_fix_r1'
REFERENCE = ROOT / 'artifacts/live_bench_20261029/foc_recorded_noise_review_r3'


def estimate(loss_w=12., split=.5, inertia=.0002):
    nameplate = Air56B2Nameplate()
    d = derive_nameplate(nameplate)

    def build(logs):
        rr, lm, rc, leakage = map(float, np.exp(logs))
        m = MotorParams(Rs=(24.7-.24)/2, Rr=rr, Lm=lm,
                        Ls_sigma=leakage*split, Lr_sigma=leakage*(1-split),
                        J=inertia, B=loss_w/d.rated_omega_rad_s**2,
                        p=1, I_n=1.24)
        return m, rc

    def residual(logs):
        m, rc = build(logs)
        p = evaluate_equivalent_circuit(m, core_resistance_ohm=rc,
            rotational_loss_w=loss_w, nameplate=nameplate, derived=d)
        return [p.line_current_a/1.24-1, p.power_factor/.78-1,
                p.output_power_w/250-1, p.max_torque_ratio/2.2-1]

    fit = least_squares(residual, np.log([11., .5, 1500., .065]),
                        bounds=(np.log([1., .05, 30., .002]),
                                np.log([60., 3., 100000., .3])),
                        max_nfev=1000, ftol=1e-12, xtol=1e-12, gtol=1e-12)
    if not fit.success or max(map(abs, residual(fit.x))) > .01:
        raise RuntimeError('Nameplate operating-point fit did not converge')
    m, rc = build(fit.x)
    prediction = evaluate_equivalent_circuit(m, core_resistance_ohm=rc,
        rotational_loss_w=loss_w, nameplate=nameplate, derived=d)
    # Initial no-load experiment uses reduced flux/current. These do not
    # increase the existing1.35A raw trip or any bus/SD/temperature protection.
    controller = dict(rs=m.Rs, rr=m.Rr, ls=m.Lm+m.Ls_sigma,
        lr=m.Lm+m.Lr_sigma, lm=m.Lm, j=m.J, b=m.B, poles=1,
        flux=.25, current_limit=.8, trip_current=1.35,
        current_bw=400., speed_bw=12.)
    return dict(motor=controller, circuit=asdict(m),
                core_resistance_ohm=rc, prediction=asdict(prediction),
                assumptions=dict(rotational_loss_w=loss_w, leakage_split=split,
                                 inertia_kg_m2=inertia), fit_residuals=residual(fit.x))


def cpp_motor(m):
    fields=('rs','rr','ls','lr','lm','j','b','poles','flux',
            'current_limit','trip_current','current_bw','speed_bw')
    return '{'+','.join(str(int(m[k])) if k=='poles' else format(m[k], '.12g')+'f'
                       if '.' in format(m[k], '.12g') or 'e' in format(m[k], '.12g')
                       else format(m[k], '.12g')+'.f' for k in fields)+'}'


def main():
    global PACKAGE
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir', type=Path, required=True)
    p.add_argument('--controller-package',type=Path)
    args=p.parse_args()
    if args.controller_package:PACKAGE=args.controller_package.resolve()
    out=args.outdir.resolve();out.mkdir(parents=True, exist_ok=False)
    central=estimate();m=central['motor']
    # Profile explicitly carries calculated provenance. It must never acquire
    # an 'identified_physical_motor' label or forged measurement evidence.
    profile=dict(schema='mic_ai.multi_algorithm.motor_profile.v1',
        purpose='nameplate_estimated_motor_experimental',
        source_kind='catalog_fit_plus_existing_DC_resistance',
        motor=m, nominal=asdict(Air56B2Nameplate()), estimate=central,
        physical_parameters_measured=False, installed=False,
        intended_experiment=dict(mode='FOC', target_hz=5, max_duration_s=5,
                                 acceleration_hz_s=5, load='none', flux_wb=.25),
        protection_thresholds_increased=False,
        limitations=[
            'Calculated model is not a unique measurement of motor parameters.',
            'Nominal current, power factor, output power and maximum torque are fit constraints; starting ratios remain independent residuals.',
            'Single-cage model does not reproduce all catalog starting characteristics; no direct-on-line start is modeled as a validated result.',
            'J, loss split and individual leakage split are explicit priors.',
            'Core-loss resistor is used in the ratings fit; firmware dynamic model omits explicit core loss.',
            'Existing firmware physical-profile gate and target timing are not modified by this offline tool.',
        ])
    (out/'profile.json').write_text(json.dumps(profile, indent=2)+'\n', encoding='utf-8')
    variants=[dict(label='central', motor=m)]
    for label, loss, split, j in [('low_losses',6.,.5,.0002),
        ('high_losses',20.,.5,.0002),('leak_split35',12.,.35,.0002),
        ('leak_split65',12.,.65,.0002),('small_inertia',12.,.5,.00007),
        ('large_inertia',12.,.5,.0004)]:
        variants.append(dict(label=label, motor=estimate(loss,split,j)['motor']))
    for name, factor in [('rs',.7),('rs',1.4),('rr',.6),('rr',1.4),
                         ('lm',.7),('lm',1.3),('leakage',.5),('leakage',1.5)]:
        v=dict(m)
        if name=='lm':
            lls=v['ls']-v['lm'];llr=v['lr']-v['lm']
            v['lm']*=factor;v['ls']=v['lm']+lls;v['lr']=v['lm']+llr
        elif name=='leakage':
            v['ls']=v['lm']+(v['ls']-v['lm'])*factor
            v['lr']=v['lm']+(v['lr']-v['lm'])*factor
        else:v[name]*=factor
        variants.append(dict(label=f'{name}_factor{factor}', motor=v))
    (out/'uncertainty_cases.json').write_text(json.dumps(variants,indent=2)+'\n', encoding='utf-8')
    source=ROOT/'tools/multi_algorithm/recorded_noise_test.cpp'
    code=source.read_text(encoding='utf-8').rsplit('int main() {',1)[0]
    code=code.replace('static constexpr double amp_per_count=',
        'static ma_motor configured_controller,configured_plant;\nstatic constexpr double amp_per_count=')
    old='ma_motor m=prior();Plant plant;plant.m=m;'
    assert code.count(old)==1
    code=code.replace(old,'ma_motor m=configured_controller;Plant plant;plant.m=configured_plant;')
    # Native receives the ramped VF reference, not an instantaneous5Hz step.
    # Ramp only the experimental command; never filter current/trip samples.
    old_ref='trajectory==1?5.f:trajectory==2?'
    assert code.count(old_ref)==1
    code=code.replace(old_ref,'trajectory==1?(float)std::min(5.,5*time):trajectory==2?')
    commandmain=['int main(){properties();int bad=0;',
                 'configured_controller='+cpp_motor(m)+';',
                 'assert(ma_motor_valid(&configured_controller));']
    case_order=[]
    for index, variant in enumerate(variants):
        commandmain.append('configured_plant='+cpp_motor(variant['motor'])+';')
        for algo in (2,3):
            for trajectory in (1,2):
                case_order.append(dict(variant=index,label=variant['label'],
                                       algorithm=algo,trajectory=trajectory))
                commandmain.append(f'bad+=stress({algo},0,1,73,1,-1,{trajectory});')
    commandmain.append('return bad?1:0;}')
    generated=out/'estimated_model.cpp'
    generated.write_text(code+'\n'+'\n'.join(commandmain)+'\n',encoding='utf-8')
    shutil.copyfile(REFERENCE/'recorded_noise_data.h',out/'recorded_noise_data.h')
    exe=out/'model.exe'
    cmd=[shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',
         '-Wno-misleading-indentation','-I',str(PACKAGE/'nucleo/Inc'),
         '-I',str(ROOT/'tools/multi_algorithm'),'-I',str(out),str(generated),'-o',str(exe)]
    build=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
    (out/'build.log').write_text(build.stdout+build.stderr,encoding='utf-8');build.check_returncode()
    result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=120)
    (out/'run.jsonl').write_text(result.stdout,encoding='utf-8')
    (out/'run.log').write_text(result.stderr,encoding='utf-8')
    if result.returncode not in (0,1):result.check_returncode()
    rows=[json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert len(rows)==len(case_order)==60
    for row,meta in zip(rows,case_order):row.update(meta)
    report=dict(study_completed=True,all_scenarios_passed=result.returncode==0,
        hardware_commands=0,start_commands=0,clear_commands=0,firmware_changed=False,
        protection_thresholds_increased=False,profile=m,variants=variants,scenarios=rows,
        profile_sha256=hashlib.sha256((out/'profile.json').read_bytes()).hexdigest(),
        actual_c_kernel_sha256=hashlib.sha256((PACKAGE/'nucleo/Inc/motor_control.h').read_bytes()).hexdigest(),
        source_noise_captures=json.loads((REFERENCE/'report.json').read_text())['captures'],
        fixed_controller_under_plant_uncertainty=True, estimated_parameters_are_not_measurements=True,
        trajectories={'1':'0to5Hz at5Hz/s, then4s hold;5s total',
                      '2':'0to50Hz at5Hz/s, then4s hold;14s total'},
        note='Same original noise-transfer limitations as foc_recorded_noise_review_r3; simulation is not target timing or hardware qualification.')
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(profile=m,cases=len(rows),passed=sum(r['passed'] for r in rows),
                          failed=sum(not r['passed'] for r in rows),hardware_commands=0)))


if __name__=='__main__':main()
