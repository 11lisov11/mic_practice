"""Prepare a frozen Python reference for a future SimInTech engine comparison.

This script does NOT run SimInTech and must never label its results as a
SimInTech simulation or as a check of the demo block/state limits.
"""
from __future__ import annotations
import csv
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'research/mic_ai_theory/snh_pwm/source'
sys.path.insert(0,str(SOURCE))
from estimation.sensorless_flux_slip_observer import SensorlessFluxSlipConfig,SensorlessFluxSlipObserver
from tools.run_air56b2_sensorless_independent_plant_study import _make_trace,DT_S,DURATION_S,EVALUATION_START_S

OUT=Path(__file__).resolve().parent/'mvp_20261122'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metric(rows, estimate, valid):
    selected=[r for r in rows if r['evaluate']]
    errors=[abs(r[estimate]-r['omega_true_rad_s']) for r in selected]
    return {'samples':len(selected),'mean_abs_speed_error_rad_s':sum(errors)/len(errors),
            'max_abs_speed_error_rad_s':max(errors),'final_abs_speed_error_rad_s':errors[-1],
            'valid_fraction':sum(r[valid] for r in selected)/len(selected),
            'final_true_speed_rad_s':selected[-1]['omega_true_rad_s'],
            'final_estimated_speed_rad_s':selected[-1][estimate]}


def one_case(bundle,config,sample_index,load_fraction):
    trace=_make_trace(bundle,sample_index=sample_index,target_frequency_hz=5.,load_fraction=load_fraction)
    oracle=SensorlessFluxSlipObserver(config)
    reconstructed=SensorlessFluxSlipObserver(config)
    theta=0.
    phase_rms=bundle['fidelity']['derived_nameplate']['model_phase_voltage_v']
    vdc=bundle['fidelity']['f3_samples'][sample_index]['inverter']['nominal_vdc_v']
    rows=[]
    for n,(va,vb,ia,ib,omega,evaluate) in enumerate(trace):
        t=n*DT_S
        frequency=5*min(1.,t/.35)
        theta+=2*math.pi*frequency*DT_S
        amplitude=min(math.sqrt(2)*phase_rms*frequency/50,.95*vdc/math.sqrt(3))
        command_a=amplitude*math.cos(theta)
        command_b=amplitude*math.sin(theta)
        phases=[command_a,-.5*command_a+math.sqrt(3)/2*command_b,-.5*command_a-math.sqrt(3)/2*command_b]
        common=-.5*(max(phases)+min(phases))
        duty=[.5+(v+common)/vdc for v in phases]
        assert all(0<=x<=1 for x in duty)
        # What a nominal, ideal-DC-bus duty reconstruction provides. Actual
        # conduction drops remain hidden from this observer's input.
        rec_phase=[(d-.5)*vdc for d in duty]
        mean=sum(rec_phase)/3
        rec_a=rec_phase[0]-mean
        rec_b=(rec_phase[1]-rec_phase[2])/math.sqrt(3)
        assert abs(rec_a-command_a)<1e-10 and abs(rec_b-command_b)<1e-10
        ideal=oracle.step(v_alpha_v=va,v_beta_v=vb,i_s_alpha_a=ia,i_s_beta_a=ib,dt_s=DT_S).state
        real=reconstructed.step(v_alpha_v=rec_a,v_beta_v=rec_b,i_s_alpha_a=ia,i_s_beta_a=ib,dt_s=DT_S).state
        rows.append({'time_s':(n+1)*DT_S,'stator_frequency_command_hz':frequency,
                     'vdc_nominal_assumed_V':vdc,'duty_a':duty[0],'duty_b':duty[1],'duty_c':duty[2],
                     'v_alpha_applied_truth_V':va,'v_beta_applied_truth_V':vb,
                     'v_alpha_reconstructed_V':rec_a,'v_beta_reconstructed_V':rec_b,
                     'i_alpha_measured_A':ia,'i_beta_measured_A':ib,
                     'omega_true_rad_s':omega,'omega_oracle_voltage_rad_s':ideal.omega_m_rad_s,
                     'oracle_valid':int(ideal.valid),'omega_reconstructed_voltage_rad_s':real.omega_m_rad_s,
                     'reconstructed_valid':int(real.valid),'evaluate':int(evaluate)})
    name=f'prior_{sample_index}_load_{load_fraction:g}'
    with (OUT/f'{name}.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    return {'case':name,'sample_index':sample_index,'load_fraction_rated_torque':load_fraction,
            'rows':len(rows),'source':'existing_independent_Python_RK4_plant',
            'ideal_applied_voltage_diagnostic':metric(rows,'omega_oracle_voltage_rad_s','oracle_valid'),
            'nominal_duty_voltage_reconstruction':metric(rows,'omega_reconstructed_voltage_rad_s','reconstructed_valid'),
            'max_measured_current_vector_A':max(math.hypot(r['i_alpha_measured_A'],r['i_beta_measured_A']) for r in rows)},rows


