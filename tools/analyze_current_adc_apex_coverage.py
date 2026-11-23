"""Offline sweep of actual V/f compares versus ADC latest-upstroke deadline."""
import json
import re
import shutil
import subprocess
from pathlib import Path
import audit_production_pwm_filters as code

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261024/current_adc_window_fix_r1'
OUT=BASE.parent/'adc_coverage_analysis_r1'
TEST=r'''
#include "current_adc_window_plan.h"
int main(){TIM_TypeDef timer; PWM_Handle_t pwm{&timer}; ACIM_VF_Handle_t vf{&pwm};
 for(float bus:{318.f,320.f,324.f})for(float f:{40.f,45.f,50.f})
 for(unsigned latest:{4928U,5056U,5120U,5152U,5184U,5200U,5280U}){
  unsigned good=0;vf.fVoutMax_PWM_Mod_V=bus/2;vf.fFlux_Freq_Hz=f;
  for(unsigned a=0;a<3600;++a){vf.fFlux_Angle_rad=a*(2*PI/3600);
   if(ACIM_VF_Controller(&vf))return 1;
   auto p=mic_plan_current_window(timer.CCR1,timer.CCR2,timer.CCR3,latest,771,112);good+=p.valid;
  }
  printf("%.0f,%.0f,%u,%u\n",bus,f,latest,good);
 }
}
'''
def main():
    OUT.mkdir(exist_ok=True)
    base=BASE/'nucleo'
    pwm,vf,math=[(base/p).read_text(encoding='utf-8-sig') for p in (code.PWM,code.VF,Path('Src/mc_math.c'))]
    s='#include <cstring>\n'+code.PREAMBLE+code.function(vf,'mic_float_isfinite')+'\n'
    s+=re.search(r'#define SIN_FLOAT_0_90_TABLE.*?\}',math,re.S)[0]+'\nconst float fSin_Table[256]=SIN_FLOAT_0_90_TABLE;\n'
    for text,name in ((math,'MCM_floatTrig_Functions'),(pwm,'PWM_SetPhasePWMOutputs'),(vf,'ACIM_VF_Controller')):s+=code.function(text,name)+'\n'
    (OUT/'variants.cpp').write_text(s+TEST,encoding='utf-8')
    b=subprocess.run([shutil.which('g++'),'-std=c++17','-Ofast','-I',str(base/'Inc'),str(OUT/'variants.cpp'),'-o',str(OUT/'variants.exe')],capture_output=True,text=True)
    (OUT/'build.log').write_text(b.stdout+b.stderr,encoding='utf-8');b.check_returncode()
    r=subprocess.run([str(OUT/'variants.exe')],capture_output=True,text=True,check=True)
    (OUT/'variants.csv').write_text('bus_v,field_hz,latest_trigger,safe_angles_of_3600\n'+r.stdout,encoding='utf-8')
    rows=[dict(zip(('bus_v','field_hz','latest_trigger','safe_angles'),map(int,l.split(',')))) for l in r.stdout.splitlines()]
    report=dict(hardware_commands=0,source='actual installed PWM/Vf functions',rows=rows,
        limitation='Compare geometry only; changing the sampling point does not replay analog currents there.')
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps([r for r in rows if r['latest_trigger'] in (4928,5184)]))
if __name__=='__main__':main()
