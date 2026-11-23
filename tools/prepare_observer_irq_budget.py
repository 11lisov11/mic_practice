"""Offline UART TX IRQ ordering fix and per-vector observer-window evidence."""
import json,os,shutil
from prepare_standstill_commissioning import ROOT,read,write,once
from prepare_cin_sd_diag import sha
BASE=ROOT/'artifacts/live_bench_20261114/current_polarity_budget_r1'
OUT=ROOT/'artifacts/live_bench_20261115/observer_irq_budget_r1'
NEW=(2026111501,2026111502)


def main():
 assert not (OUT/'manifest.json').exists()
 if OUT.exists():assert {f.name for f in OUT.iterdir()} <= {'nucleo','UNOQ_MOTOR','libraries','web_hmi'}
 for rel,h in json.loads(read(BASE/'source_hashes.json')).items():assert sha(BASE/rel)==h,rel
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  def cp(src,dst):
   rel=os.path.relpath(src,BASE/folder).split(os.sep)
   if folder=='libraries' or folder=='nucleo' and rel[0] in ('Drivers','MCSDK_v6.4.2-Full'):
    if os.path.exists(dst):assert os.path.samefile(src,dst)
    else:os.link(src,dst)
    return dst
   return shutil.copy2(src,dst)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=cp,dirs_exist_ok=True,ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    s=read(f);n=s.replace('2026111407',str(NEW[0])).replace('2026111408',str(NEW[1]))
    if n!=s:write(f,n)
 f=OUT/'nucleo/Src/main.c';s=read(f)
 s=once(s,'DMA1_Channel1->CCR |= DMA_CCR_EN|DMA_CCR_TEIE;',
 '''/* DMA TC owns the transition to UART TC. No UART TC interrupt while
     bytes remain in memory, even if the peripheral sees an inter-byte gap. */
  DMA1_Channel1->CCR |= DMA_CCR_EN|DMA_CCR_TEIE|DMA_CCR_TCIE;''')
 s=once(s,'  huart1.Instance->CR1 |= USART_CR1_TCIE;\n}',
 '''  /* TCIE is enabled only by the final DMA transfer-complete IRQ. */
}''')
 s=once(s,'    ++mic_uart_tx.early_tc;return;',
 '''    ++mic_uart_tx.early_tc;
    /* Never clear TC here: a higher IRQ could have delayed this branch until
       after the final stop bit. DMA TC will arm TCIE and observe that level. */
    huart1.Instance->CR1 &= ~USART_CR1_TCIE;return;''')
 s=once(s,'  if(!(flags&8U)) return;',
 '''  if(!(flags&8U)) {
    if((flags&2U) && mic_uart_tx.active && !mic_uart_tx.hard_error &&
       DMA1_Channel1->CNDTR==0U) {
      /* Last byte is now owned by UART. If its stop bit already left while
         this IRQ was delayed, the pending TC level immediately requests IRQ. */
      huart1.Instance->CR1 |= USART_CR1_TCIE;
    }
    return;
  }''')
 # The strict runtime timing protocol gets21 observational words. No guard uses them.
 s=once(s,'timing_page=(timing_page+1U)%6U','timing_page=(timing_page+1U)%9U')
 write(f,s)
 # Instrument each real vector separately; direct C calls to another IRQ handler
 # do not count as another hardware exception. All priorities stay untouched.
 handlers=[('main.c','DMA2_Channel1_IRQHandler','DMA2_Channel1_IRQn'),
  ('main.c','DMA1_Channel1_IRQHandler','DMA1_Channel1_IRQn'),
  ('main.c','USART1_IRQHandler','USART1_IRQn'),
  ('stm32g4xx_mc_it.c','ADC1_2_IRQHandler','ADC1_2_IRQn'),
  ('stm32g4xx_mc_it.c','TIMx_UP_M1_IRQHandler','TIM1_UP_TIM16_IRQn'),
  ('stm32g4xx_mc_it.c','TIMx_BRK_M1_IRQHandler','TIM1_BRK_TIM15_IRQn'),
  ('stm32g4xx_mc_it.c','USART2_IRQHandler','USART2_IRQn'),
  ('stm32g4xx_mc_it.c','SysTick_Handler','SysTick_IRQn'),
  ('stm32g4xx_mc_it.c','EXTI15_10_IRQHandler','EXTI15_10_IRQn')]
 from test_foc_update_latency_fix import function
 for index,(name,fn,irq) in enumerate(handlers):
  f=OUT/'nucleo/Src'/name;s=read(f)
  if fn=='EXTI15_10_IRQHandler':
   assert s.count('EXTI15_10_IRQHandler (void)')==2
   s=s.replace('EXTI15_10_IRQHandler (void)','EXTI15_10_IRQHandler(void)')
  old=function(s,fn)
  new=once(old,'MIC_FOC_IRQ_SCOPE;',f'MIC_FOC_IRQ_SCOPE_NAMED({index},{irq});')
  write(f,once(s,old,new))
 write(OUT/'nucleo/Inc/foc_timing_irq.h',read(ROOT/'tools/observer_irq_budget/foc_timing_irq.h'))
 write(OUT/'nucleo/Inc/irq_breakdown.h',read(ROOT/'tools/observer_irq_budget/irq_breakdown.h'))
 f=OUT/'nucleo/Src/multi_native.c';s=read(f)
 s=once(s,'static ma_motor model=FE_ESTIMATED_MOTOR,staged;',
 '''static ma_motor model=FE_ESTIMATED_MOTOR,staged;
/* Only used after the unchanged per-frame fe_profile_allowed/fe_model_exact
 * check. Constant propagation removes repeated motor-parameter divisions;
 * this is the SAME model, not a guessed replacement or cached validation. */
static const ma_motor fe_control_model=FE_ESTIMATED_MOTOR;''')
 s=once(s,'ft_irq_meter mic_foc_irq_meter;', '''ft_irq_meter mic_foc_irq_meter;
#include "irq_breakdown.h"
ib_meter mic_foc_irq_detail;
static ib_snapshot ma_irq_begin;
static uint32_t ma_irq_last[21],ma_irq_first[21];''')
 s=once(s,' ma_freeze_publication(w+14);',
 ''' ma_freeze_publication(w+14);
 if(ma_observer_active)ib_delta(&mic_foc_irq_detail,&ma_irq_begin,at,ma_irq_first);
 else memcpy(ma_irq_first,ma_irq_last,sizeof(ma_irq_first));''')
 s=once(s,' ma_freeze_publication(ma_first_runtime.word+14);',
 '''  ma_freeze_publication(ma_first_runtime.word+14);
  if(ma_observer_active)ib_delta(&mic_foc_irq_detail,&ma_irq_begin,DWT->CYCCNT,ma_irq_first);
  else memcpy(ma_irq_first,ma_irq_last,sizeof(ma_irq_first));''')
 s=once(s,'  words[0]=ma_perf.wall;', '  words[0]=ma_perf.wall;') # Require the old protocol anchor.
 s=once(s,'uint32_t words[7]={0};page%=6;', 'uint32_t words[7]={0};page%=9;')
 s=once(s,'}else if(complete)memcpy(words,ma_first_runtime.word+(page-2)*7,sizeof(words));',
 '''}else if(page<6){if(complete)memcpy(words,ma_first_runtime.word+(page-2)*7,sizeof(words));}
 else memcpy(words,(complete?ma_irq_first:ma_irq_last)+(page-6)*7,sizeof(words));''')
 s=once(s,'p[2]=0xE8;p[3]=2;', 'p[2]=0xE8;p[3]=3;')
 s=once(s,'  ma_observer_active=1;ma_observer_stage=EP_COMPUTE;ma_input_bin=stamp;',
 '''  ib_read(&mic_foc_irq_detail,&ma_irq_begin,clock_begin.now);
  ma_observer_active=1;ma_observer_stage=EP_COMPUTE;ma_input_bin=stamp;''')
 s=once(s,'  ma_observer_active=0;\n  ma_perf.steps=observer.steps;',
 '''  ib_delta(&mic_foc_irq_detail,&ma_irq_begin,clock_end.now,ma_irq_last);
  ma_observer_active=0;
  ma_perf.steps=observer.steps;''')
 s=once(s,'running=0;run_fault=0;fe_trial_done=0;memset(&ma_perf,0,sizeof(ma_perf));',
 '''running=0;run_fault=0;fe_trial_done=0;memset(&ma_perf,0,sizeof(ma_perf));
  memset(ma_irq_last,0,sizeof(ma_irq_last));''')
 a=s.index('  int fault=ma_control_checked(',s.index('uint16_t ma_native_fast('))
 b=s.index('  if(!fault && voltage_fault)',a)
 call=s[a:b]
 fixed=call.replace('  int fault=','    fault=').replace('&controller,&model,','&controller,&fe_control_model,')
 dynamic=call.replace('  int fault=','    fault=')
 s=s[:a]+'  int fault;\n  if(qualification==FE_ESTIMATED){\n'+fixed+'  }else{\n'+dynamic+'  }\n'+s[b:]
 s=once(s,'fe_rc=avrc?avrc:ma_control(&fe_test_controller,&model,',
 '''const int model_ok=fe_model_exact(&model);
 fe_rc=avrc?avrc:ma_control_checked(&fe_test_controller,&fe_control_model,''')
 s=once(s,'fe_test_ia,fe_test_ib,fe_test_ref,fe_test_bus,1.f/16000U,1,&fe_test_out);',
        'fe_test_ia,fe_test_ib,fe_test_ref,fe_test_bus,1.f/16000U,1,&fe_test_out,model_ok);')
 write(f,s)
 # Remove calculations whose result was always overwritten during magnetisation.
 # Keep the exact original expressions/order whenever the speed loop is active.
 f=OUT/'nucleo/Inc/motor_control.h';s=read(f)
 s=once(s,'static inline int ma_control_checked(',
        'static inline __attribute__((always_inline)) int ma_control_checked(')
 s=once(s,'  float a[6][6],f[6][6],tmp[6][6],cov[6][6];',
 '''  float a[6][6],f[6][6],tmp[6][6];
  /* The Jacobian is dead after F is built. Reuse its144-byte workspace for
     covariance; no arithmetic order changes and no shared/static scratch. */
  float (*cov)[6]=a;''')
 s=once(s,'    memcpy(cov,tmp,sizeof(cov));','    memcpy(cov,tmp,sizeof(a));')
 a=s.index('  const float iqmax=',s.index('static inline int ma_control_checked'))
 b=s.index('  const float err[2]',a)
 old=s[a:b]
 new=old.replace('  float iqref=ma_clip(raw/tqgain,-iqmax,iqmax);','  iqref=ma_clip(raw/tqgain,-iqmax,iqmax);')
 new=new.replace('  if(c->time_s<.35f){iqref=0;c->speed_integral=0;}\n','')
 new='  float iqref=0;\n  if(c->time_s<.35f)c->speed_integral=0;\n  else {\n'+new+'  }\n'
 write(f,s[:a]+new+s[b:])
 for folder in ('nucleo/Inc','UNOQ_MOTOR'):
  f=OUT/folder/'foc_timing_wire.h';s=read(f)
  s=s.replace('FT_FORMAT=2,FT_PAGES=6','FT_FORMAT=3,FT_PAGES=9').replace('words[42]','words[63]')
  s=s.replace('uint8_t mask,flags;','uint16_t mask;uint8_t flags;').replace('(uint8_t)(1U<<p[4])','(uint16_t)(1U<<p[4])')
  write(f,s)
 f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
 anchor='    s += " foc_runtime_w41=";s += String((unsigned long)g_foc_timing.words[41]);'
 addition='\n'.join(f'    s += " foc_runtime_w{i}=";s += String((unsigned long)g_foc_timing.words[{i}]);' for i in range(42,63))
 write(f,once(s,anchor,anchor+'\n'+addition))
 f=OUT/'web_hmi/server.py';s=read(f)
 anchor='                "foc_runtime_w41": int(kv.get("foc_runtime_w41","0")),'
 if anchor not in s:
  import re
  match=re.search(r'^.*"foc_runtime_w41".*$',s,re.M);assert match
  anchor=match[0]
 extra='\n'.join(f'                "foc_runtime_w{i}": int(kv.get("foc_runtime_w{i}","0")),' for i in range(42,63))
 s=once(s,anchor,anchor+'\n'+extra)
 # Add a named, explicitly inclusive breakdown without changing existing timing fields.
 s=once(s,'def foc_runtime_status(kv):',read(ROOT/'tools/observer_irq_budget/hmi_irq_decode.inc')+'\n\ndef foc_runtime_status(kv):')
 s=once(s,'observer_steps=w[12], meter_errors=w[13], first_fault=fault,',
        'observer_steps=w[12], meter_errors=w[13], first_fault=fault, IRQ_breakdown=irq_breakdown_status(kv,fault),')
 write(f,s)
 preserved=json.loads(read(BASE/'preserved_capture_hashes.json'))
 for f in BASE.rglob('*'):
  if f.is_file() and f.suffix in ('.json','.jsonl','.bin','.log','.txt','.png'):
   preserved[f.relative_to(ROOT).as_posix()]=sha(f)
 write(OUT/'preserved_capture_hashes.json',json.dumps(preserved,indent=2)+'\n')
 m=json.loads(read(BASE/'manifest.json'))
 m.update(pair=list(NEW),base_pair=[2026111407,2026111408],built=False,installed=False,
          hardware_commands=0,START=0,CLEAR=0,ARM=0,RESET=0,thresholds_changed=False,
          target_timing_measured=False,OFF_CPU_qualified=False,FOC_start_ready=False,
          target_timing_requalification_required=True,full_adapter_under_PWM_measured=False,
          hardware_validated=False,IRQ_breakdown_inclusive=True)
 for key in ('artifacts','source_files','preserved_files_verified','verification_reports','RAM_sections',
             'RAM_allocated','RAM_unallocated','installation_report','idle_timing_report','timing_block',
             'both_readbacks_verified','native_flash_bytes','hex_padding_offsets','host_tests_passed','model_tests_passed'):
  m.pop(key,None)
 write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
 print('Prepared offline',NEW)


if __name__=='__main__':main()
