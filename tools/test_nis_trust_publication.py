"""PC-only actual native adapter regression on preserved1802 first-NIS prior."""
import json,subprocess
from pathlib import Path
import prepare_exact_nis_input_release as p
from test_foc_estimate_publish_fix import native_source
from test_observer_current_window import compile_case

OUT=p.ROOT/'artifacts/live_bench_20261118/nis_exact_source_analysis_r1'


def main():
    out=OUT/'verification_r2';out.mkdir(exist_ok=False)
    fixture=p.read(p.OUT/'verification/adapter/exact_native_adapter.cpp')
    pre=fixture.split('#define MIC_NATIVE_BUILD',1)[0].replace('static bool inject_torn;','')
    pre+='''\nstatic int fixture_observe(ma_observer*,const ma_motor*,const float*,const ma_noise*);
static bool force_nis=false;static float forced_nis;
'''
    decoded=json.loads(p.read(p.OUT/'FOC_5Hz_r2/observer_trace_decoded.json'))
    d=decoded['first_nis_replay'];first=decoded['first_loss'];f=lambda x:repr(float(x))+'f'
    previous=(first['observation_cycles']-round(d['inputs']['dt_s']*170000000))&0xffffffff
    seed=f'''
static void seed(unsigned steps=658U){{
 timer.BDTR=1;fake_bus=321;selected=MA_FOC;qualification=FE_ESTIMATED;
 profile_ready=1;running=1;run_fault=first_fault=0;fe_complete=1;fe_started=1;
 fe_case=64;fe_fault=0;fe_trial_done=0;id_profile_attempted=1;id_profile_running=0;
 cycle.CYCCNT={first['observer_adc_cycles']+10000}U;telemetry_seq=0;
 start_cycles=fe_trial_begin=cycle.CYCCNT-1700000U;
 ma_estimate_reset({previous}U);observer_center_cycles={previous}U;
 memset(&observer,0,sizeof(observer));
 const float x[6]={{{','.join(f(v) for v in d['prior_state'])}}};
 const float P[36]={{{','.join(f(v) for row in d['prior_covariance'] for v in row)}}};
 memcpy(observer.x,x,sizeof(x));memcpy(observer.p,P,sizeof(P));
 observer.steps=steps;observer.rejected=0;
 bin_current={{}};bin_current.valid=bin_current.zero=1;
 bin_current.cycles={first['observer_adc_cycles']}U;bin_current.sequence=42;
 bin_current.pair=2;bin_current.arr=5312;bin_current.bus_v=321;
 bin_current.ccr[0]=2908;bin_current.ccr[1]=2723;bin_current.ccr[2]=2404;
 bin_cycles=bin_current.cycles;bin_control_sequence=42;bin_control_adc_cycles=bin_cycles;
 bin_window={{}};bin_window.first={first['window_first_cycles']}U;
 bin_window.center={first['observation_cycles']}U;bin_window.end=bin_cycles;
 bin_window.previous_center={previous}U;bin_window.count=16;bin_window.pair_counts=16U<<10;
 bin_window.ia={f(d['inputs']['ia_A'])};bin_window.ib={f(d['inputs']['ib_A'])};
 bin_va=bin_window.va=bin_window.tail_va={f(d['inputs']['va_V'])};
 bin_vb=bin_window.vb=bin_window.tail_vb={f(d['inputs']['vb_V'])};
 memset(&observer_trace,0,sizeof(observer_trace));observer_trace.seen_valid=1;
 memset(&ma_perf,0,sizeof(ma_perf));memset(&ma_first_runtime,0,sizeof(ma_first_runtime));
 memset(&mic_foc_irq_meter,0,sizeof(mic_foc_irq_meter));
 ma_perf_off=0;sample=bin_current;sample_coherent=1;
 request_calls=0;force_nis=false;
}}
'''
    body=r'''
static void NVIC_SetPendingIRQ(int irq){assert(irq==25);++kicks;ma_native_profile_tick();}
static int fixture_observe(ma_observer*o,const ma_motor*m,const float*v,const ma_noise*n){
 int rc=mic_observer_step(o,m,v,n);if(force_nis)o->nis=forced_nis;return rc;
}
SEED
int main(){
 unsigned checks=0;
 // Real64-case adapter qualification with a fake cycle source; not target timing.
 selected=MA_FOC;sample.zero=sample.valid=1;fake_bus=0;
 for(unsigned i=0;i<2000U&&!fe_complete&&!fe_fault;++i)ma_native_service();
 assert(fe_complete&&fe_case==64U&&!fe_fault);++checks;
 assert(FE_FAST_BUDGET==4000U&&FE_OBSERVER_BUDGET==85000U);++checks;
 seed();uint32_t old=estimate_cycles;ma_native_service();
 const float physical_nis=observer.nis;
 assert(fabsf(physical_nis-29.30712509f)<.0001f);++checks;
 assert(observer_trace.replay_latched&&observer.steps==659U);++checks;
 assert(request_calls==1&&request_first==bin_window.first&&request_end==bin_window.end&&request_step==659U);++checks;
 assert(observer_trace.blob.header.first_loss_present&&observer_trace.blob.header.first_loss_step==659U);++checks;
 #ifdef CANDIDATE
 assert(run_fault==MA_OBSERVER&&estimate_cycles==old);++checks;
 assert(observer_trace.blob.first_loss.published==0&&observer_trace.blob.first_loss.observer_fault==MA_OBSERVER);++checks;
 assert(ma_first_runtime.word[0]==FT_OBSERVER&&ma_first_runtime.word[1]==MA_OBSERVER);++checks;
 assert(ma_native_fast(1.f)==MC_SW_ERROR);++checks;
 #else
 assert(!run_fault&&estimate_cycles==bin_cycles);++checks;
 assert(observer_trace.blob.first_loss.published==1);++checks;
 #endif
 auto frozen=observer_trace.blob.replay;ma_native_service();
 assert(!memcmp(&frozen,&observer_trace.blob.replay,sizeof(frozen))&&request_calls==1);++checks;
 // Synthetic policy boundaries remain separate from the physical record above.
 for(float nis:{24.999f,25.f,25.001f,50.f,51.f,NAN}){
  seed();force_nis=true;forced_nis=nis;old=estimate_cycles;ma_native_service();
  #ifdef CANDIDATE
  if(!(nis<25.f))assert(run_fault==MA_OBSERVER&&estimate_cycles==old);
  else assert(!run_fault&&estimate_cycles==bin_cycles);
  #else
  assert(!run_fault&&estimate_cycles==bin_cycles);
  #endif
  ++checks;
 }
 seed(498);force_nis=true;forced_nis=29;ma_native_service();
 assert(observer.steps==499&&!run_fault&&estimate_cycles==bin_cycles);++checks;
 seed();observer.rejected=19;bin_window.ib+=.3f;ma_native_service();
 assert(observer.nis>50&&run_fault==MA_OBSERVER);++checks; // Old20-step stop retained.
 seed();sample.counts[0]=150;sample.counts[1]=-75;sample.counts[2]=-75;
 assert(ma_native_fast(1.f)!=MC_NO_ERROR&&run_fault==MA_CURRENT);++checks;
 seed();ma_estimate_reset(cycle.CYCCNT-340001U);
 assert(ma_native_fast(1.f)!=MC_NO_ERROR&&run_fault==MA_STALE);++checks;
 (void)old;
 printf("{\"passed\":true,\"checks\":%u,\"OFF_cases\":64,\"physical_NIS_unchanged\":%.9g,\"fake_cycles_not_target_timing\":true}\n",checks,physical_nis);
}
'''.replace('SEED',seed)
    results={}
    for label,path in [('baseline',p.OUT),('candidate',OUT/'candidate')]:
        native=native_source(path,hook=False)
        call='int fault=mic_observer_step(&observer,&model,input,&noise);'
        assert call in native;native=native.replace(call,'int fault=fixture_observe(&observer,&model,input,&noise);')
        code=('#define CANDIDATE\n' if label=='candidate' else '')+pre+native+'\n'+body
        exe=compile_case(out,label,code,p.OUT)
        run=subprocess.run([str(exe)],capture_output=True,text=True)
        p.write(out/(label+'_run.log'),run.stdout+run.stderr);run.check_returncode()
        results[label]=json.loads(run.stdout)
    report=dict(passed=True,hardware_commands=0,results=results,
        physical_NIS_not_artificially_reduced=True,candidate_stops_untrusted_publication=True,
        raw_capture_before_stop_preserved=True,thresholds_unchanged=True,
        actual_target_CPU_not_measured=True)
    p.write(out/'native_report.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
