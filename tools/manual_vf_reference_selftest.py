"""Execute the real MCSDK ramp, VF_OL branch, ACIM getter and public reference API."""
import argparse
import json
import re
import subprocess
from pathlib import Path
from prepare_pwm_filter_pair import sha

def function(source,name):
    m=re.search(r'(?:__weak\s+)?(?:int16_t|int32_t|bool|float)\s+'+name+r'\s*\([^;]*?\)\s*\{',source)
    assert m,name
    end=m.end();depth=1
    while depth:depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[m.start():end]

def main(package):
    out=package/'vf_reference_selftest';out.mkdir(exist_ok=True)
    base=package/'nucleo';lib=base/'MCSDK_v6.4.2-Full/MotorControl/MCSDK'
    ramp=lib/'MCLib/Any/Src/ramp_ext_mngr.c';header=lib/'MCLib/Any/Inc/ramp_ext_mngr.h'
    vf=lib/'MCLibACIM/Any/Src/acim_vf_control.c';api=base/'Src/mc_interface.c'
    old=Path(json.loads((package/'manifest.json').read_text())['predecessor_candidate'])/'nucleo/Src/mc_interface.c'
    ramp_text=ramp.read_text().replace('#include "ramp_ext_mngr.h"','')
    h=header.read_text();struct=h[h.index('typedef struct'):h.index('} RampExtMngr_Handle_t;')+len('} RampExtMngr_Handle_t;')]
    v=vf.read_text()
    main_path=base/'Src/main.c'
    condition='uno_link.ramp_target_speed_unit!=target_speed_unit && MC_HasRampCompletedMotor1()'
    assert condition in main_path.read_text()
    program='''#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <initializer_list>
#define __weak
#define SPEED_UNIT 10
#define PI 3.14159265358979323846f
'''+struct+'\n'+ramp_text+'''
enum {VF_OL,VF_CL};
struct Motor {uint8_t bPP;};struct Speed {int16_t hAvrMecSpeedUnit;};
struct ACIM_VF_Handle_t {
 RampExtMngr_Handle_t*pRMNGR;Motor*pACIM_MotorParams;Speed*SPD_real;void*fPI;
 int bVF_Mode;float fFlux_Freq_Hz,fFlux_Freq_rads,fRotorFreqRef_rads,fRotorFreqRef_RPM,fSlipFrequency_rads;
};
float PI_Float_Calc(void*,float){return 0;}
struct MCI_Handle_t {ACIM_VF_Handle_t*pACIM_VF;};
'''+ '\n'.join(function(v,n) for n in ('ACIM_VF_FluxFreqCalc','ACIM_VF_GetMecSpeedRefUnit','ACIM_VF_ExecRamp','ACIM_VF_RampCompleted'))+'\n'+function(api.read_text(),'MCI_GetMecSpeedRefUnit')+'\n'+function(old.read_text(),'MCI_GetMecSpeedRefUnit').replace('MCI_GetMecSpeedRefUnit','old_MCI_GetMecSpeedRefUnit')+'''
constexpr int RUN=6,M1=0;
MCI_Handle_t *pMCI[1];
int MCI_GetSTMState(MCI_Handle_t*){return RUN;}
'''+function(api.read_text(),'MCI_RampCompleted')+'\n'+function((base/'Src/mc_api.c').read_text(),'MC_HasRampCompletedMotor1')+r'''
unsigned checks=0;
void check(bool ok,const char*why){++checks;if(!ok){fprintf(stderr,"FAIL %s\n",why);exit(1);}}
int main(){
 for(unsigned pp : {1U,2U}) {
  RampExtMngr_Handle_t ramp{};ramp.FrequencyHz=1000;REMNG_Init(&ramp);
  Motor motor{(uint8_t)pp};Speed speed{};ACIM_VF_Handle_t vf{};
  vf.pRMNGR=&ramp;vf.pACIM_MotorParams=&motor;vf.SPD_real=&speed;vf.bVF_Mode=VF_OL;
  MCI_Handle_t mci{&vf};pMCI[0]=&mci;
  if(pp==1) {
   ACIM_VF_ExecRamp(&vf,100,0);ACIM_VF_FluxFreqCalc(&vf);
   ACIM_VF_ExecRamp(&vf,99,200);
   for(unsigned i=0;i<50;++i) ACIM_VF_FluxFreqCalc(&vf);
   struct {int16_t ramp_target_speed_unit;} uno_link{99};int16_t target_speed_unit=50;
   check(MCI_GetMecSpeedRefUnit(&mci)==99,"negative control: integer reference reaches rounded segment target early");
   check(!('''+condition+r'''),"actual Nucleo continuation waits for SDK completion despite rounded reference equality");
   for(unsigned i=0;i<152;++i) ACIM_VF_FluxFreqCalc(&vf);
   check(('''+condition+r'''),"actual Nucleo continuation advances when SDK ramp completes");
   REMNG_Init(&ramp);
  }
  for(auto target : {5,10,50,20,5}) {
   const unsigned duration=target==20?60000:2500;
   check(ACIM_VF_ExecRamp(&vf,target*SPEED_UNIT/(int)pp,duration),"actual SDK ramp accepts target");
   for(unsigned i=0;i<duration+3;++i) {
    ACIM_VF_FluxFreqCalc(&vf);
    check(std::abs(MCI_GetMecSpeedRefUnit(&mci)*pp/(float)SPEED_UNIT-vf.fFlux_Freq_Hz)<.201f,"public API follows actual VF_OL field used by modulation");
   }
   check(std::abs(vf.fFlux_Freq_Hz-target)<.001f,"actual SDK flux field settles at target");
   check(vf.fRotorFreqRef_RPM==0,"VF_OL leaves CL-only rotor reference unchanged");
   check(old_MCI_GetMecSpeedRefUnit(&mci)==0,"negative control reproduces installed zero-reference bug");
  }
 }
 printf("{\"pass\":true,\"assertions\":%u,\"negative_control_reproduced\":true}\n",checks);
}
'''
    cpp=out/'actual_sdk_reference.cpp';cpp.write_text(program);exe=cpp.with_suffix('.exe')
    built=subprocess.run(['g++','-std=c++17','-Ofast','-Wall','-Wextra','-Werror',str(cpp),'-o',str(exe)],capture_output=True,text=True)
    (out/'compile.log').write_text(built.stdout+built.stderr);built.check_returncode()
    result=subprocess.run([str(exe)],capture_output=True,text=True);(out/'run.log').write_text(result.stdout+result.stderr);result.check_returncode()
    r=json.loads(result.stdout);r.update(hardware_commands=0,hardware_validated=False,
        mc_interface_sha256=sha(api),nucleo_main_sha256=sha(main_path),vf_controller_sha256=sha(vf),ramp_manager_sha256=sha(ramp),
        scope='Exact MCSDK ramp source and actual VF_OL flux calculation/getter/API functions. Peripheral structs and unused closed-loop PI stubbed; no motor simulation.')
    (out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path,required=True);a=p.parse_args();main(a.candidate.resolve())
