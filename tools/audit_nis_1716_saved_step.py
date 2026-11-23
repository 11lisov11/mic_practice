"""Independent, offline audit of the physical1716 first-NIS capture.

No hardware/network APIs. Existing records are never rewritten. Counterfactual
sensitivities discriminate hypotheses; they are NOT calibrated corrections.
"""
import json
from pathlib import Path
import numpy as np
from check_observer_equations_offline import f, rk4, jacobian
from replay_observer_pair_noise import replay_pair_record, sha

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261117/observer_pair_noise_r1'
CAP=BASE/'FOC_5Hz_r2'
OUT=ROOT/'artifacts/live_bench_20261118/nis_input_window_r1'


def evaluate(d, *, voltage_delta=(0.,0.), dt_delta=0., variational=False,
             motor_override=None):
    md=d['motor']|dict(motor_override or {})
    motor=[md[k] for k in ('rs','rr','ls','lr','lm','j','b','poles')]
    x=np.array(d['prior_state']); P=np.array(d['prior_covariance'])
    inp=d['inputs'];dt=inp['dt_s']+dt_delta
    v=np.array([inp['va_V'],inp['vb_V']])+voltage_delta
    y=np.array([inp['ia_A'],inp['ib_A']]);R=np.array(d['measurement_noise_A2'])
    predicted=rk4(motor,x,v,dt)
    A=jacobian(lambda z:f(motor,z,v),x)
    F=(jacobian(lambda z:rk4(motor,z,v,dt),x) if variational
       else np.eye(6)+dt*A+.5*dt*dt*A@A)
    covariance=F@P@F.T+np.diag([.02,.02,.00001,.00001,4,.0001])*dt
    S=covariance[:2,:2]+R;e=y-predicted[:2]
    K=np.linalg.solve(S,covariance[:2,:]).T
    H=np.zeros((2,6));H[:,:2]=np.eye(2);I=np.eye(6)-K@H
    posterior=predicted+K@e;postP=I@covariance@I.T+K@R@K.T
    legacyS=covariance[:2,:2]+np.eye(2)*.0004
    return dict(NIS=float(e@np.linalg.solve(S,e)),predicted=predicted.tolist(),
        residual_A=e.tolist(),S_A2=S.tolist(),post_x=posterior.tolist(),
        post_P=postP.tolist(),minimum_P_eigenvalue=float(np.linalg.eigvalsh(postP).min()),
        original_fixed_R_watchdog_NIS=float(e@np.linalg.solve(legacyS,e)))


def main():
    OUT.mkdir(parents=True,exist_ok=False)
    protected={}
    for folder in (BASE,CAP):
        inventories=('source_hashes.json','release/sha256.json') if folder==BASE else (
            'saved_files_sha256.json','analysis_files_sha256.json','operator_confirmation_sha256.json')
        for inv in inventories:
            for rel,h in json.loads((folder/inv).read_text(encoding='utf-8-sig')).items():
                path=(BASE/'release'/rel) if inv=='release/sha256.json' else folder/rel
                assert sha(path)==h,str(path)
                protected[path.relative_to(ROOT).as_posix()]=h
    trace=json.loads((CAP/'observer_trace_decoded.json').read_text(encoding='utf-8'))
    d=trace['first_nis_replay'];calc=evaluate(d)
    elf=BASE/'release/nucleo_2026111716_pair_noise.elf'
    arm=replay_pair_record((CAP/'observer_trace.bin').read_bytes(),elf,2026111716)
    assert arm['passed'] and arm['bit_exact']
    assert abs(calc['NIS']-d['nis'])<1e-4
    np.testing.assert_allclose(calc['post_x'],d['post_state'],rtol=2e-5,atol=1e-6)
    np.testing.assert_allclose(calc['post_P'],d['post_covariance'],rtol=3e-4,atol=1e-7)
    assert calc['minimum_P_eigenvalue']>0
    sensitivity={
        'RK4_variational_covariance':evaluate(d,variational=True),
        'dt_minus10us':evaluate(d,dt_delta=-1e-5),
        'dt_plus10us':evaluate(d,dt_delta=1e-5),
        'voltage_alpha_plus0_5V':evaluate(d,voltage_delta=(.5,0)),
        'voltage_alpha_minus0_5V':evaluate(d,voltage_delta=(-.5,0)),
        'voltage_beta_plus0_5V':evaluate(d,voltage_delta=(0,.5)),
        'Rs_plus20percent':evaluate(d,motor_override={'rs':d['motor']['rs']*1.2}),
        'Rs_minus20percent':evaluate(d,motor_override={'rs':d['motor']['rs']*.8})}
    status=json.loads((CAP/'final_status.json').read_text(encoding='utf-8'))
    first=trace['first_loss'];rows=status['mc_adc_peak']['samples']
    delays=[((r['cycles']-first['observer_adc_cycles'])&0xffffffff)/170 for r in rows]
    report=dict(hardware_commands=0,installed_sources_changed=False,
        exact_ARM_replay=arm,independent_double=calc,sensitivities=sensitivity,
        mean_window={'first_cycles':first['window_first_cycles'],
            'center_cycles':first['observation_cycles'],'end_cycles':first['observer_adc_cycles'],
            'pair_counts':d['pair_counts']},raw_ADC_rows_after_endpoint_us=delays,
        raw_ADC_contains_source16=False,
        proven_defect='ADC ring12 plus post6 cannot preserve source16 when the observer requests capture after computing NIS',
        second_defect='Capture request is gated by first validity-loss kind; an earlier non-NIS loss can suppress the first-NIS raw request',
        physical_motor_or_voltage_error_uniquely_identified=False,
        Q_R_and_NIS_limits_changed=False,protection_limits_changed=False,
        no_counterfactual_is_labelled_physical_fix=True)
    assert min(delays)>0
    (OUT/'saved_step_audit.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (OUT/'protected_inputs_sha256.json').write_text(json.dumps(protected,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(ARM_exact=True,NIS_double=calc['NIS'],
        sensitivity_NIS={k:v['NIS'] for k,v in sensitivity.items()},protected_files=len(protected))))


if __name__=='__main__':main()
