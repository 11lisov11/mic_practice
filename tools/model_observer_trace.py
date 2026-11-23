"""Independent flux-plant check of native observer diagnostics, without boards."""
import importlib.util,json,re,subprocess,sys
import prepare_observer_trace as p
import test_foc_runtime_fix as common
from test_foc_estimate_publish_fix import native_source


def main():
    out=p.OUT/'verification';out.mkdir(exist_ok=True);common.p=p
    template=p.read(p.ROOT/'artifacts/live_bench_20261029/foc_observer_schedule_fix_r1/verification/plant_budget_sweep.cpp')
    pre=template.split('#define MIC_NATIVE_BUILD',1)[0]
    pre='#include "observer_trace_core.h"\n#include "observer_trace_wire.h"\n'+pre
    tail=template[template.index('#undef ma_observe'):]
    tail=tail.replace('wall_cycles=117645,queue_cycles=62522,account_cycles=446',
                      'wall_cycles=116656,queue_cycles=17000,account_cycles=0')
    tail=tail.replace('static unsigned frames,observer_calls;',
        'static unsigned frames,observer_calls,late_n,valid_n,step_before;\nstatic double error_sum,peak_nis,min_flux=100;static int scenario;')
    tail=tail.replace(' int rc=ma_native_fast(reference);',
        ' if(scenario==4){sample.counts[0]+=(int)(frames%3)-1;sample.counts[1]+=(int)((frames+1)%3)-1;sample.counts[2]=-sample.counts[0]-sample.counts[1];}\n'
        ' if(scenario==5){sample.counts[0]+=(int)(((frames*1103515245U+12345U)>>16)%33)-16;sample.counts[1]+=(int)(((frames*1664525U+1013904223U)>>16)%33)-16;sample.counts[2]=-sample.counts[0]-sample.counts[1];}\n int rc=ma_native_fast(reference);')
    tail=tail.replace(' setup();',''' scenario=argc>=4?atoi(argv[3]):0;
 setup();
 if(scenario==1)plant.m.rs*=1.2f;
 if(scenario==2)plant.m.rr*=1.2f;
 if(scenario==3)plant.m.lm*=.95f;''')
    tail=tail.replace('   ma_native_service();','''   step_before=observer.steps;ma_native_service();
   if(observer.steps!=step_before){
     peak_nis=fmax(peak_nis,observer.nis);min_flux=fmin(min_flux,hypot(observer.x[2],observer.x[3]));
     if(running&&!run_fault&&timer.BDTR&&sim_now-origin>=170000000ULL){double e=(observer.x[4]-plant.x[4])*9.5492965855;error_sum+=e*e;++late_n;
       if(od_reasons(running,fe_profile_allowed(selected),observer.steps,run_fault,hypotf(observer.x[2],observer.x[3]),model.flux,observer.nis)==0)++valid_n;}
   }''')
    a=tail.index(' printf("{\\"completed_5s')
    tail=tail[:a]+r'''
 DIAGNOSTIC_EXPORT
 printf("{\"completed_5s\":%s,\"PWM_duration_s\":%.9g,\"frames\":%u,\"observer_calls\":%u,\"fault\":%u,\"reason\":%u,\"peak_plant_A\":%.9g,\"rpm_true_end\":%.9g,\"rpm_est_end\":%.9g,\"speed_RMSE_after1s_rpm\":%.9g,\"native_valid_fraction_after1s\":%.9g,\"peak_NIS\":%.9g}\n",
  completed?"true":"false",stop_tick/170000000.,frames,observer_calls,run_fault,reason,peak,
  plant.x[4]*9.5492965855,observer.x[4]*9.5492965855,late_n?sqrt(error_sum/late_n):0.,late_n?(double)valid_n/late_n:0.,peak_nis);
}
'''
    export=r'''
 ma_native_service();
 if(observer_trace.frozen){
  od_receiver rx={};uint8_t packet[43];
  for(unsigned page=0;page<OD_PAGES;++page){assert(ma_observer_trace_packet(packet,MIC_NATIVE_BUILD,page));assert(odw_receive(&rx,packet,MIC_NATIVE_BUILD,MIC_NATIVE_BUILD,true));}
  assert(rx.complete);
  const char*path=argc>=5?argv[4]:"DEFAULT_PATH";FILE*f=fopen(path,"wb");assert(f);assert(fwrite(rx.data,1,OD_BYTES,f)==OD_BYTES);fclose(f);
 }
'''.replace('DEFAULT_PATH',(out/'model_default_trace.bin').as_posix())
    results={}
    for variant,folder in [('baseline',p.BASE),('candidate',p.OUT)]:
        source=pre+'\n'+native_source(folder,hook=True)+'\n'+tail.replace('DIAGNOSTIC_EXPORT',export if variant=='candidate' else '')
        first=json.loads(common.compile_run(out,'plant_observer_'+variant,source))
        results[variant]=[]
        for scenario,name in enumerate(('nominal','Rs_plus20pct','Rr_plus20pct','Lm_minus5pct','ADC_plusminus1count','ADC_plusminus16counts')):
            path=out/(variant+'_'+name+'_trace.bin')
            cmd=[str(out/('plant_observer_'+variant+'.exe')),'116656','17000',str(scenario),str(path)]
            r=subprocess.run(cmd,capture_output=True,text=True,check=True)
            p.write(out/(variant+'_'+name+'.log'),r.stdout+r.stderr)
            results[variant].append(dict(case=name,**json.loads(r.stdout)))
        overload=subprocess.run([str(out/('plant_observer_'+variant+'.exe')),'357000','0','0',str(out/(variant+'_overload_trace.bin'))],capture_output=True,text=True,check=True)
        results[variant].append(dict(case='observer_wall2_1ms',**json.loads(overload.stdout)))
    assert results['baseline']==results['candidate'],'Diagnostics changed simulated actuator trajectory'
    assert results['candidate'][0]['completed_5s']
    assert not results['candidate'][-1]['completed_5s'] and results['candidate'][-1]['fault']==3
    spec=importlib.util.spec_from_file_location('observer_model_decoder',p.OUT/'web_hmi/server.py')
    hmi=importlib.util.module_from_spec(spec);sys.modules[spec.name]=hmi;spec.loader.exec_module(hmi)
    decoded=[]
    for r in results['candidate']:
        f=out/('candidate_'+r['case']+'_trace.bin')
        if not f.exists():continue
        d=hmi.decode_observer_trace_hex(f.read_bytes().hex(),p.NEW[1]);p.write(f.with_suffix('.json'),json.dumps(d,ensure_ascii=False,indent=2))
        decoded.append(dict(case=r['case'],record_count=d['count'],first_loss=d['first_loss'],valid=d['valid_samples'],invalid=d['invalid_samples']))
    report=dict(passed=True,hardware_commands=0,results=results['candidate'],diagnostic_records=decoded,
        baseline_candidate_model_trajectories_identical=True,observer_tuning_unchanged=True,
        independent_plant='double precision stator/rotor flux RK4, separate equations from native current-state observer',
        raw_currents_quantized_from_simulation=True,measured_hardware_replay=False,
        wall_cycles_assumed=116656,queue_cycles_assumed=17000,diagnostic_execution_cost_not_measured_on_target=True,
        no_hardware_speed_ground_truth=True)
    p.write(out/'model_report.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True,results=report['results'],trajectories_identical=True)))


if __name__=='__main__':main()
