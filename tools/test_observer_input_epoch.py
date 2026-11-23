"""Actual native adapter interleavings and unchanged protections, offline only."""
import importlib.util
import inspect
import json
import subprocess
import sys
import prepare_observer_input_epoch as p
import test_foc_runtime_fix as common
from test_foc_estimate_publish_fix import native_source
from test_foc_update_latency_fix import function


def main():
    out = p.OUT / 'verification'
    out.mkdir(exist_ok=True)
    common.p = p
    template = p.read(p.ROOT / 'artifacts/live_bench_20261029/foc_observer_schedule_fix_r1/verification/plant_budget_sweep.cpp')
    pre = template.split('#define MIC_NATIVE_BUILD', 1)[0]
    pre = pre.replace('struct Timer{uint32_t ARR=', 'struct Timer{uint32_t ARR=')
    pre = '#include "observer_trace_core.h"\n#include "observer_trace_wire.h"\n' + pre
    pre += '\nstatic bool force_torn;\n'
    checks = r'''
#undef ma_observe
static unsigned calls;
static float received_a,received_b,received_dt;
static int host_observe(ma_observer*o,const ma_motor*,float a,float b,float,float,float dt){
 ++calls;received_a=a;received_b=b;received_dt=dt;++o->steps;o->x[2]=.2f;return 0;
}
static void host_publication_irq(){}
static void NVIC_SetPendingIRQ(int irq){assert(irq==25);++kicks;ma_native_profile_tick();}
static void setup(){
 timer.BDTR=0;cycle.CYCCNT=1000000;selected=MA_FOC;qualification=FE_ESTIMATED;
 fe_complete=fe_started=1;fe_fault=0;fe_case=64;id_profile_attempted=1;id_profile_running=0;
 fake_bus=323;sample={};sample.valid=sample.zero=1;sample_coherent=1;
 first_fault=0;memset(&ma_first_runtime,0,sizeof(ma_first_runtime));
 assert(ma_native_prepare());timer.BDTR=1;calls=0;force_torn=false;
}
int main(){
 unsigned tested=0;double mismatch=0;
 for(unsigned delay:{0U,1U,2U,3U,5U}){
  setup();
  if(delay==5)cycle.CYCCNT=0xffff0000U; // input epoch crosses DWT wrap
  for(unsigned frame=0;frame<16;++frame){
   cycle.CYCCNT+=10624;sample.cycles=cycle.CYCCNT-4000;sample.sequence=2*(frame+1);
   sample.counts[0]=20;sample.counts[1]=-10;sample.counts[2]=-10;
   assert(!ma_native_fast(5));
  }
  const uint32_t end=sample.cycles,stamp=bin_cycles;const auto saved=sample;
  // More ADC publications occur while the main loop has not serviced this bin.
  for(unsigned n=0;n<delay;++n){
   cycle.CYCCNT+=10624;sample.cycles=cycle.CYCCNT-4000;sample.sequence+=2;
   sample.counts[0]=80;sample.counts[1]=-40;sample.counts[2]=-40;
  }
  TORN_SNAPSHOT
  ma_native_service();assert(calls==1&&!run_fault);
  const float endpoint=ma_amps(saved.counts[0]);
  CHECK_ENDPOINT
  mismatch+=fabs(received_a-endpoint);++tested;
  // A second service turn must not integrate the same bin again.
  ma_native_service();assert(calls==1);++tested;
 }
 // The exact existing 2ms estimate-age and ADC-age guards still stop.
 for(unsigned kind=0;kind<3;++kind){
  setup();cycle.CYCCNT+=10624;sample.cycles=cycle.CYCCNT;
  sample.counts[0]=20;sample.counts[1]=-10;sample.counts[2]=-10;
  assert(!ma_native_fast(5));
  // Leave the existing1ms neutral priming phase before injecting faults.
  cycle.CYCCNT+=180000;sample.cycles=cycle.CYCCNT;
  assert(!ma_native_fast(5));
  cycle.CYCCNT+=kind==0?340000:10624;sample.cycles=cycle.CYCCNT;
  if(kind==1)sample.cycles-=SystemCoreClock*3U/16000U;
  if(kind==2){sample.counts[0]=150;sample.counts[1]=-75;sample.counts[2]=-75;}
  assert(ma_native_fast(5)!=0);
  assert(run_fault==(kind==2?MA_CURRENT:MA_STALE));++tested;
 }
 printf("{\"checks\":%u,\"summed_endpoint_error_A\":%.9g}\n",tested,mismatch);
}
'''
    results = {}
    for variant, folder in [('baseline', p.BASE), ('candidate', p.OUT)]:
        assert_case = ('assert(received_a==endpoint&&stamp==end);' if variant == 'candidate'
            else 'assert(stamp==end+4000&&received_a==ma_amps(sample.counts[0]));')
        native=native_source(folder, hook=False)
        torn=''
        if variant=='candidate':
            native=native.replace('  sample=bin_current;',
                '  sample=bin_current; if(force_torn){++telemetry_seq;force_torn=false;}')
            torn='if(delay==2){force_torn=true;ma_native_service();assert(calls==0);++telemetry_seq;}'
        code = pre + native + checks.replace('CHECK_ENDPOINT', assert_case).replace('TORN_SNAPSHOT',torn)
        results[variant] = json.loads(common.compile_run(out, 'input_epoch_' + variant, code))
    assert results['baseline']['summed_endpoint_error_A'] > 2
    assert results['candidate']['summed_endpoint_error_A'] == 0

    # Reuse the full recorder/wire test with ONLY the current expected identity.
    import test_observer_trace as old
    src = inspect.getsource(old.main)
    src = src[:src.index('    changed={')]
    src = src.replace('2026103016', str(p.NEW[1]))
    src += '\n    return dict(recorder_wire_checks=core["checks"],actuator=differential)\n'
    scope = dict(old.__dict__, p=p)
    exec(compile(src, __file__, 'exec'), scope)
    recorder_checks=scope['main']()

    base_native = p.read(p.BASE / 'nucleo/Src/multi_native.c')
    new_native = p.read(p.OUT / 'nucleo/Src/multi_native.c')
    assert function(base_native, 'ma_native_diag') == function(new_native, 'ma_native_diag')
    unchanged = ['nucleo/Src/current_shunt.c', 'nucleo/Inc/foc_experiment.h',
        'nucleo/Inc/current_adc_window_plan.h', 'nucleo/Inc/current_adc_deadline.h',
        'nucleo/Inc/local_stop.h', 'nucleo/Inc/first_break_snapshot.h',
        'nucleo/Inc/repeat_state.h']
    for rel in unchanged:
        expected=p.read(p.BASE / rel).replace('2026111401',str(p.NEW[0])).replace('2026111402',str(p.NEW[1]))
        assert expected == p.read(p.OUT / rel), rel
    for fn in ['uno_handle_valid_frame', 'uno_rearm_break_irq', 'mic_repeat_break_irq',
               'mic_local_stop_clear', 'mic_local_stop_enable_outputs']:
        a = p.read(p.BASE / 'nucleo/Src/main.c')
        b = p.read(p.OUT / 'nucleo/Src/main.c')
        assert function(a, fn) == function(b, fn), fn
    for fn in ['ma_observe', 'ma_derivative', 'ma_control_checked']:
        a = p.read(p.BASE / 'nucleo/Inc/motor_control.h')
        b = p.read(p.OUT / 'nucleo/Inc/motor_control.h')
        if fn == 'ma_control_checked':
            b = b.replace('\n  out->id_measured=id;out->iq_measured=iq;', '')
        assert function(a, fn) == function(b, fn), fn
    result = dict(passed=True, actual_adapter_interleavings=results,
        recorder_and_actuator_checks=recorder_checks,
        torn_snapshot_rejected=True, DWT_wrap_checked=True,
        old_voltage_and_new_current_mismatch_reproduced=True,
        candidate_current_and_timestamp_same_endpoint=True,
        protection_sources_unchanged=unchanged, observer_tuning_unchanged=True,
        hardware_commands=0, physical_record_replay=False,
        limitation='Recorded run has no flux/NIS/IdIq capture; exact past loss cause is unproven.')
    p.write(out / 'report.json', json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
