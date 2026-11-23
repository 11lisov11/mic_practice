"""Prepare deterministic observer service and bounded runtime timing evidence."""
import json,os,re,shutil
from pathlib import Path
from prepare_standstill_commissioning import ROOT,read,write,once
BASE=ROOT/'artifacts/live_bench_20261029/foc_start_epoch_fix_r1'
OUT=ROOT/'artifacts/live_bench_20261029/foc_runtime_fix_r1'
NEW=(2026102971,2026102972)
TEMPLATE=ROOT/'tools/foc_runtime_fix'

def main():
 assert not (OUT/'manifest.json').exists(),'Never overwrite a completed package'
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  def cp(src,dst):
   rel=Path(src).relative_to(BASE/folder)
   if folder=='libraries' or (folder=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full')):
    if Path(dst).exists():assert os.path.samefile(src,dst)
    else:os.link(src,dst)
    return dst
   return shutil.copy2(src,dst)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=cp,dirs_exist_ok=True,
   ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    s=read(f);n=s.replace('2026102961','2026102971').replace('2026102962','2026102972')
    if n!=s:write(f,n)
 for name in ('foc_timing_core.h','foc_timing_irq.h'):write(OUT/'nucleo/Inc'/name,read(TEMPLATE/name))
 for folder in ('nucleo/Inc','UNOQ_MOTOR'):write(OUT/folder/'foc_timing_wire.h',read(TEMPLATE/'foc_timing_wire.h'))
 f=OUT/'nucleo/Inc/multi_native.h';s=once(read(f),'#include <stdint.h>','#include <stdint.h>\n#include "foc_timing_core.h"')
 write(f,once(s,'void ma_native_diag(uint8_t*packet,uint32_t build);','void ma_native_diag(uint8_t*packet,uint32_t build);\nvoid ma_timing_diag(uint8_t*,uint32_t,unsigned);'))
 f=OUT/'nucleo/Src/multi_native.c';s=read(f)
 s=once(s,'int ma_native_prepare(void){',read(TEMPLATE/'native_timing.inc')+'\nint ma_native_prepare(void){')
 s=once(s,'running=0;run_fault=0;fe_trial_done=0;ma_reset','running=0;run_fault=0;fe_trial_done=0;memset(&ma_perf,0,sizeof(ma_perf));ma_perf_off=0;ma_reset')
 s=once(s,'  if(selected==MA_VF)return;\n  if((uint32_t)(now-estimate_cycles)<SystemCoreClock/1000U)return;',
  '  if(selected==MA_VF||!running||run_fault)return;\n  /* Completed16-sample bins define cadence; service immediately when ready. */')
 s=once(s,'  const uint32_t now=DWT->CYCCNT;\n  if(!LL_TIM_IsEnabledAllOutputs(TIM1)){','  if(!LL_TIM_IsEnabledAllOutputs(TIM1)){')
 s=once(s,'  if(dt>.002f){ma_fail(MA_STALE);return;}\n  uint32_t begin=DWT->CYCCNT;',
 '''  if(dt>.002f){ma_fail_at(MA_STALE,FT_OBSERVER_DT,DWT->CYCCNT,&sample,estimate_cycles,stamp,0);return;}
  ft_clock clock_begin=ma_clock_snapshot();ma_observer_begin=clock_begin.now;
  ma_perf.queue=clock_begin.now-stamp;ma_perf.adc_age=clock_begin.now-sample.cycles;
  if(ma_perf.queue>ma_perf.max_queue)ma_perf.max_queue=ma_perf.queue;
  ma_observer_active=1;''')
 s=once(s,'  uint32_t cycles=DWT->CYCCNT-begin;if(cycles>max_observer_cycles)max_observer_cycles=cycles;\n  if(fault){ma_fail((unsigned)fault);return;}\n  ++estimate_seq;',
 '''  ft_clock clock_end=ma_clock_snapshot();ft_measure(&ma_perf,clock_begin,clock_end);
  ma_observer_active=0;
  ma_perf.steps=observer.steps;
  if(ma_perf.wall>max_observer_cycles)max_observer_cycles=ma_perf.wall;
  if(fault){ma_fail_at((unsigned)fault,FT_OBSERVER,clock_end.now,&sample,estimate_cycles,stamp,ma_perf.wall);return;}
  /* Never publish a late estimate after an IRQ has already latched a stop. */
  if(run_fault||!LL_TIM_IsEnabledAllOutputs(TIM1))return;
  ma_perf.result_age=clock_end.now-stamp;
  if(ma_perf.result_age>ma_perf.max_result)ma_perf.max_result=ma_perf.result_age;
  ++estimate_seq;''')
 s=once(s,'  ma_current_sample sample;int got=mic_current_fast(&sample);','  ma_current_sample sample={0};int got=mic_current_fast(&sample);')
 s=once(s,'    ma_fail(MA_STALE);return MC_SW_ERROR;',
 '''    unsigned why=!got?FT_NO_SAMPLE:(!sample.valid||!sample.zero)?FT_ADC_INVALID:
      (uint32_t)(begin-sample.cycles)>=SystemCoreClock*3U/16000U?FT_ADC_AGE:FT_ESTIMATE_AGE;
    ma_fail_at(MA_STALE,why,begin,&sample,est_cycles,bin_cycles,0);return MC_SW_ERROR;''')
 s=once(s,'    ma_fail((unsigned)(fault?fault:MA_STALE));return MC_DURATION;',
 '''    ma_fail_at((unsigned)(fault?fault:MA_STALE),fault?FT_CONTROL:FT_FAST_DURATION,
      begin,&sample,est_cycles,bin_cycles,elapsed);return MC_DURATION;''')
 # Add split diagnostics to OFF profiling without changing its original gate.
 s=once(s,'   const uint32_t begin=DWT->CYCCNT;\n   int rc=ma_observe(&fe_test_observer',
  '   ft_clock split_begin=ma_clock_snapshot();\n   const uint32_t begin=DWT->CYCCNT;\n   int rc=ma_observe(&fe_test_observer')
 s=once(s,'   uint32_t cycles=DWT->CYCCNT-begin;\n   if(cycles>fe_observer_cycles)',
  '   uint32_t cycles=DWT->CYCCNT-begin;\n   ft_clock split_end=ma_clock_snapshot();ft_measure(&ma_perf,split_begin,split_end);\n   ma_perf_off=1;++ma_perf.steps;\n   if(cycles>fe_observer_cycles)')
 write(f,s)
 # Keep V/f unchanged. Its angle (including double fmod) is unused by native FOC.
 f=OUT/'nucleo/Src/mc_tasks.c';s=once(read(f),'  ACIM_VF_CalcAngle(pACIM_VF[M1]);','  /* Scalar angle is computed only in the scalar branch below. */')
 s=once(s,'''  returnValue = ma_native_selected()==1U ? ACIM_VF_Controller(pACIM_VF[M1]) :
      ma_native_fast(pACIM_VF[M1]->fFlux_Freq_Hz);''',
 '''  if(ma_native_selected()==1U){
    ACIM_VF_CalcAngle(pACIM_VF[M1]);
    returnValue=ACIM_VF_Controller(pACIM_VF[M1]);
  }else returnValue=ma_native_fast(pACIM_VF[M1]->fFlux_Freq_Hz);''')
 write(f,s)
 for name,handlers in [('main.c',('DMA2_Channel1_IRQHandler','DMA1_Channel1_IRQHandler','USART1_IRQHandler')),
  ('stm32g4xx_mc_it.c',('ADC1_2_IRQHandler','TIMx_UP_M1_IRQHandler','TIMx_BRK_M1_IRQHandler','USART2_IRQHandler','SysTick_Handler','EXTI15_10_IRQHandler'))]:
  f=OUT/'nucleo/Src'/name;s=read(f)
  anchor='#include "main.h"' if name=='main.c' else '#include "mc_config.h"'
  s=once(s,anchor,anchor+'\n#include "foc_timing_irq.h"')
  for h in handlers:
   pattern=r'(void\s+'+h+r'\s*\(void\)\s*\{)'
   assert len(re.findall(pattern,s))==1,h
   s=re.sub(pattern,r'\1\n  MIC_FOC_IRQ_SCOPE;',s)
  if name=='main.c':
   s=once(s,'    uno_link_poll();\n    ma_native_service();','    ma_native_service();\n    uno_link_poll();')
   s=once(s,'  while (uno_rx_pop(&byte, &flags)) {',
    '  unsigned serviced=0;\n  while (serviced<UV3_FRAME && uno_rx_pop(&byte, &flags)) {\n    ++serviced;')
   s=once(s,'  if (tx_status == HAL_OK) { mic_send_research_page(now_ms);mic_send_break_page(now_ms);mic_send_current_page(now_ms);mic_send_peak_page(now_ms);mic_send_noise_page(now_ms);mic_send_identification(now_ms); }',
    '''  if (tx_status == HAL_OK) {
    ma_native_service();mic_send_research_page(now_ms);
    ma_native_service();mic_send_current_page(now_ms);
    ma_native_service();
    /* Bulk frozen records wait until OFF; sampling/capture and normal control
     * replies continue during RUN. Do not serialize old traces ahead of FOC. */
    if(!LL_TIM_IsEnabledAllOutputs(TIM1)){
      mic_send_break_page(now_ms);mic_send_peak_page(now_ms);
      mic_send_noise_page(now_ms);mic_send_identification(now_ms);
    }
  }''')
   s=once(s,'  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK)last_ms=now_ms;',
    '''  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK){
    last_ms=now_ms;static unsigned timing_page;
    ma_native_service();
    ma_timing_diag(packet,MIC_NUCLEO_FW_BUILD_ID,timing_page);
    if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK)timing_page=(timing_page+1U)%4U;
  }''')
  write(f,s)
 f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
 s=once(s,'static xp_receiver g_research_caps={};','#include "foc_timing_wire.h"\nstatic ft_receiver g_foc_timing={};\nstatic xp_receiver g_research_caps={};')
 s=once(s,'      if(buf[2]==XP_WIRE){',
 '''      if(buf[2]==FT_WIRE){
        const uint32_t now=millis();const bool fresh=g_bp_mcsdk_telemetry&&(uint32_t)(now-g_bp_last_rsp_ms)<300U;
        (void)ft_receive(&g_foc_timing,buf,g_bp_fw_build,fresh,now);continue;
      }
      if(buf[2]==XP_WIRE){''')
 text='''    s += " foc_runtime_valid=";s += String(ft_fresh(&g_foc_timing,native_fresh,millis())?1:0);
    s += " foc_runtime_flags=";s += String((unsigned)g_foc_timing.flags);
    s += " foc_runtime_good=";s += String((unsigned long)g_foc_timing.good);
    s += " foc_runtime_bad=";s += String((unsigned long)g_foc_timing.bad);
'''
 for i in range(28):text+='    s += " foc_runtime_w'+str(i)+'=";s += String((unsigned long)g_foc_timing.words['+str(i)+']);\n'
 s=once(s,'    s += " research_native_valid=";',text+'    s += " research_native_valid=";');write(f,s)
 f=OUT/'web_hmi/server.py';s=read(f)
 text=''.join('                "'+k+'": int(kv.get("'+k+'","0")),\n' for k in
  ['foc_runtime_valid','foc_runtime_flags','foc_runtime_good','foc_runtime_bad']+['foc_runtime_w'+str(i) for i in range(28)])
 s=once(s,'                "research_native_valid":',text+'                "research_native_valid":')
 from foc_runtime_fix.patch_hmi import patch_server,patch_js
 write(f,patch_server(s,TEMPLATE))
 f=OUT/'web_hmi/static/app.js';write(f,patch_js(read(f)))
 f=OUT/'web_hmi/static/index.html';write(f,read(f).replace('2961-foc-start-epoch','2971-foc-runtime'))
 write(OUT/'manifest.json',json.dumps(dict(schema='mic_ai.foc_runtime_fix.v1',pair=list(NEW),
  base_pair=[2026102961,2026102962],built=False,installed=False,
  current_model_changed=False,ADC_source_changed=False,thresholds_changed=False,
  age_limits_changed=False,IRQ_priorities_changed=False,IRQ_masking_added=False,
  observer_math_changed=False,native_autostop_seconds=5,experimental_max_hz=5,
  no_new_motor_tests=True,start_commands=0,clear_commands=0,flash_commands=0),indent=2))
 print('Prepared2971/2972; no hardware access')

if __name__=='__main__':main()
