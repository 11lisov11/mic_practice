"""Coherent regular-ADC age and immutable first-reason record; offline only."""
import json, os, shutil
from pathlib import Path
from prepare_standstill_commissioning import ROOT, read, write, once
BASE=ROOT/'artifacts/live_bench_20261029/foc_regular_adc_fix_r2'
OUT=ROOT/'artifacts/live_bench_20261029/foc_cache_snapshot_fix_r1'
NEW=(2026103007,2026103008)


def main():
 assert not OUT.exists()
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  def cp(src,dst):
   rel=Path(src).relative_to(BASE/folder)
   if folder=='libraries' or (folder=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full')):
    os.link(src,dst);return dst
   return shutil.copy2(src,dst)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=cp,ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    s=read(f);n=s.replace('2026103005','2026103007').replace('2026103006','2026103008').replace('3005-regular-adc','3007-cache-snapshot')
    if n!=s:write(f,n)

 f=OUT/'nucleo/Inc/foc_timing_core.h'
 write(f,once(read(f),'FT_CONTROL=7,FT_OBSERVER=8','FT_CONTROL=7,FT_OBSERVER=8,FT_REGULAR_ADC=9'))
 # Keep the packet format, page CRC and atomic first-writer ownership. The
 # new reason has its own14-word interpretation; it never sets MA_CURRENT.
 f=OUT/'nucleo/Inc/multi_native.h'
 write(f,once(read(f),'void ma_timing_diag(uint8_t*,uint32_t,unsigned);',
  'void ma_timing_diag(uint8_t*,uint32_t,unsigned);\nvoid ma_native_regular_fault(const uint32_t*words);'))
 f=OUT/'nucleo/Src/multi_native.c';s=read(f)
 anchor='void ma_timing_diag(uint8_t*p,uint32_t build,unsigned page){'
 s=once(s,anchor,'''/* First regular-ADC safety failure survives STOP/CLEAR and later faults.
 * RCM latches MC_SW_ERROR independently before calling this recorder. */
void ma_native_regular_fault(const uint32_t*words){
 uint32_t expected=0;
 if(!__atomic_compare_exchange_n(&ma_first_runtime.state,&expected,1,0,__ATOMIC_ACQ_REL,__ATOMIC_RELAXED))return;
 for(unsigned i=0;i<14;++i)ma_first_runtime.word[i]=words[i];
 __DMB();__atomic_store_n(&ma_first_runtime.state,2,__ATOMIC_RELEASE);
}
'''+anchor);write(f,s)

 f=OUT/'nucleo/Src/regular_conversion_manager.c';s=read(f)
 s=once(s,'#include "current_shunt.h"','#include "current_shunt.h"\n#include "multi_native.h"')
 begin=s.index('static RegConv_t *rcm_pending;');end=s.index('/* Private function prototypes',begin)
 helpers='''static RegConv_t *rcm_pending;
static uint8_t rcm_next;
static volatile uint8_t rcm_valid[RCM_MAX_CONV];
static volatile uint32_t rcm_stamp[RCM_MAX_CONV];
static volatile uint16_t rcm_fault;
enum {RCF_CONFIG=1,RCF_INVALID=2,RCF_EXPIRED=3,RCF_CONTENTION=4,
      RCF_NO_EOC=5,RCF_BUSY=6,RCF_HANDLE=7};
static void rcm_fail(unsigned reason,unsigned id,uint32_t now,uint32_t stamp){
 rcm_fault=MC_SW_ERROR; /* existing safety stop, before any diagnostics */
 uint32_t words[14]={FT_REGULAR_ADC,reason,now,stamp,id,now-stamp,
  TIM1->CNT,TIM1->CR1,ADC1->ISR,ADC1->CR,ADC1->SQR1,
  rcm_pending?rcm_pending->id:UINT32_MAX,
  (id<RCM_conversion_nb?rcm_valid[id]:0U)|
   (LL_TIM_IsEnabledAllOutputs(TIM1)?2U:0U),__get_IPSR()};
 /* ISR/CR/SQR are read-only observations here; DR is never touched. */
 ma_native_regular_fault(words);
}
static int rcm_fresh(unsigned id){
 uint32_t stamp=0,now=0;
 for(unsigned retry=0;retry<3;++retry){
  uint32_t valid=rcm_valid[id];stamp=rcm_stamp[id];__DMB();
  now=DWT->CYCCNT;__DMB();
  if(stamp!=rcm_stamp[id])continue;
  if(!valid){rcm_fail(RCF_INVALID,id,now,stamp);return 0;}
  if((uint32_t)(now-stamp)>=SystemCoreClock/1000U){
   rcm_fail(RCF_EXPIRED,id,now,stamp);return 0;
  }
  return 1;
 }
 rcm_fail(RCF_CONTENTION,id,now,stamp);return 0;
}
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
 for(unsigned i=0;i<RCM_conversion_nb;++i){
  RegConv_t*c=RCM_handle_array[i];
  if(c->regADC!=ADC1||c->samplingTime!=LL_ADC_SAMPLINGTIME_47CYCLES_5){
   rcm_fail(RCF_CONFIG,i,DWT->CYCCNT,rcm_stamp[i]);return 0;
  }
  if(!rcm_fresh(i))return 0;
 }
 return 1;
}
void RCM_ServiceAfterInjected(void){
 if(!LL_TIM_IsEnabledAllOutputs(TIM1)||rcm_fault)return;
 if(!rcm_complete()){
  unsigned id=rcm_pending->id;rcm_fail(RCF_NO_EOC,id,DWT->CYCCNT,rcm_stamp[id]);return;
 }
 if(!RCM_conversion_nb||!mic_current_regular_window())return;
 RegConv_t*c=RCM_handle_array[rcm_next];
 if(LL_ADC_REG_IsConversionOngoing(c->regADC)){
  rcm_fail(RCF_BUSY,c->id,DWT->CYCCNT,rcm_stamp[c->id]);return;
 }
 LL_ADC_REG_SetSequencerRanks(c->regADC,LL_ADC_REG_RANK_1,__LL_ADC_DECIMAL_NB_TO_CHANNEL(c->channel));
 (void)LL_ADC_REG_ReadConversionData12L(c->regADC);LL_ADC_ClearFlag_EOC(c->regADC);
 rcm_pending=c;__DMB();LL_ADC_REG_StartConversion(c->regADC);
 rcm_next=(uint8_t)((rcm_next+1U)%RCM_conversion_nb);
}

'''
 s=s[:begin]+helpers+s[end:]
 s=once(s,'''    if(id>=RCM_conversion_nb||RCM_handle_array[id]!=regConv||!rcm_valid[id]||
       (uint32_t)(DWT->CYCCNT-rcm_stamp[id])>=SystemCoreClock/1000U)rcm_fault=MC_SW_ERROR;''',
 '''    if(id>=RCM_conversion_nb||RCM_handle_array[id]!=regConv)
      rcm_fail(RCF_HANDLE,id,DWT->CYCCNT,0);
    else (void)rcm_fresh(id);''')
 write(f,s)

 f=OUT/'web_hmi/server.py';s=read(f)
 s=once(s,"7: 'ошибка регулятора', 8: 'ошибка вычисления наблюдателя'}",
  "7: 'ошибка регулятора', 8: 'ошибка вычисления наблюдателя', 9: 'ошибка регулярного АЦП'}")
 marker="        return {'foc_runtime': dict(available=True, observer_measured=w[0]>0,"
 s=once(s,marker,'''        if flags & 1 and w[14] == 9:
            reasons = {1: 'неподдерживаемая конфигурация АЦП', 2: 'нет готового отсчёта',
                       3: 'возраст отсчёта достиг 1 мс', 4: 'не получен согласованный снимок',
                       5: 'нет EOC предыдущей конверсии', 6: 'АЦП занят перед запуском',
                       7: 'неверный дескриптор канала'}
            sub, ident = w[15], w[18]
            if sub not in reasons or ident not in (0, 1) and sub != 7:
                raise ValueError('invalid regular ADC fault')
            fault = dict(reason_code=9, reason_ru='АЦП: '+reasons[sub], algorithm_fault=0,
                         at_cycles=w[16], regular_adc=dict(reason_code=sub, reason_ru=reasons[sub],
                         id=ident, channel={0:2, 1:8}.get(ident), at_cycles=w[16], stamp_cycles=w[17],
                         age_us=w[19]/170, timer_cnt=w[20], timer_cr1=w[21], adc_isr=w[22],
                         adc_cr=w[23], adc_sqr1=w[24], pending_id=w[25], flags=w[26], ipsr=w[27],
                         age_valid_for_expiry=sub==3))
'''+marker);write(f,s)
 f=OUT/'web_hmi/static/app.js';s=read(f)
 marker='function mcFaultSummary(data, code) {'
 s=once(s,marker,marker+'''
  const regularFault = data.foc_runtime?.first_fault;
  if ((Number(data.mc_fault_current_mask || data.mc_fault_occurred_mask || 0) & 128) &&
      regularFault?.reason_code === 9 && regularFault.regular_adc) {
    return regularFault.reason_ru;
  }
''');write(f,s)
 write(OUT/'manifest.json',json.dumps(dict(pair=list(NEW),base_pair=[2026103005,2026103006],
  built=False,installed=False,current_trip_A=1.35,ADC_guard_ticks=2048,safety_cache_age_ms=1,
  snapshot_max_attempts=3,IRQ_masking_added=False,thresholds_changed=False,
  hardware_commands=0,start_commands=0,clear_commands=0,
  physical_5s_not_proven=True,historical_fault_branch_not_proven=True),indent=2)+'\n')
 print('Prepared3007/3008 offline; installed3005/3006 untouched')


if __name__=='__main__':main()
