"""Read-only recorded evidence audit; no hardware/network imports or commands."""
import hashlib,importlib.util,json,math,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CAP=ROOT/'artifacts/live_bench_20261116/rpc_hmi_admission_r1/FOC_trial_r1'
OUT=ROOT/'artifacts/live_bench_20261116/observer_current_window_r1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def main():
    protected={}
    for name in ('saved_files_sha256.json','analysis_files_sha256.json'):
        for rel,h in json.loads((CAP/name).read_text(encoding='utf8')).items():
            assert sha(CAP/rel)==h,rel
            protected[(CAP/rel).relative_to(ROOT).as_posix()]=h
    trace=json.loads((CAP/'observer_trace_decoded.json').read_text(encoding='utf8'))
    spec=importlib.util.spec_from_file_location('offline_hmi',CAP.parent/'web_hmi/server.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    status=json.loads((CAP/'final_status.json').read_text(encoding='utf8'))
    adc=m.decode_adc_peak_hex(status['mc_adc_peak_hex'],2026111606)
    write(OUT/'recorded_ADC_decoded.json',adc)
    rows=[]
    for r in [trace['first_loss']]+trace['samples']:
        nis=sum(e*e/s for e,s in zip(r['innovation_A'],r['innovation_variance_A2']))
        assert math.isclose(nis,r['nis'],rel_tol=2e-6)
        assert r['control_adc_cycles']==r['observer_adc_cycles']==r['bin_cycles']
        rows.append(dict(step=r['steps'],nis=r['nis'],reference_hz=r['reference_hz'],rpm_est=r['rpm_est'],
            residual_A=r['innovation_A'],sigma_A=[math.sqrt(s) for s in r['innovation_variance_A2']],
            flux_Wb=r['flux_wb'],input_epoch_coherent=True,dt_s=r['dt_s']))
    assert all(x['accepted_by_monitor'] and x['epoch_consistent'] for x in adc['samples'])
    currents=[x['nominal_currents_a'] for x in adc['samples']]
    alpha=[x[0] for x in currents];beta=[(x[0]+2*x[1])/math.sqrt(3) for x in currents]
    clocks=[x['cycles'] for x in adc['samples']]
    stats=[]
    for axis,values in [('alpha',alpha),('beta',beta)]:
        # Short recorded window. This is scatter, NOT an identified noise PDF.
        mean=statistics.mean(values)
        stats.append(dict(axis=axis,mean_A=mean,sample_std_A=statistics.stdev(values),
            min_A=min(values),max_A=max(values),max_adjacent_change_A=max(abs(b-a) for a,b in zip(values,values[1:])),
            nonoverlapping_4point_means_A=[statistics.mean(values[i:i+4]) for i in (0,4,8)]))
    timing=json.loads((CAP/'CPU_IRQ_and_first_fault.json').read_text(encoding='utf8'))
    write(OUT/'recorded_analysis.json',dict(hardware_commands=0,thresholds_changed=False,
        protected_files_verified=len(protected),observer_rows=rows,
        ADC_window_s=((clocks[-1]-clocks[0])&0xffffffff)/170e6,ADC_scatter=stats,
        max_estimate_age_us=timing['max_result_age_us'],estimate_limit_us=2000,
        diagnostic_issue='Current was decimated16kHz->1kHz by selecting one unfiltered endpoint; recorded local scatter exceeds modeled innovation sigma',
        important_distinction='Interval-average voltage with endpoint current is mathematically legitimate; the demonstrated software improvement is filtering before current decimation, not merely making those two averages equal',
        evidence_limit='12 decimated observer rows + 12 ADC rows cannot replay4978 complete EKF steps or identify actual voltage/motor parameters/speed',
        hardware_NIS_root_cause_fully_proven=False,
        first_loss_ADC_is_later_than_observer_input=True))
    write(OUT/'protected_capture_hashes.json',protected)
    print(json.dumps(dict(verified=len(protected),ADC_scatter=stats,first_NIS=trace['first_loss']['nis'])))
if __name__=='__main__':main()
