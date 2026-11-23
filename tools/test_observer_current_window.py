"""Actual native C + independent double flux plant. No hardware interfaces."""
import json,shutil,subprocess
import prepare_observer_current_window as p
from test_foc_estimate_publish_fix import native_source
from analyze_observer_nis import write

def compile_case(out,name,source,folder):
    cpp=out/(name+'.cpp');cpp.write_text(source,encoding='utf8');exe=cpp.with_suffix('.exe')
    r=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',
        '-Wno-unused-function','-Wno-misleading-indentation','-Wno-missing-field-initializers',
        '-I',str(folder/'nucleo/Inc'),'-I',str(folder/'UNOQ_MOTOR'),str(cpp),'-o',str(exe)],capture_output=True,text=True)
    (out/(name+'_build.log')).write_text(r.stdout+r.stderr,encoding='utf8');r.check_returncode();return exe
def main():
    out=p.OUT/'verification';out.mkdir(exist_ok=True)
    template=p.read(p.BASE/'model_verification/plant_observer_candidate.cpp')
    pre=template.split('#define MIC_NATIVE_BUILD',1)[0]
    tail=template[template.index('#undef ma_observe'):]
    # Priming must use actual startup invalid samples, not a fictitious ADC
    # measurement timestamp before PWM startup.
    tail=tail.replace('sample.valid=sample.zero=1;sample.cycles=cycle.CYCCNT-4000;',
        'sample.zero=1;sample.valid=(frames>0);sample.cycles=cycle.CYCCNT-4000;')
    tail=tail.replace(' int rc=ma_native_fast(reference);',
        ''' if(scenario==6&&frames>16000U){sample.counts[0]+=12;sample.counts[1]-=6;sample.counts[2]=-sample.counts[0]-sample.counts[1];}
 if(scenario==7&&frames==20000U){sample.counts[0]=150;sample.counts[1]=-75;sample.counts[2]=-75;}
 int rc=ma_native_fast(reference);''')
    results={}
    for label,folder in [('baseline',p.BASE),('candidate',p.OUT)]:
        extra='#include "observer_current_window.h"\n#include "observer_forecast.h"\n' if label=='candidate' else ''
        this_tail=tail
        if label=='candidate':
            extra+='static int host_forecast(const ma_motor*,const float*,float,float,float,float*);\n#define ow_forecast host_forecast\n'
            this_tail=this_tail.replace('static void host_publication_irq(){',
                '''#undef ow_forecast
static int host_forecast(const ma_motor*m,const float*x,float a,float b,float dt,float*y){
 int rc=ow_forecast(m,x,a,b,dt,y);advance(sim_now+5000U);return rc;
}
static void host_publication_irq(){''')
        exe=compile_case(out,'native_plant_'+label,extra+pre+native_source(folder)+'\n'+this_tail,folder)
        results[label]=[]
        for scenario,name in enumerate(('nominal','Rs_plus20pct','Rr_plus20pct','Lm_minus5pct','ADC_1count','ADC_16counts','sustained_current_bias','raw_overcurrent')):
            cmd=[str(exe),'95737','17000',str(scenario),str(out/(label+'_'+name+'.bin'))]
            r=subprocess.run(cmd,capture_output=True,text=True)
            (out/(label+'_'+name+'.log')).write_text(r.stdout+r.stderr,encoding='utf8');r.check_returncode()
            results[label].append(dict(case=name,**json.loads(r.stdout)))
        r=subprocess.run([str(exe),'357000','0','0',str(out/(label+'_stale.bin'))],capture_output=True,text=True,check=True)
        results[label].append(dict(case='observer_wall_2_1ms',**json.loads(r.stdout)))
    c=results['candidate'];b=results['baseline']
    assert all(x['completed_5s'] for x in c[:6])
    assert c[0]['native_valid_fraction_after1s']>.99
    assert c[5]['peak_NIS']<b[5]['peak_NIS']*.5
    assert c[5]['native_valid_fraction_after1s']>b[5]['native_valid_fraction_after1s']
    assert c[7]['fault']==2 and not c[7]['completed_5s'] # raw1.35A unchanged
    assert c[8]['fault']==3 and not c[8]['completed_5s'] #2ms unchanged
    write(out/'model_report.json',dict(passed=True,hardware_commands=0,results=results,
        measured_hardware_replay=False,plant='independent double precision stator/rotor flux RK4',
        actual_native_adapter=True,target_CPU_cycles_measured=False,
        wall_cycles_assumed=95737,queue_cycles_assumed=17000,candidate_forecast_extra_cycles_assumed=5000,
        Q_R_NIS_current_age_limits_unchanged=True))
    print(json.dumps(dict(passed=True,model_cases_per_variant=len(c),baseline_noisy=b[5],candidate_noisy=c[5],hardware_commands=0)))
if __name__=='__main__':main()