def main():
    OUT.mkdir(exist_ok=True)
    bundle_path=ROOT/'artifacts/air56b2_fidelity_bundle.json'
    study_path=ROOT/'artifacts/air56b2_sensorless_independent_plant_study.json'
    bundle=json.loads(bundle_path.read_text(encoding='utf-8'))
    study=json.loads(study_path.read_text(encoding='utf-8'))
    config=SensorlessFluxSlipConfig(**study['selected']['config'])
    profiles={str(i):{'motor_prior':bundle['fidelity']['f2_samples'][i],
                      'inverter_measurement_prior':bundle['fidelity']['f3_samples'][i]} for i in [128,11]}
    params={'status':'PREPARED_FOR_ENGINE_COMPARISON_NOT_SIMINTECH_EXECUTED',
            'motor':'IEK AIR56B2','nameplate':bundle['fidelity']['nameplate'],
            'derived_nameplate':bundle['fidelity']['derived_nameplate'],
            'profiles':profiles,'observer':asdict(config),
            'observer_parameters_frozen_before_5Hz_run':True,'parameters_measured':False,
            'experiment':{'stator_frequency_hz':5,'dt_s':DT_S,'duration_s':DURATION_S,
                          'frequency_ramp_s':.35,'load_step_time_s':.55,'evaluate_from_command_time_s':EVALUATION_START_S},
            'inverter_model':'averaged voltage vector with conduction drop; no switched gates or dead-time in this reference',
            'measurement_model':'existing source current delay and quantization; nominal Vdc known exactly in duty reconstruction',
            'not_claimed':['SimInTech numerical result','actual block or ODE count','demo license success','hardware qualification','full switching loss or core-loss model'],
            'sources':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in [bundle_path,study_path,
                SOURCE/'estimation/sensorless_flux_slip_observer.py',SOURCE/'models/induction_motor_current_flux_rk4.py',
                SOURCE/'tools/run_air56b2_sensorless_independent_plant_study.py']}}
    (OUT/'frozen_profile.json').write_text(json.dumps(params,ensure_ascii=False,indent=2),encoding='utf-8')
    results=[]; all_rows=[]
    for i,load in [(128,0.),(128,.35),(11,.35)]:
        result,rows=one_case(bundle,config,i,load)
        results.append(result);all_rows.append(rows)
    old=next(r for r in study['low_speed_diagnostic']['rows'] if r['sample_index']==11)
    old_err=old['mean_abs_speed_error_rad_s']
    replay_err=results[2]['ideal_applied_voltage_diagnostic']['mean_abs_speed_error_rad_s']
    replay_delta=abs(replay_err-old_err)
    output={'status':'PYTHON_REFERENCE_ONLY','SimInTech_installation_status':'not_checked_by_this_reference_script','SimInTech_run_executed':False,
            'SimInTech_block_count':None,'SimInTech_ODE_count':None,'frequency_hz':5,
            'replay_check':{'historical_mean_error_rad_s':old_err,'replayed_mean_error_rad_s':replay_err,
                            'absolute_difference_rad_s':replay_delta,'matches_at_1e_9':replay_delta<1e-9},
            'cases':results,'hardware_actions':0}
    (OUT/'reference_results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(3,1,figsize=(10,8),layout='constrained')
    for ax,result,rows in zip(axs,results,all_rows):
        times=[r['time_s'] for r in rows]
        for key,label in [('omega_true_rad_s','Plant truth'),('omega_oracle_voltage_rad_s','Observer: exact applied voltage'),
                          ('omega_reconstructed_voltage_rad_s','Observer: nominal duty reconstruction')]:
            ax.plot(times,[r[key] for r in rows],label=label,lw=1.2)
        ax.axvline(.55,color='grey',ls=':',lw=.8)
        ax.set(title=result['case'],xlabel='Time, s',ylabel='Mechanical speed, rad/s')
        ax.legend(fontsize=7)
    fig.suptitle('Python reference ONLY - 5 Hz diagnostic - not a SimInTech run')
    fig.savefig(OUT/'python_reference_5Hz.png',dpi=160)
    plt.close(fig)
    print(json.dumps(output,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
