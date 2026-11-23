"""Reproduce a preempted freshness read in actual3006 C; no hardware access."""
import json
import prepare_foc_regular_adc_fix as p
import test_foc_runtime_fix as common
from test_foc_update_latency_fix import function


def main():
    out = p.OUT/'powered_FOC_ADC_20261030_r2'
    assert not (out/'timestamp_race_replay.json').exists()
    common.p = p
    src = p.read(p.OUT/'nucleo/Src/regular_conversion_manager.c')
    helpers = src[src.index('static RegConv_t *rcm_pending;'):src.index('/* Private function prototypes')]
    original = function(src, 'RCM_ExecRegularConv')
    pre = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#define __DMB() __asm__ volatile("":::"memory")
#define MC_SW_ERROR 128
#define LL_ADC_SAMPLINGTIME_47CYCLES_5 4
#define LL_ADC_REG_RANK_1 1
#define __LL_ADC_DECIMAL_NB_TO_CHANNEL(c) (c)
#define RCM_MAX_CONV 4
static uint32_t clock_now=1000000,*interrupt_stamp;
static bool inject;
struct CounterRead{
 operator uint32_t()const{
  uint32_t saved=clock_now;
  // Exact ARM interleaving: load CYCCNT, higher-priority ADC IRQ publishes
  // a newer stamp, resume SysTick and load that stamp.
  if(inject){inject=false;*interrupt_stamp=saved+64;clock_now=saved+128;}
  return saved;
 }
};
static struct{CounterRead CYCCNT;}clock_;static auto DWT=&clock_;
static uint32_t SystemCoreClock=170000000;
struct ADC_TypeDef{};static ADC_TypeDef adc;static auto ADC1=&adc;
struct RegConv_t{ADC_TypeDef*regADC;uint32_t samplingTime;uint8_t channel;uint16_t data;uint8_t id;};
static RegConv_t*RCM_handle_array[RCM_MAX_CONV];static uint8_t RCM_conversion_nb=1;
static int TIM1;
static int LL_TIM_IsEnabledAllOutputs(int){return 1;}
static int LL_ADC_IsActiveFlag_EOC(ADC_TypeDef*){return 1;}
static int LL_ADC_REG_IsConversionOngoing(ADC_TypeDef*){return 0;}
static uint16_t LL_ADC_REG_ReadConversionData12L(ADC_TypeDef*){return 3200;}
static void LL_ADC_ClearFlag_EOC(ADC_TypeDef*){}
static void LL_ADC_REG_SetSequencerRanks(ADC_TypeDef*,int,unsigned){}
static void LL_ADC_REG_StartConversion(ADC_TypeDef*){}
static int mic_current_regular_window(){return 1;}
'''
    proposed = r'''
// Candidate only: bounded coherent read, same1ms expiry, no IRQ masking.
static bool rcm_cache_fresh(unsigned id){
 for(unsigned n=0;n<3;++n){
  uint32_t stamp=*(volatile uint32_t*)&rcm_stamp[id];__DMB();
  uint32_t now=DWT->CYCCNT;__DMB();
  if(stamp==*(volatile uint32_t*)&rcm_stamp[id])
   return (uint32_t)(now-stamp)<SystemCoreClock/1000U;
 }
 return false;
}
'''
    old_age = '(uint32_t)(DWT->CYCCNT-rcm_stamp[id])>=SystemCoreClock/1000U'
    assert old_age in original
    fixed = original.replace('RCM_ExecRegularConv(', 'candidate_ExecRegularConv(', 1).replace(old_age, '!rcm_cache_fresh(id)')
    checks = r'''
int main(){
 RegConv_t c={ADC1,4,2,3200,0};RCM_handle_array[0]=&c;
 rcm_valid[0]=1;interrupt_stamp=&rcm_stamp[0];
 rcm_stamp[0]=clock_now-200;inject=true;
 assert(RCM_ExecRegularConv(&c)==3200);
 assert(rcm_fault==128); // old code rejects a cache just refreshed byADC
 uint32_t apparent_age=(uint32_t)(1000000U-1000064U);
 rcm_fault=0;clock_now=1000000;rcm_stamp[0]=clock_now-200;inject=true;
 assert(candidate_ExecRegularConv(&c)==3200&&rcm_fault==0);
 // Expired data is still rejected, exactly at the original1ms boundary.
 for(unsigned age: {169999U,170000U,170001U}){
  clock_now=1000000;rcm_stamp[0]=clock_now-age;rcm_fault=0;
  candidate_ExecRegularConv(&c);assert((rcm_fault==128)==(age>=170000));
 }
 clock_now=0x100;rcm_stamp[0]=0xfffffff0U;rcm_fault=0;
 candidate_ExecRegularConv(&c);assert(rcm_fault==0);
 printf("old_false_trip=128 apparent_age=%u fixed_coherent_read=OK expiry1ms=unchanged wrap=OK\n",apparent_age);
}
'''
    result = common.compile_run(out, 'timestamp_race_replay', pre+'\n#include <initializer_list>\n'+helpers+original+proposed+fixed+checks)
    arm = p.read(p.OUT/'verification/regular_ADC_ARM.txt')
    assert '8010f3e:' in arm and '8010f42:' in arm
    report = dict(actual_3006_C_false_trip_reproduced=True,
                  compiled_ARM_load_order=['0x08010f3e CYCCNT','0x08010f42 cached timestamp'],
                  higher_priority_ADC_preempts_SysTick=True,
                  apparent_age_cycles=4294967232, real_cache_fresh=True,
                  proposed_coherent_snapshot_passed=True,
                  actual_historical_fault_branch_not_recorded=True,
                  cannot_uniquely_attribute_physical_stop=True,
                  unchanged_cache_age_limit_cycles=170000, trip_A=1.35, ADC_guard_ticks=2048,
                  installed_firmware_modified=False, hardware_commands=0,
                  result=result.strip())
    p.write(out/'timestamp_race_replay.json',json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':
    main()
