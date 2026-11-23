"""Schedule shared regular ADC before injection; no hardware commands."""
import json,os,shutil
from pathlib import Path
from prepare_standstill_commissioning import ROOT,read,write,once
BASE=ROOT/'artifacts/live_bench_20261029/foc_update_latency_fix_r1'
OUT=ROOT/'artifacts/live_bench_20261029/foc_regular_adc_fix_r2'
NEW=(2026103005,2026103006)
def main():
 assert not OUT.exists()
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  def cp(src,dst):
   rel=Path(src).relative_to(BASE/folder)
   if folder=='libraries' or (folder=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full')):os.link(src,dst);return dst
   return shutil.copy2(src,dst)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=cp,ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    s=read(f);n=s.replace('2026103003','2026103005').replace('2026103004','2026103006').replace('3003-update-latency','3005-regular-adc')
    if s!=n:write(f,n)
 f=OUT/'nucleo/Inc/current_shunt.h';write(f,once(read(f),'void mic_current_update_epoch(void);','void mic_current_update_epoch(void);\nuint8_t mic_current_regular_window(void);'))
 f=OUT/'nucleo/Src/current_shunt.c';s=read(f)
 anchor='static void queue_pair(uint8_t pair) {'
 s=once(s,anchor,'''/* ADC-IRQ tail only. Middle of down-count half: injection has finished,
 * and>1024 ticks remain before bottom/TIM1 preemption. A regular47.5+12.5
 * ADC-cycle conversion at42.5MHz needs240 timer ticks. */
uint8_t mic_current_regular_window(void){
 uint32_t cnt=TIM1->CNT,down=TIM1->CR1&TIM_CR1_DIR;
 uint32_t arr=TIM1->ARR;
 return (uint8_t)(down&&arr>1536U&&cnt>1024U&&cnt<arr-512U);
}

'''+anchor);write(f,s)
 f=OUT/'nucleo/Inc/regular_conversion_manager.h';s=read(f);s=once(s,'void RCM_WaitForConv(void);','void RCM_WaitForConv(void);\nint RCM_CurrentEpoch(void);\nvoid RCM_ServiceAfterInjected(void);\nuint16_t RCM_CurrentFault(void);');write(f,s)
 f=OUT/'nucleo/Src/regular_conversion_manager.c';s=read(f)
 s=once(s,'#include "mc_config.h"','#include "mc_config.h"\n#include "current_shunt.h"\n#include "stm32g4xx_ll_tim.h"')
 anchor='/* Private function prototypes -----------------------------------------------*/'
 helpers='''/* Only ADC IRQ tail launches regular conversions during RUN. SysTick reads
 * completed cached values: it never changes SQR or ADSTART during injection.
 * OFF keeps the original blocking API and primes these same caches. */
static RegConv_t *rcm_pending;
static uint8_t rcm_next,rcm_valid[RCM_MAX_CONV];
static uint32_t rcm_stamp[RCM_MAX_CONV];
static volatile uint16_t rcm_fault;
static int rcm_complete(void){
 if(!rcm_pending)return 1;
 if(!LL_ADC_IsActiveFlag_EOC(rcm_pending->regADC))return 0;
 rcm_pending->data=LL_ADC_REG_ReadConversionData12L(rcm_pending->regADC);
 rcm_stamp[rcm_pending->id]=DWT->CYCCNT;__DMB();rcm_valid[rcm_pending->id]=1;
 rcm_pending=NULL;return 1;
}
uint16_t RCM_CurrentFault(void){return rcm_fault;}
int RCM_CurrentEpoch(void){
 if(!LL_TIM_IsEnabledAllOutputs(TIM1))return 1;
 if(rcm_fault)return 0;
 /* Missing conversion completion or stale safety feedback fails closed.
  * The original safety period is0.5ms; maximum cache age here is1ms. */
 for(unsigned i=0;i<RCM_conversion_nb;++i){
  RegConv_t*c=RCM_handle_array[i];
  if(c->regADC!=ADC1||c->samplingTime!=LL_ADC_SAMPLINGTIME_47CYCLES_5||
     !rcm_valid[i]||(uint32_t)(DWT->CYCCNT-rcm_stamp[i])>=SystemCoreClock/1000U){
    rcm_fault=MC_SW_ERROR;return 0;
  }
 }
 return 1;
}
void RCM_ServiceAfterInjected(void){
 if(!LL_TIM_IsEnabledAllOutputs(TIM1)||rcm_fault)return;
 if(!rcm_complete()){rcm_fault=MC_SW_ERROR;return;}
 if(!RCM_conversion_nb||!mic_current_regular_window())return;
 RegConv_t*c=RCM_handle_array[rcm_next];
 if(LL_ADC_REG_IsConversionOngoing(c->regADC)){rcm_fault=MC_SW_ERROR;return;}
 LL_ADC_REG_SetSequencerRanks(c->regADC,LL_ADC_REG_RANK_1,__LL_ADC_DECIMAL_NB_TO_CHANNEL(c->channel));
 (void)LL_ADC_REG_ReadConversionData12L(c->regADC);LL_ADC_ClearFlag_EOC(c->regADC);
 rcm_pending=c;__DMB();LL_ADC_REG_StartConversion(c->regADC);
 rcm_next=(uint8_t)((rcm_next+1U)%RCM_conversion_nb);
}

'''
 s=once(s,anchor,helpers+anchor)
 anchor='uint16_t RCM_ExecRegularConv(RegConv_t *regConv)\n{\n  uint16_t result;'
 s=once(s,anchor,anchor+'''
  if(regConv&&LL_TIM_IsEnabledAllOutputs(TIM1)){
    unsigned id=regConv->id;
    if(id>=RCM_conversion_nb||RCM_handle_array[id]!=regConv||!rcm_valid[id]||
       (uint32_t)(DWT->CYCCNT-rcm_stamp[id])>=SystemCoreClock/1000U)rcm_fault=MC_SW_ERROR;
    return regConv->data;
  }
  /* A RUN conversion may finish after STOP; consume it before changing SQR. */
  while(!rcm_complete()){} /* OFF only; same blocking convention as original */
''')
 anchor='  result = LL_ADC_REG_ReadConversionData12L(regConv->regADC);'
 s=once(s,anchor,anchor+'''
  regConv->data=result;rcm_stamp[regConv->id]=DWT->CYCCNT;
  __DMB();rcm_valid[regConv->id]=1;rcm_fault=0;
''');write(f,s)
 f=OUT/'nucleo/Src/mc_tasks.c';s=read(f)
 s=once(s,'  if(returnValue != MC_NO_ERROR)',
 '  if(returnValue==MC_NO_ERROR&&!RCM_CurrentEpoch())returnValue=MC_SW_ERROR;\n  if(returnValue != MC_NO_ERROR)')
 s=s.replace('  MCI_FaultProcessing(&Mci[bMotor], CodeReturn, ~CodeReturn);',
 '  CodeReturn |= RCM_CurrentFault();\n  MCI_FaultProcessing(&Mci[bMotor], CodeReturn, ~CodeReturn);')
 assert s.count('CodeReturn |= RCM_CurrentFault();')==2
 write(f,s)
 f=OUT/'nucleo/Src/stm32g4xx_mc_it.c';s=read(f)
 s=once(s,'#include "mc_config.h"','#include "mc_config.h"\n#include "regular_conversion_manager.h"')
 s=once(s,'  mic_current_adc_irq();','  mic_current_adc_irq();\n  RCM_ServiceAfterInjected();');write(f,s)
 write(OUT/'manifest.json',json.dumps(dict(pair=list(NEW),base_pair=[2026103003,2026103004],built=False,installed=False,
  trip_current_A=1.35,ADC_guard_ticks=2048,thresholds_changed=False,IRQ_masking_added=False,
  current_feedback_filter_added=False,current_model_changed=False,
  historical_spike_classification='unresolved; shared-ADC scheduling defect corrected, not proven unique cause',
  hardware_commands=0,start_commands=0,clear_commands=0),indent=2)+'\n')
 print('Prepared3005/3006 offline; no hardware access')
if __name__=='__main__':main()
