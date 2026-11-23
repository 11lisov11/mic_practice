"""Replay frozen compute-stage refusal and map timing budgets, without hardware."""
import json
import subprocess
import prepare_foc_observer_schedule_fix as p
import test_foc_runtime_fix as common
from test_foc_estimate_publish_fix import native_source


def main():
    out = p.OUT / 'verification'
    common.p = p
    capture = json.loads(p.read(p.BASE / 'powered_FOC_publication_20261030_r2/analysis.json'))
    ff = capture['first_fault']
    pub = ff['publication']
    pre = p.read(p.ROOT / 'artifacts/live_bench_20261029/foc_runtime_fix_r1/verification/native_runtime.cpp').split('#define MIC_NATIVE_BUILD', 1)[0]
    proto = '''static int host_observe(ma_observer*,const ma_motor*,float,float,float,float,float);
#define ma_observe host_observe
'''
    body = r'''
#undef ma_observe
static void NVIC_SetPendingIRQ(int irq){assert(irq==25);++kicks;ma_native_profile_tick();}
static int host_observe(ma_observer*o,const ma_motor*m,float a,float b,float va,float vb,float dt){
 // Suspend the next calculation at the retained interrupt timestamp.
 // X/P themselves were not recorded; their seed below is synthetic.
 cycle.CYCCNT=AT;sample.cycles=ADC;sample.valid=sample.zero=1;
 sample.counts[0]=-46;sample.counts[1]=40;sample.counts[2]=6;bin_cycles=BIN;
 int rc=ma_native_fast(.7f);assert(rc==MC_SW_ERROR);timer.BDTR=0;
 return ma_observe(o,m,a,b,va,vb,dt);
}
int main(){
 selected=MA_FOC;qualification=FE_ESTIMATED;profile_ready=1;
 fe_complete=fe_started=1;fe_case=64;fe_fault=0;id_profile_attempted=1;
 running=1;run_fault=first_fault=0;fe_trial_done=0;ma_reset(&observer,&controller);
 observer.steps=455;ma_estimate_reset(OLD);
 estimate_slot[0].stamp=OLDER;estimate_slot[1].stamp=OLD;estimate_index=1;
 ma_observer_done_cycles=DONE;ma_commit_mark_cycles=COMMIT;ma_perf.steps=455;
 ma_perf.wall=138678;ma_perf.irq=116486;ma_perf.cpu_upper=22192;
 cycle.CYCCNT=BEGIN;bin_cycles=INPUT;bin_va=bin_vb=0;telemetry_seq=914;
 sample={};sample.valid=sample.zero=1;sample_coherent=1;sample.cycles=BEGIN-4000;
 fake_bus=320;timer.BDTR=1;start_cycles=fe_trial_begin=AT-17000000;
 ma_native_service();
 assert(run_fault==MA_STALE&&!timer.BDTR);
 auto*w=ma_first_runtime.word;
 assert(w[0]==FT_ESTIMATE_AGE&&w[2]==AT&&w[4]==OLD);
 assert(w[14]==1&&w[15]==EP_COMPUTE&&w[18]==1&&w[21]==INPUT);
 assert(w[16]==DONE&&w[17]==COMMIT&&w[27]==1);
 assert(estimate_cycles==OLD); // Faulted in-flight calculation never commits.
 printf("{\"reason\":%u,\"stage\":%u,\"age_us\":%.9g,\"stop_retained\":true}\n",w[0],w[15],(AT-OLD)/170.);
}
'''
    constants = '\n'.join('static const uint32_t %s=%sU;' % (name, value) for name, value in {
        'AT': ff['at_cycles'], 'ADC': ff['adc_cycles'], 'BIN': ff['bin_cycles'],
        'BEGIN': ff['observer_begin_cycles'], 'OLD': ff['estimate_cycles'],
        'OLDER': pub['slot_stamps'][0], 'INPUT': pub['input_bin_cycles'],
        'DONE': pub['done_mark_cycles'], 'COMMIT': pub['commit_mark_cycles']}.items())
    replay = json.loads(common.compile_run(out, 'compute_stage_replay',
        '#include <cstdio>\n' + pre + proto + native_source(p.OUT, hook=False) + constants + body))
    # Reuse the already-reviewed actual native-adapter + independent plant harness.
    # Native source differs only in its ID; the changed numeric header is compiled
    # from THIS package. Delays are parameters, never claimed as measured speedup.
    source = p.read(p.BASE / 'verification/plant_schedule_candidate.cpp')
    source = source.replace('2026103010', '2026103012').replace('2026103009', '2026103011')
    begin = source.index(' if(argc>1&&strcmp(argv[1],"overload")')
    end = source.index(' setup();', begin)
    source = source[:begin] + '''
 if(argc>=3){wall_cycles=(uint32_t)strtoul(argv[1],nullptr,10);queue_cycles=(uint32_t)strtoul(argv[2],nullptr,10);}
 account_cycles=0;
''' + source[end:]
    source = source.replace(' if(argc==1)assert(completed&&frames>=80000);\n else assert(!completed&&run_fault==MA_STALE&&reason==FT_ESTIMATE_AGE);', '')
    source = '#include <cstdlib>\n' + source
    first = json.loads(common.compile_run(out, 'plant_budget_sweep', source))
    exe = out / 'plant_budget_sweep.exe'
    results = []
    for wall, queue in [(138678, 63025), (117584, 63025), (138678, 17000),
                        (138678, 0), (119000, 17000), (102000, 17000), (357000, 0)]:
        r = subprocess.run([str(exe), str(wall), str(queue)], capture_output=True, text=True, check=True)
        p.write(out / ('budget_%d_%d.log' % (wall, queue)), r.stdout + r.stderr)
        results.append(dict(wall_cycles=wall, queue_cycles=queue, **json.loads(r.stdout)))
    assert not results[0]['completed_5s'] and results[0]['reason'] == 4
    assert results[2]['completed_5s'] and results[2]['fault'] == 0
    assert not results[-1]['completed_5s'] and results[-1]['reason'] == 4
    report = dict(passed=True, hardware_commands=0, capture_replay=replay,
        original_observer_X_P_not_recorded=True, IRQ_checkpoint_injected_from_frozen_timestamps=True,
        same_latency_still_stops=True, no_fake_timestamp_refresh=True,
        two_ms_guard_unchanged=True, local_five_second_autostop_verified_in_model=True,
        source='Actual native adapter, controller/observer C and independent double-precision flux plant',
        ADC_is_quantized_plant_not_physical_replay=True, timing_scenarios_are_assumptions=True,
        max_wall_and_max_queue_not_proven_from_same_call=True,
        target_speedup_not_measured=True, hardware_5s_not_proven=True,
        needed_budget_example='With an assumed816us observer wall time, <=100us queue delay passes this model. This is a requirement, not a measured candidate timing.',
        default_earlier_capture_scenario=first, results=results)
    p.write(out / 'schedule_model.json', json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
