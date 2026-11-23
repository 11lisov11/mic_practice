"""Publish observer results before accounting via an atomic two-slot handoff."""
import json,os,shutil
from pathlib import Path
from prepare_standstill_commissioning import ROOT,read,write,once
BASE=ROOT/'artifacts/live_bench_20261029/foc_cache_snapshot_fix_r1'
OUT=ROOT/'artifacts/live_bench_20261029/foc_estimate_publish_fix_r2'
NEW=(2026103009,2026103010)

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
    s=read(f);n=s.replace('2026103007','2026103009').replace('2026103008','2026103010').replace('3007-cache-snapshot','3009-estimate-publish')
    if n!=s:write(f,n)
 f=OUT/'nucleo/Src/multi_native.c';s=read(f)
 s=once(s,'''static volatile uint32_t estimate_seq;
static volatile float estimate[6];
static volatile uint32_t estimate_cycles;''','''/* Single foreground writer; highest-priority TIM1 reader cannot be preempted
 * by that writer. Only a complete inactive slot is published, in one store. */
typedef struct {float x[6];uint32_t stamp;} ma_estimate_slot;
static ma_estimate_slot estimate_slot[2];
static uint32_t estimate_index;
static volatile uint32_t estimate_cycles;
enum {EP_IDLE=0,EP_COMPUTE=1,EP_COPY=2,EP_COMMITTED=3,EP_ACCOUNTING=4,EP_ABORTED=5};
static volatile uint32_t ma_observer_stage,ma_observer_done_cycles,ma_commit_mark_cycles,ma_input_bin;
static void ma_estimate_reset(uint32_t stamp){
 memset(estimate_slot,0,sizeof(estimate_slot));
 estimate_slot[0].stamp=estimate_slot[1].stamp=stamp;
 __atomic_store_n(&estimate_index,0,__ATOMIC_RELEASE);estimate_cycles=stamp;
 ma_observer_stage=EP_IDLE;ma_observer_done_cycles=ma_commit_mark_cycles=ma_input_bin=0;
}
static int ma_estimate_publish(const float*x,uint32_t stamp){
 if(run_fault||!LL_TIM_IsEnabledAllOutputs(TIM1))return 0;
 unsigned next=__atomic_load_n(&estimate_index,__ATOMIC_RELAXED)^1U;
 ma_observer_stage=EP_COPY;
 for(unsigned i=0;i<6;++i)estimate_slot[next].x[i]=x[i];
 estimate_slot[next].stamp=stamp;
 __DMB();if(run_fault||!LL_TIM_IsEnabledAllOutputs(TIM1))return 0;
 ma_commit_mark_cycles=DWT->CYCCNT;
 __atomic_store_n(&estimate_index,next,__ATOMIC_RELEASE);
 estimate_cycles=stamp;ma_observer_stage=EP_COMMITTED;return 1;
}
static uint32_t ma_estimate_read(float*x){
 unsigned index=__atomic_load_n(&estimate_index,__ATOMIC_ACQUIRE);
 for(unsigned i=0;i<6;++i)x[i]=estimate_slot[index].x[i];
 return estimate_slot[index].stamp;
}
static void ma_freeze_publication(uint32_t*w){
 unsigned index=__atomic_load_n(&estimate_index,__ATOMIC_ACQUIRE);
 w[0]=1;w[1]=ma_observer_stage;w[2]=ma_observer_done_cycles;w[3]=ma_commit_mark_cycles;
 w[4]=index;w[5]=estimate_slot[0].stamp;w[6]=estimate_slot[1].stamp;
 w[7]=ma_input_bin;w[8]=estimate_cycles;w[9]=ma_perf_steps_placeholder;
 w[10]=observer.steps;w[11]=bin_cycles;w[12]=telemetry_seq;
 w[13]=__atomic_load_n(&estimate_index,__ATOMIC_ACQUIRE);
}''')
 # Helpers that mention later-declared telemetry/performance globals belong
 # after those definitions; the publication reader itself has no such dependency.
 begin=s.index('static void ma_freeze_publication(');end=s.index('\n}',begin)+2
 freeze=s[begin:end].replace('ma_perf_steps_placeholder','ma_perf.steps');s=s[:begin]+s[end:]
 s=once(s,'static volatile uint8_t ma_observer_active;', 'static volatile uint8_t ma_observer_active;\n'+freeze)
 s=once(s,'static float cached_estimate[6];\nstatic uint32_t cached_estimate_cycles;','')
 s=once(s,' w[12]=elapsed;w[13]=observer.steps;',
  ' w[12]=elapsed;w[13]=observer.steps;\n ma_freeze_publication(w+14);')
 # The regular-ADC recorder uses the same atomic first-owner state.
 anchor=' for(unsigned i=0;i<14;++i)ma_first_runtime.word[i]=words[i];'
 s=once(s,anchor,anchor+'\n ma_freeze_publication(ma_first_runtime.word+14);')
 s=once(s,'uint32_t words[7]={0};page%=4;','uint32_t words[7]={0};page%=6;')
 s=once(s,'p[2]=0xE8;p[3]=1;','p[2]=0xE8;p[3]=2;')
 s=once(s,'''  ++estimate_seq;__DMB();for(unsigned i=0;i<6;i++)estimate[i]=0;
  estimate_cycles=DWT->CYCCNT;__DMB();++estimate_seq;''','''  ma_estimate_reset(DWT->CYCCNT);''')
 s=once(s,'''  memset(&cached_sample,0,sizeof(cached_sample));memset(cached_estimate,0,sizeof(cached_estimate));
  cached_estimate_cycles=estimate_cycles;return 1;''','''  memset(&cached_sample,0,sizeof(cached_sample));return 1;''')
 s=once(s,'''    estimate_seq++;for(unsigned i=0;i<6;i++)estimate[i]=0;
    estimate_cycles=DWT->CYCCNT;estimate_seq++;''','''    ma_estimate_reset(DWT->CYCCNT);''')
 s=once(s,'  ma_observer_active=1;','  ma_observer_active=1;ma_observer_stage=EP_COMPUTE;ma_input_bin=stamp;')
 marker='  ft_clock clock_end=ma_clock_snapshot();ft_measure(&ma_perf,clock_begin,clock_end);'
 s=once(s,marker,'''  ma_observer_done_cycles=DWT->CYCCNT;
  /* Publish a successfully calculated state before IRQ/performance bookkeeping.
   * Its age remains anchored to the measured input bin, never to this instant. */
  int published=!fault&&ma_estimate_publish(observer.x,stamp);
  ma_observer_stage=published?EP_ACCOUNTING:EP_ABORTED;
'''+marker)
 s=once(s,'''  /* Never publish a late estimate after an IRQ has already latched a stop. */
  if(run_fault||!LL_TIM_IsEnabledAllOutputs(TIM1))return;''','''  if(!published||run_fault||!LL_TIM_IsEnabledAllOutputs(TIM1))return;''')
 s=once(s,'''  ++estimate_seq;__DMB();for(unsigned i=0;i<6;i++)estimate[i]=observer.x[i];
  estimate_cycles=stamp;__DMB();++estimate_seq;''','''  ma_observer_stage=EP_IDLE;''')
 s=once(s,'    running=1;estimate_cycles=begin;start_cycles=begin;',
  '''    running=1;estimate_cycles=begin;start_cycles=begin;
    estimate_slot[__atomic_load_n(&estimate_index,__ATOMIC_RELAXED)].stamp=begin;''')
 begin=s.index('  float x[6];uint32_t seq=estimate_seq;');end=s.index('\n  int fresh=',begin)
 s=s[:begin]+'''  float x[6];uint32_t est_cycles=ma_estimate_read(x);
  const int coherent=1; /* whole published slot, no odd-sequence fallback */'''+s[end:]
 assert 'cached_estimate' not in s and 'estimate_seq' not in s
 write(f,s)
 f=OUT/'nucleo/Inc/foc_timing_core.h';write(f,once(read(f),'state,word[14]','state,word[28]'))
 for folder in ('nucleo/Inc','UNOQ_MOTOR'):
  f=OUT/folder/'foc_timing_wire.h';s=read(f)
  s=once(s,'FT_FORMAT=1,FT_PAGES=4','FT_FORMAT=2,FT_PAGES=6')
  s=once(s,'words[28]','words[42]')
  s=once(s,'r->mask==15','r->mask==((1U<<FT_PAGES)-1U)');write(f,s)
 f=OUT/'nucleo/Src/main.c';s=read(f)
 s=once(s,'    ma_timing_diag(packet,MIC_NUCLEO_FW_BUILD_ID,timing_page);',
  '    if(!LL_TIM_IsEnabledAllOutputs(TIM1)){\n    ma_timing_diag(packet,MIC_NUCLEO_FW_BUILD_ID,timing_page);')
 s=once(s,'timing_page=(timing_page+1U)%4U;', 'timing_page=(timing_page+1U)%6U;\n      }')
 write(f,s)
 f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
 anchor='    s += " foc_runtime_w27=";s += String((unsigned long)g_foc_timing.words[27]);'
 extra=''.join('\n    s += " foc_runtime_w'+str(i)+'=";s += String((unsigned long)g_foc_timing.words['+str(i)+']);' for i in range(28,42))
 write(f,once(s,anchor,anchor+extra))
 f=OUT/'web_hmi/server.py';s=read(f)
 s=once(s,"for i in range(28)]","for i in range(42)]")
 marker="        return {'foc_runtime': dict(available=True, observer_measured=w[0]>0,"
 s=once(s,marker,'''        if fault is not None:
            if w[28] != 1 or w[29] not in range(6) or w[32] not in (0,1) or w[41] not in (0,1):
                raise ValueError('invalid observer publication record')
            fault['publication'] = dict(schema=w[28],stage=w[29],
                stage_name=['idle','compute','copy_inactive','committed','accounting','aborted'][w[29]],
                done_mark_cycles=w[30],commit_mark_cycles=w[31],published_index=w[32],
                slot_stamps=w[33:35],input_bin_cycles=w[35],foreground_stamp=w[36],
                measured_steps=w[37],math_steps=w[38],voltage_bin_cycles=w[39],
                voltage_sequence=w[40],index_after=w[41],index_stable=w[32]==w[41],
                limitation='Diagnostic marks, not an exemption from the unchanged2ms age limit')
'''+marker)
 anchor='                "foc_runtime_w27": int(kv.get("foc_runtime_w27","0")),'
 extra=''.join('\n                "foc_runtime_w'+str(i)+'": int(kv.get("foc_runtime_w'+str(i)+'","0")),' for i in range(28,42))
 s=once(s,anchor,anchor+extra);write(f,s)
 write(OUT/'manifest.json',json.dumps(dict(pair=list(NEW),base_pair=[2026103007,2026103008],built=False,installed=False,
  trip_current_A=1.35,ADC_guard_ticks=2048,estimate_age_limit_ms=2,safety_cache_age_ms=1,
  IRQ_masking_added=False,thresholds_changed=False,hardware_commands=0,start_commands=0,clear_commands=0,
  physical_5s_not_proven=True,historical_publication_stage_not_recorded=True,
  first_fault_publication_metadata=True,observer_math_changed=False,FOC_kernel_changed=False),indent=2)+'\n')
 print('Prepared3009/3010 offline; no hardware access')

if __name__=='__main__':main()
