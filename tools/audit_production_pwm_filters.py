"""Execute the retained 1204 PWM/VF/filter functions on the host; no board access."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'artifacts/live_bench_20261012/local_button/candidate_r5/nucleo'
LIB=Path('MCSDK_v6.4.2-Full/MotorControl/MCSDK')
PWM=LIB/'MCLibACIM/Any/Src/pwm.c'
VF=LIB/'MCLibACIM/Any/Src/acim_vf_control.c'
FILTER=LIB/'MCLib/Any/Src/r_divider_bus_voltage_sensor.c'
FILTER_HEADER=LIB/'MCLib/Any/Inc/r_divider_bus_voltage_sensor.h'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def function(text,name):
    pattern=r'(?:__weak\s+)?(?:static\s+)?[A-Za-z_][A-Za-z_0-9]*\s+'+re.escape(name)+r'\([^;]*?\)\s*\{.*?^\}'
    match=re.search(pattern,text,re.M|re.S)
    if not match: raise RuntimeError('Missing function '+name)
    return match[0]


def once(text,old,new):
    if text.count(old)!=1: raise RuntimeError('Non-unique patch anchor '+old[:70])
    return text.replace(old,new)


def corrected(sources):
    out=dict(sources)
    out[PWM]=once(out[PWM],'#include "pwm.h"','#include "pwm.h"\n#include <math.h>')
    anchor='uint16_t PWM_SetPhasePWMOutputs(PWM_Handle_t *pHandle, float fDuty1, float fDuty2, float fDuty3)\n{'
    out[PWM]=once(out[PWM],anchor,anchor+'''
  /* Reject the whole update before conversion or any CCR publication. */
  if (!isfinite(fDuty1) || !isfinite(fDuty2) || !isfinite(fDuty3) ||
      fDuty1 < 0.0f || fDuty1 > 1.0f || fDuty2 < 0.0f || fDuty2 > 1.0f ||
      fDuty3 < 0.0f || fDuty3 > 1.0f || pHandle->TIMx->ARR < 2U ||
      pHandle->TIMx->ARR > 65535U)
  {
    return MC_SW_ERROR;
  }
''')
    include='#include "acim_vf_control.h"'
    out[VF]=once(out[VF],include,include+'\n#include <math.h>')
    anchor='uint16_t ACIM_VF_Controller(ACIM_VF_Handle_t *pHandle)\n{'
    out[VF]=once(out[VF],anchor,anchor+'''
  /* A zero/invalid normalizer must never reach duty conversion. */
  if (!isfinite(pHandle->fVoutMax_PWM_Mod_V) || !(pHandle->fVoutMax_PWM_Mod_V > 0.0f) ||
      !isfinite(pHandle->fFlux_Freq_Hz) || !isfinite(pHandle->fFlux_Angle_rad) ||
      !isfinite(pHandle->fFlux_K) || pHandle->fFlux_K < 0.0f ||
      !isfinite(pHandle->fMinFreq_TH_Hz) || pHandle->fMinFreq_TH_Hz < 0.0f ||
      !isfinite(pHandle->fVoltage_Offset) || pHandle->fVoltage_Offset < 0.0f ||
      !isfinite(pHandle->fNominalPhaseVoltagePeak_V) || !(pHandle->fNominalPhaseVoltagePeak_V > 0.0f))
  {
    return MC_SW_ERROR;
  }
''')
    out[Path('Src/mc_tasks.c')]=once(out[Path('Src/mc_tasks.c')],
        'if(returnValue == MC_DURATION)','if(returnValue != MC_NO_ERROR)')
    out[Path('Src/mc_tasks.c')]=once(out[Path('Src/mc_tasks.c')],
        'MCI_FaultProcessing(&Mci[M1], MC_DURATION, 0);',
        'MCI_FaultProcessing(&Mci[M1], returnValue, 0);')
    out[FILTER_HEADER]=once(out[FILTER_HEADER],'} RDivider_Handle_t;',
        '  int32_t FilterRemainder; /* Fraction retained by the 1/256 IIR. */\n} RDivider_Handle_t;')
    init='    pHandle->_Super.AvBusVoltage_d = (pHandle->OverVoltageThreshold + pHandle->UnderVoltageThreshold) / 2U;'
    out[FILTER]=once(out[FILTER],init,init+'\n    pHandle->FilterRemainder = 0;')
    old='      pHandle->_Super.AvBusVoltage_d += (hAux - pHandle->_Super.AvBusVoltage_d) >> 8U;'
    out[FILTER]=once(out[FILTER],old,'''      const int32_t delta = (int32_t)hAux - (int32_t)pHandle->_Super.AvBusVoltage_d;
      const int32_t total = delta + pHandle->FilterRemainder;
      const int32_t step = total / 256;
      pHandle->FilterRemainder = total - step * 256;
      pHandle->_Super.AvBusVoltage_d = (uint16_t)((int32_t)pHandle->_Super.AvBusVoltage_d + step);''')
    out[FILTER]=once(out[FILTER],'''    if (0xFFFFU == hAux)
    {
      /* Nothing to do */
    }''','''    if (0xFFFFU == hAux)
    {
      /* No new ADC result: do not erase a previously measured voltage fault. */
      tempValue = pHandle->_Super.FaultState;
    }''')
    return out


PREAMBLE=r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <initializer_list>
#include <algorithm>
using std::isfinite;
#define __weak
#define PI 3.14159265358979323846
#define MC_NO_ERROR 0U
#define MC_NO_FAULTS 0U
#define MC_DURATION 1U
#define MC_OVER_VOLT 2U
#define MC_UNDER_VOLT 4U
#define MC_SW_ERROR 128U
struct TIM_TypeDef {uint32_t ARR=5312,CCR1=0,CCR2=0,CCR3=0,BDTR=32768; bool update=false,update_irq=true;};
struct PWM_Handle_t {TIM_TypeDef *TIMx; float fDuty1=0,fDuty2=0,fDuty3=0; uint16_t hCCR1=0,hCCR2=0,hCCR3=0;};
struct ACIM_VF_Handle_t {PWM_Handle_t *pPWM; float fFlux_Freq_Hz=5,fFlux_Angle_rad=0,
    fMinFreq_TH_Hz=10,fFlux_K=.5717009f,fVoltage_Offset=20,
    fNominalPhaseVoltagePeak_V=127*1.4142f,fVoutMax_PWM_Mod_V=162.5f,VoltageAmpl=0;};
struct BusVoltageSensor_Handle_t {uint16_t ConversionFactor=416,LatestConv=0,AvBusVoltage_d=0,FaultState=0;};
struct RDivider_Handle_t {BusVoltageSensor_Handle_t _Super; uint16_t OverVoltageThreshold=65000,
    OverVoltageThresholdLow=65000; bool OverVoltageHysteresisUpDir=false; uint16_t UnderVoltageThreshold=0;
    int32_t FilterRemainder=0;};
struct fTrig_Components {float fSin,fCos;};
unsigned writes=0;
void LL_TIM_OC_SetCompareCH1(TIM_TypeDef *p,uint16_t v){p->CCR1=v;++writes;}
void LL_TIM_OC_SetCompareCH2(TIM_TypeDef *p,uint16_t v){p->CCR2=v;++writes;}
void LL_TIM_OC_SetCompareCH3(TIM_TypeDef *p,uint16_t v){p->CCR3=v;++writes;}
bool LL_TIM_IsActiveFlag_UPDATE(TIM_TypeDef *p){return p->update;}
#define LL_TIM_OSSI_ENABLE 1024U
#define M1 0
void LL_TIM_DisableAllOutputs(TIM_TypeDef *p){p->BDTR&=~32768U;}
void LL_TIM_DisableIT_UPDATE(TIM_TypeDef *p){p->update_irq=false;}
ACIM_VF_Handle_t *pACIM_VF[1];
PWM_Handle_t *pwmHandle[1];
struct MCI_Mock {unsigned fault=0;}; MCI_Mock Mci[1];
struct {unsigned Mark=0;} MCPA_UART_A;
unsigned GLOBAL_TIMESTAMP=0;
// Model only dispatch here; physical IRQ execution/angle integration are out of scope.
void ACIM_VF_CalcAngle(ACIM_VF_Handle_t *){}
void MCI_FaultProcessing(MCI_Mock *p,unsigned fault,unsigned){p->fault=fault;}
void MCPA_dataLog(void *){}
'''


TESTS=r'''
int main(){
 TIM_TypeDef t; PWM_Handle_t p{&t}; ACIM_VF_Handle_t h{&p};
 unsigned comparisons=0,invalid_cases=0;
 // Use the production lookup table and controller, including reverse rotation.
 for(float bus:{125.f,250.f,325.f,360.f,385.f})
  for(float hz:{-60.f,-10.f,-5.f,0.f,5.f,9.99f,10.f,50.f,60.f})
   for(unsigned k=0;k<2048;++k){
    h.fVoutMax_PWM_Mod_V=bus/2;h.fFlux_Freq_Hz=hz;
    h.fFlux_Angle_rad=float((hz<0?-1.0:1.0)*double(k)*(2*PI/2048));
    writes=0; auto a=baseline_ACIM_VF_Controller(&h);
    uint32_t c1=t.CCR1,c2=t.CCR2,c3=t.CCR3;
    float d1=p.fDuty1,d2=p.fDuty2,d3=p.fDuty3;
    auto b=candidate_ACIM_VF_Controller(&h);
    if(!(a==b && c1==t.CCR1 && c2==t.CCR2 && c3==t.CCR3)) {
      std::fprintf(stderr,"valid comparison bus=%g hz=%g k=%u angle=%g results=%u/%u duties=%g,%g,%g CCR=%u,%u,%u -> %u,%u,%u\n",
        bus,hz,k,h.fFlux_Angle_rad,a,b,d1,d2,d3,c1,c2,c3,t.CCR1,t.CCR2,t.CCR3);
      return 2;
    }
    assert(d1==p.fDuty1 && d2==p.fDuty2 && d3==p.fDuty3 && writes==6);
    assert(t.CCR1<t.ARR && t.CCR2<t.ARR && t.CCR3<t.ARR);++comparisons;
   }
 // Witness: original accepts a zero normalizer and stores nonfinite duties.
 h=ACIM_VF_Handle_t{&p};h.fVoutMax_PWM_Mod_V=0; writes=0;
 auto zero_result=baseline_ACIM_VF_Controller(&h);
 bool zero_bad=!std::isfinite(p.fDuty1)||!std::isfinite(p.fDuty2)||!std::isfinite(p.fDuty3);
 unsigned zero_writes=writes;
 assert(zero_result==MC_NO_ERROR && zero_bad && zero_writes==3);
 writes=0;assert(candidate_ACIM_VF_Controller(&h)==MC_SW_ERROR && writes==0);++invalid_cases;
 h=ACIM_VF_Handle_t{&p};
 for(float bad:{-.1f,1.1f,NAN,INFINITY,-INFINITY})for(unsigned phase=0;phase<3;++phase){
  float duty[3]={.5f,.5f,.5f};duty[phase]=bad;writes=0;
  uint32_t a=t.CCR1,b=t.CCR2,c=t.CCR3;
  assert(candidate_PWM_SetPhasePWMOutputs(&p,duty[0],duty[1],duty[2])==MC_SW_ERROR);
  assert(writes==0 && a==t.CCR1 && b==t.CCR2 && c==t.CCR3);++invalid_cases;
 }
 for(uint32_t arr:{0U,1U,65536U}){t.ARR=arr;writes=0;
  assert(candidate_PWM_SetPhasePWMOutputs(&p,.5f,.5f,.5f)==MC_SW_ERROR && writes==0);++invalid_cases;}
 t.ARR=5312;
 for(float norm:{-1.f,NAN,INFINITY}){h=ACIM_VF_Handle_t{&p};h.fVoutMax_PWM_Mod_V=norm;writes=0;
  assert(candidate_ACIM_VF_Controller(&h)==MC_SW_ERROR && writes==0);++invalid_cases;}
 h=ACIM_VF_Handle_t{&p};h.fFlux_Freq_Hz=NAN;writes=0;
 assert(candidate_ACIM_VF_Controller(&h)==MC_SW_ERROR && writes==0);++invalid_cases;
 h=ACIM_VF_Handle_t{&p};h.fFlux_Angle_rad=NAN;writes=0;
 assert(candidate_ACIM_VF_Controller(&h)==MC_SW_ERROR && writes==0);++invalid_cases;
 for(unsigned field=0;field<4;++field)for(float bad:{-1.f,NAN,INFINITY}){
  h=ACIM_VF_Handle_t{&p};
  float *fields[]={&h.fFlux_K,&h.fMinFreq_TH_Hz,&h.fVoltage_Offset,&h.fNominalPhaseVoltagePeak_V};
  *fields[field]=bad;writes=0;
  assert(candidate_ACIM_VF_Controller(&h)==MC_SW_ERROR && writes==0);++invalid_cases;
 }
 t.update=true;h=ACIM_VF_Handle_t{&p};
 assert(candidate_ACIM_VF_Controller(&h)==MC_DURATION);t.update=false;++invalid_cases;
 pACIM_VF[0]=&h;pwmHandle[0]=&p;
 h=ACIM_VF_Handle_t{&p};h.fVoutMax_PWM_Mod_V=0; t.BDTR=32768;t.update_irq=true;Mci[0].fault=0;writes=0;
 baseline_TSK_HighFrequencyTask();
 assert(t.BDTR==32768 && Mci[0].fault==0 && writes==3);
 t.BDTR=32768;t.update_irq=true;Mci[0].fault=0;writes=0;
 candidate_TSK_HighFrequencyTask();
 assert(!(t.BDTR&32768) && !t.update_irq && Mci[0].fault==MC_SW_ERROR && writes==0);++invalid_cases;
 h=ACIM_VF_Handle_t{&p};t.BDTR=32768;t.update_irq=true;t.update=true;Mci[0].fault=0;
 candidate_TSK_HighFrequencyTask();
 assert(!(t.BDTR&32768) && !t.update_irq && Mci[0].fault==MC_DURATION);t.update=false;++invalid_cases;
 unsigned max_old_lag=0,max_new_lag=0,filter_cases=0;
 for(unsigned code=0;code<4096;++code)for(unsigned init:{0U,65535U}){
  uint16_t raw=uint16_t(code<<4);RDivider_Handle_t a,b;
  a._Super.AvBusVoltage_d=b._Super.AvBusVoltage_d=uint16_t(init);
  for(unsigned n=0;n<4096;++n){
   baseline_RVBS_CalcAvVbus(&a,raw);candidate_RVBS_CalcAvVbus(&b,raw);
   assert(b._Super.AvBusVoltage_d>=std::min(unsigned(raw),init));
   assert(b._Super.AvBusVoltage_d<=std::max(unsigned(raw),init));
   assert(std::abs(b.FilterRemainder)<256);
  }
  unsigned old=std::abs(int(raw)-int(a._Super.AvBusVoltage_d));
  unsigned fixed=std::abs(int(raw)-int(b._Super.AvBusVoltage_d));
  max_old_lag=std::max(max_old_lag,old);max_new_lag=std::max(max_new_lag,fixed);
  assert(fixed==0);
  auto state=b;candidate_RVBS_CalcAvVbus(&b,0xffff);
  assert(b._Super.AvBusVoltage_d==state._Super.AvBusVoltage_d && b.FilterRemainder==state.FilterRemainder);
  ++filter_cases;
 }
 RDivider_Handle_t up,down;unsigned up95=0,down95=0;
 down._Super.AvBusVoltage_d=50000;
 for(unsigned n=1;n<4096;++n){candidate_RVBS_CalcAvVbus(&up,50000);candidate_RVBS_CalcAvVbus(&down,0);
  if(!up95 && up._Super.AvBusVoltage_d>=47500)up95=n;
  if(!down95 && down._Super.AvBusVoltage_d<=2500)down95=n;}
 assert(up95==down95 && up95>=760 && up95<=770);
 unsigned unavailable_fault_cases=0;
 for(uint16_t fault:{uint16_t(0),uint16_t(2),uint16_t(4)}){
  RDivider_Handle_t h;h._Super.FaultState=fault;
  assert(baseline_RVBS_CalcAvVbus(&h,0xffff)==MC_NO_ERROR);
  assert(candidate_RVBS_CalcAvVbus(&h,0xffff)==fault);++unavailable_fault_cases;
 }
 RDivider_Handle_t init;init.FilterRemainder=250;candidate_RVBS_Init(&init);assert(init.FilterRemainder==0);
 // Actual unchanged fault predicate still handles threshold/hysteresis correctly.
 for(unsigned value:{0U,9999U,10000U,30000U,50000U,50001U,65535U}){
  RDivider_Handle_t a,b;a.UnderVoltageThreshold=b.UnderVoltageThreshold=10000;
  a.OverVoltageThreshold=b.OverVoltageThreshold=50000;
  a.OverVoltageThresholdLow=b.OverVoltageThresholdLow=40000;
  a._Super.AvBusVoltage_d=b._Super.AvBusVoltage_d=uint16_t(value);
  assert(baseline_RVBS_CheckFaultState(&a)==candidate_RVBS_CheckFaultState(&b));
  assert(a.OverVoltageHysteresisUpDir==b.OverVoltageHysteresisUpDir);
 }
 std::printf("{\"pass\":true,\"valid_pwm_comparisons\":%u,\"invalid_input_cases\":%u,"
  "\"baseline_zero_normalizer_result\":%u,\"baseline_zero_normalizer_nonfinite_duty\":true,"
  "\"baseline_zero_normalizer_ccr_writes\":%u,\"filter_constant_input_cases\":%u,"
  "\"baseline_max_filter_lag_u16\":%u,\"candidate_max_filter_lag_u16\":%u,"
  "\"candidate_rise_95_samples\":%u,\"candidate_fall_95_samples\":%u,"
  "\"unavailable_adc_fault_preservation_cases\":%u}\n",
  comparisons,invalid_cases,zero_result,zero_writes,filter_cases,max_old_lag,max_new_lag,up95,down95,unavailable_fault_cases);
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir',type=Path,required=True)
    args=parser.parse_args(); out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    paths=[PWM,VF,FILTER,FILTER_HEADER,Path('Src/mc_tasks.c'),Path('Src/mc_math.c'),
        Path('Inc/parameters_conversion.h'),Path('Inc/parameters_conversion_g4xx.h'),Path('Inc/drive_parameters.h')]
    sources={p:(PROJECT/p).read_text(encoding='utf-8-sig',errors='replace') for p in paths}
    before={str(p):sha(PROJECT/p) for p in paths}
    fixed=corrected(sources)
    patches=[]
    for p in paths:
        if sources[p]!=fixed[p]:
            dest=out/'candidate_unflashed'/p;dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(fixed[p],encoding='utf-8',newline='\n')
            patches.append(''.join(difflib.unified_diff(sources[p].splitlines(True),fixed[p].splitlines(True),
                fromfile='a/'+p.as_posix(),tofile='b/'+p.as_posix())))
    (out/'candidate_unflashed.patch').write_text('\n'.join(patches),encoding='utf-8')
    table=re.search(r'#define SIN_FLOAT_0_90_TABLE.*?\}',sources[Path('Src/mc_math.c')],re.S)[0]
    program=PREAMBLE+table+'\nconst float fSin_Table[256]=SIN_FLOAT_0_90_TABLE;\n'
    program+=function(sources[Path('Src/mc_math.c')],'MCM_floatTrig_Functions')+'\n'
    for label,body in (('baseline',sources),('candidate',fixed)):
        blocks=[function(body[PWM],'PWM_SetPhasePWMOutputs'),function(body[VF],'ACIM_VF_Controller'),
                function(body[PWM],'PWM_SwitchOffPWM'),function(body[Path('Src/mc_tasks.c')],'TSK_HighFrequencyTask'),
                function(body[FILTER],'RVBS_CheckFaultState'),function(body[FILTER],'RVBS_CalcAvVbus'),
                function(body[FILTER],'RVBS_Init')]
        block='\n'.join(blocks)
        for name in ('PWM_SetPhasePWMOutputs','ACIM_VF_Controller','PWM_SwitchOffPWM','TSK_HighFrequencyTask',
                     'RVBS_CheckFaultState','RVBS_CalcAvVbus','RVBS_Init'):
            block=re.sub(r'\b'+name+r'\b',label+'_'+name,block)
        program+=block+'\n'
    program+=TESTS
    unit=out/'actual_functions.cpp';unit.write_text(program,encoding='utf-8')
    compiler=shutil.which('g++');assert compiler,'g++ required'
    exe=out/'actual_functions.exe'
    build=subprocess.run([compiler,'-O2','-std=c++17','-Wall','-Wextra',str(unit),'-o',str(exe)],
        capture_output=True,text=True,timeout=40)
    (out/'build.log').write_text(build.stdout+build.stderr)
    build.check_returncode()
    run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=40)
    (out/'run.log').write_text(run.stdout+run.stderr);run.check_returncode()
    report=json.loads(run.stdout)
    report.update(schema='mic_ai.production_pwm_filter_audit.v1',source_pair=[2026101205,2026101204],
        hardware_commands=0,firmware_flashed=False,release_ready=False,
        source_sha256=before,sources_unchanged=all(sha(PROJECT/p)==before[str(p)] for p in paths),
        candidate_modified_files=[p.as_posix() for p in paths if fixed[p]!=sources[p]],
        physical_incident_cause_proven=False,
        limitations=['Host register stubs do not reproduce physical output pulses or IRQ timing; angle-update dispatch is stubbed in HFT propagation tests',
          'Zero normalizer exposes a software defect; it is not demonstrated in the powered trial',
          'Filter correction changes DC bias and handle layout: target rebuild and calibration review required',
          'Hardware BKIN filter and UART acceptance/stop guards remain unchanged'])
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in report if k not in ('source_sha256','limitations')},indent=2))


if __name__=='__main__':main()
