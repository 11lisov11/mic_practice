"""Run the exact target ramp/phase/VF/PWM functions on a host timer model."""
import json,re,subprocess
import prepare_no_switch_diag as p
import audit_production_pwm_filters as a
TEST=r'''
static unsigned checks;
static void test(bool v){++checks;if(!v){fprintf(stderr,"math check%u\n",checks);exit(1);}}
int main(){
 TIM_TypeDef timer;timer.BDTR=0;PWM_Handle_t pwm{&timer};
 ACIM_VF_Handle_t h{&pwm};RampExtMngr_Handle_t ramp{};ramp.FrequencyHz=500;
 Motor motor{1};h.pACIM_MotorParams=&motor;h.pRMNGR=&ramp;h.bVF_Mode=VF_OL;
 h.fCalcAngleExecFreqHz=16000;h.fCalcAngleExecTime_s=1.f/16000;h.fVoutMax_PWM_Mod_V=327.f/2;
 REMNG_Init(&ramp);test(ACIM_VF_ExecRamp(&h,50,3000));
 unsigned lo=5312,hi=0;float old=0;
 for(unsigned n=0;n<80000;n++){
  if(n%32==0){ACIM_VF_FluxFreqCalc(&h);test(h.fFlux_Freq_Hz>=old&&h.fFlux_Freq_Hz<=5);old=h.fFlux_Freq_Hz;}
  ACIM_VF_CalcAngle(&h);writes=0;test(ACIM_VF_Controller(&h)==0&&writes==3);
  test(timer.BDTR==0);test(h.fFlux_Angle_rad>=0&&h.fFlux_Angle_rad<2*PI);
  for(unsigned c:{timer.CCR1,timer.CCR2,timer.CCR3}){test(c<5312);lo=std::min(lo,c);hi=std::max(hi,c);}
  if(n==16000)test(h.fFlux_Freq_Hz>=1.6f&&h.fFlux_Freq_Hz<=1.7f);
  if(n==32000)test(h.fFlux_Freq_Hz>=3.3f&&h.fFlux_Freq_Hz<=3.4f);
  if(n>49000)test(h.fFlux_Freq_Hz==5);
 }
 test(lo>=2329&&lo<=2331&&hi>=2979&&hi<=2981);
 test(fabs(h.VoltageAmpl-20)<.0001f);
 h.fVoutMax_PWM_Mod_V=0;writes=0;test(ACIM_VF_Controller(&h)==MC_SW_ERROR&&writes==0);
 printf("{\"passed\":true,\"checks\":%u,\"actual_controller_calls\":80000,\"actual_medium_calls\":2500,\"ccr_min\":%u,\"ccr_max\":%u,\"physical_hardware\":false}\n",checks,lo,hi);
}
'''
def main():
 c=p.OUT/'nucleo';lib=c/'MCSDK_v6.4.2-Full/MotorControl/MCSDK';v=p.OUT/'verification'
 vf=p.read(c/a.VF);pwm=p.read(c/a.PWM);math=p.read(c/'Src/mc_math.c')
 header=p.read(lib/'MCLib/Any/Inc/ramp_ext_mngr.h')
 struct=header[header.index('typedef struct'):header.index('} RampExtMngr_Handle_t;')+len('} RampExtMngr_Handle_t;')]
 ramp=p.read(lib/'MCLib/Any/Src/ramp_ext_mngr.c').replace('#include "ramp_ext_mngr.h"','')
 pre=a.PREAMBLE.replace('using std::isfinite;','#include <cstring>\n#include <cstdlib>\nusing std::isfinite;\n#define SPEED_UNIT 10\n'+struct+'\n')
 pre=pre.replace('void ACIM_VF_CalcAngle(ACIM_VF_Handle_t *){}','')
 pre=pre.replace('struct ACIM_VF_Handle_t {PWM_Handle_t *pPWM;','''enum {VF_OL,VF_CL};struct Motor{uint8_t bPP;};struct Speed{int16_t hAvrMecSpeedUnit;};
struct ACIM_VF_Handle_t {PWM_Handle_t*pPWM;RampExtMngr_Handle_t*pRMNGR=nullptr;Motor*pACIM_MotorParams=nullptr;Speed*SPD_real=nullptr;void*fPI=nullptr;
 int bVF_Mode=VF_OL;int16_t hElAngle=0;float fFlux_Freq_rads=0,fCalcAngleExecTime_s=0,fCalcAngleExecFreqHz=0,
 fRotorFreqRef_rads=0,fRotorFreqRef_RPM=0,fSlipFrequency_rads=0;
''')
 pre+='\nfloat PI_Float_Calc(void*,float){return 0;}\n'
 unit=lib/'MCLibACIM/Any/Src/unit_conversions.c'
 table=re.search(r'#define SIN_FLOAT_0_90_TABLE.*?\}',math,re.S)[0]
 code=pre+ramp+'\n'+a.function(p.read(unit),'Convert_Rad_to16bit')+'\n'+a.function(vf,'mic_float_isfinite')+'\n'+table+'\nconst float fSin_Table[256]=SIN_FLOAT_0_90_TABLE;\n'
 code+=a.function(math,'MCM_floatTrig_Functions')+'\n'+a.function(pwm,'PWM_SetPhasePWMOutputs')+'\n'
 for name in ('ACIM_VF_ExecRamp','ACIM_VF_FluxFreqCalc','ACIM_VF_CalcAngle','ACIM_VF_Controller'):code+=a.function(vf,name)+'\n'
 p.write(v/'actual_diag_math.cpp',code+TEST)
 exe=v/'math.exe'
 q=subprocess.run(['g++','-std=c++17','-Ofast','-Wall','-Wextra','-Werror',str(v/'actual_diag_math.cpp'),'-o',str(exe)],capture_output=True,text=True,timeout=60)
 p.write(v/'math_compile.log',q.stdout+q.stderr)
 if q.returncode:print(q.stderr);q.check_returncode()
 q=subprocess.run([str(exe)],capture_output=True,text=True,timeout=60);p.write(v/'math.log',q.stdout+q.stderr)
 if q.returncode:print(q.stderr);q.check_returncode()
 r=json.loads(q.stdout);p.write(v/'math_report.json',json.dumps(r,indent=2)+'\n');print(json.dumps(r))
if __name__=='__main__':main()
