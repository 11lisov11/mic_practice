"""Audit sealed installed PWM/current code on host; never access a board."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import audit_production_pwm_filters as code

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT/'artifacts/live_bench_20261024/current_shunt_monitor_r4'

TEST = r'''
#include "current_core.h"
#include "current_adc_window_plan.h"
static bool outside_all_edges(unsigned u,unsigned v,unsigned w,unsigned trigger,
                              unsigned before,unsigned after) {
 for(unsigned c:{u,v,w})if(c+before>=trigger && c<=trigger+after)return false;
 return true;
}
int main() {
 TIM_TypeDef timer; PWM_Handle_t pwm{&timer}; ACIM_VF_Handle_t vf{&pwm};
 const unsigned trigger=5312-384,settle=771,aperture=112;
 FILE *csv=fopen("window_sweep.csv","w");if(!csv)return 2;
 fprintf(csv,"bus_v,field_hz,angles,accepted_pair_windows,unmeasured_compare_in_acquisition,all_edge_guard_rejects,max_ccr,proposed_plan_valid\n");
 unsigned total_hazards=0;float first[3]={0,0,0};unsigned example[7]={0};
 unsigned planned=0,planner_failures=0,unavailable=0;
 unsigned index=0;
 for(float bus:{318.f,320.f,323.f}) {
  vf.fVoutMax_PWM_Mod_V=bus/2;
  for(unsigned fi=0;fi<=500;++fi) {
   vf.fFlux_Freq_Hz=fi*.1f;
   unsigned accepted=0,hazards=0,rejected=0,maximum=0,valid_plans=0;
   for(unsigned angle=0;angle<3600;++angle) {
    vf.fFlux_Angle_rad=angle*(2*PI/3600);
    if(ACIM_VF_Controller(&vf)!=MC_NO_ERROR)return 3;
    unsigned u=timer.CCR1,v=timer.CCR2,w=timer.CCR3;
    maximum=std::max(maximum,std::max(u,std::max(v,w)));
    unsigned pair=cm_choose_pair(u,v,w);
    auto plan=mic_plan_current_window(u,v,w,trigger,settle,aperture);
    if(plan.valid) {
     ++planned;++valid_plans;
     if(plan.trigger>trigger || !cm_pair_window(plan.pair,u,v,w,plan.trigger,settle)
          || !outside_all_edges(u,v,w,plan.trigger,settle,aperture)) {
       if(!planner_failures)fprintf(stderr,"Bad plan bus=%f hz=%f angle=%u c=%u,%u,%u t=%u pair=%u\n",bus,fi*.1f,angle,u,v,w,plan.trigger,plan.pair);
       ++planner_failures;
     }
    } else ++unavailable; // no safe interval: reject, never invent a sample
    bool okay=cm_pair_window(pair,u,v,w,trigger,settle);
    if(!okay)continue;
    ++accepted;
    unsigned excluded=pair==2?u:pair==1?v:w;
    if(excluded>=trigger && excluded<=trigger+aperture) {
     ++hazards;
     if(!example[0]) {
      example[0]=fi;example[1]=angle;example[2]=u;example[3]=v;
      example[4]=w;example[5]=pair;example[6]=(unsigned)bus;
     }
    }
    if(!outside_all_edges(u,v,w,trigger,settle,aperture))++rejected;
   }
   if(hazards && first[index]==0)first[index]=fi*.1f;
   total_hazards+=hazards;
   fprintf(csv,"%.0f,%.1f,3600,%u,%u,%u,%u,%u\n",bus,fi*.1f,accepted,hazards,rejected,maximum,valid_plans);
  }
  ++index;
 }
 fclose(csv);
 if(!total_hazards || planner_failures)return 4;
 // Invalid/impossible intervals must never wrap around into a valid plan.
 if(mic_plan_current_window(5000,5000,5000,4928,771,112).valid)return 6;
 if(mic_plan_current_window(2656,2656,2656,200,771,112).valid)return 7;
 // Demonstrate an accepted measurement artifact, not a real motor model.
 // Inject 6 non-clipped raw-ADC outliers into 3200 constant-current samples.
 cm_core state;cm_init(&state);state.zero_ready=1;
 for(unsigned p=0;p<4;++p)state.offset[p]=2068;
 for(unsigned n=0;n<=3200;++n) {
  bool outlier=n>0 && n<=6;
  unsigned a=2068-(outlier?1162:78),b=2068+(outlier?581:39);
  cm_sample(&state,n/16,1,0,a,b,1,0);
 }
 const auto &win=state.published;
 const double scale=3.3/(4095*.04*2.1);
 if(!cm_window_valid(&win) || win.bad || win.flags&CM_CLIP)return 5;
 printf("{\"host_reproduction_passed\":true,\"hardware_commands\":0,"
        "\"proposed_planner\":{\"safe_windows\":%u,\"no_safe_window\":%u,\"geometry_failures\":%u,\"installed\":false},"
        "\"first_aperture_collision_hz_at_bus318_320_323\":[%.1f,%.1f,%.1f],"
        "\"example\":{\"field_hz\":%.1f,\"angle_deg\":%.1f,\"ccr\":[%u,%u,%u],\"pair\":%u,\"bus_v\":%u},"
        "\"synthetic_outlier_demo\":{\"assumed_true_u_a\":%.6f,\"published_rms_u_a\":%.6f,"
        "\"published_peak_u_a\":%.6f,\"valid\":true,\"bad\":%u,\"samples\":%u},"
        "\"physical_cause_proven\":false}",
        planned,unavailable,planner_failures,first[0],first[1],first[2],example[0]*.1,example[1]*.1,
        example[2],example[3],example[4],example[5],example[6],
        78*scale,sqrt((double)win.square[0]/win.n)*scale,win.peak[0]*scale,win.bad,win.n);
}
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--outdir', type=Path, required=True)
    ap.add_argument('--candidate', type=Path, default=PACKAGE)
    ap.add_argument('--planner-latest',type=int,default=4928)
    a = ap.parse_args()
    out = a.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    candidate=a.candidate.resolve()
    base = candidate/'nucleo'
    files = [code.PWM, code.VF, Path('Src/mc_math.c'), Path('Inc/current_core.h'),
             Path('Src/current_shunt.c'), Path('Src/main.c')]
    hashes = {str(p):hashlib.sha256((base/p).read_bytes()).hexdigest() for p in files}
    hashes['proposed_planner'] = hashlib.sha256((ROOT/'tools/current_adc_window_plan.h').read_bytes()).hexdigest()
    pwm, vf, math = [(base/p).read_text(encoding='utf-8-sig') for p in files[:3]]
    table = re.search(r'#define SIN_FLOAT_0_90_TABLE.*?\}', math, re.S)[0]
    source = '#include <cstring>\n'+code.PREAMBLE+code.function(vf, 'mic_float_isfinite')+'\n'
    source += table+'\nconst float fSin_Table[256]=SIN_FLOAT_0_90_TABLE;\n'
    for text, name in [(math, 'MCM_floatTrig_Functions'), (pwm, 'PWM_SetPhasePWMOutputs'), (vf, 'ACIM_VF_Controller')]:
        source += code.function(text, name)+'\n'
    unit = out/'actual_pwm_adc_windows.cpp'
    assert 1<=a.planner_latest<=5312
    test=TEST.replace('mic_plan_current_window(u,v,w,trigger,settle,aperture)',
        'mic_plan_current_window(u,v,w,'+str(a.planner_latest)+',settle,aperture)')
    test=test.replace('plan.trigger>trigger','plan.trigger>'+str(a.planner_latest))
    unit.write_text(source+test, encoding='utf-8')
    exe = out/'actual_pwm_adc_windows.exe'
    build = subprocess.run([shutil.which('g++'), '-std=c++17', '-Ofast', '-Wall', '-Wextra', '-Werror',
                            '-I', str(base/'Inc'), '-I', str(ROOT/'tools'), str(unit), '-o', str(exe)],
                            capture_output=True, text=True, timeout=60)
    (out/'build.log').write_text(build.stdout+build.stderr, encoding='utf-8')
    build.check_returncode()
    run = subprocess.run([str(exe)], cwd=out, capture_output=True, text=True, timeout=50)
    (out/'run.log').write_text(run.stdout+run.stderr, encoding='utf-8')
    run.check_returncode()
    result = json.loads(run.stdout)
    result.update(source_package=str(candidate), source_sha256=hashes,
        source_unchanged=all(hashlib.sha256((base/p).read_bytes()).hexdigest()==hashes[str(p)] for p in files),
        timer_mhz=170, adc_mhz=42.5, adc_sample_cycles=24.5, adc_assumed_trigger_latency_cycles=3.5,
        trigger_ticks=4928, selected_pair_settle_ticks=771, acquisition_end_after_trigger_ticks=112,
        planner_latest_trigger_ticks=a.planner_latest,
        limitations=['Timer compare geometry only; not an analog interference or motor simulation.',
                     'Synthetic ADC outliers are deliberately injected; their occurrence in hardware is not proven.',
                     'No new motor run, firmware update or live register access performed.'])
    (out/'report.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
