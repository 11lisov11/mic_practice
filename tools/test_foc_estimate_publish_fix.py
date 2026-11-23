"""Recorded C interleaving, atomic-slot interrupts, real guards and wire tests."""
import json,subprocess,math
import prepare_foc_estimate_publish_fix as p
import test_foc_runtime_fix as common
from test_foc_update_latency_fix import function

def native_source(folder,hook=True):
 s=p.read(folder/'nucleo/Src/multi_native.c')
 for name in ('ma_native_profile_tick','fe_profile_tick','fe_profile_service'):
  f=function(s,name);s=s.replace(f,f.replace('DWT->CYCCNT','host_profile_clock()'))
 if hook:s=s.replace('  ma_observer_active=0;','  ma_observer_active=0;host_publication_irq();')
 return '\n'.join(line for line in s.splitlines() if not line.startswith(('#include','#pragma')))

def main():
 out=p.OUT/'verification';out.mkdir(exist_ok=True);common.p=p
 captured=json.loads(p.read(p.BASE/'powered_FOC_ADC_20261030_r2/analysis.json'))
 t=captured['CPU_IRQ'];f=t['first_fault'];pub=captured['publication_analysis']
 at=f['at_cycles'];done=pub['last_clock_end'];stamp=pub['inferred_observer_input_bin'];old=f['estimate_cycles']
 pre=p.read(p.ROOT/'artifacts/live_bench_20261029/foc_runtime_fix_r1/verification/native_runtime.cpp').split('#define MIC_NATIVE_BUILD',1)[0]
 prototype='''static void host_publication_irq();
static int host_observe(ma_observer*,const ma_motor*,float,float,float,float,float);
#define ma_observe host_observe
'''
 constants=f'''\nstatic const uint32_t CAP_AT={at}U,CAP_DONE={done}U,CAP_INPUT={stamp}U,CAP_OLD={old}U,
 CAP_BEGIN={f['observer_begin_cycles']}U,CAP_ADC={f['adc_cycles']}U,CAP_BIN={f['bin_cycles']}U;
'''
 body=r'''
#undef ma_observe
static bool checkpoint=true,external_stop;
static int irq_rc;
static void NVIC_SetPendingIRQ(int irq){assert(irq==25);++kicks;ma_native_profile_tick();}
static int host_observe(ma_observer*o,const ma_motor*m,float a,float b,float va,float vb,float dt){
 int rc=ma_observe(o,m,a,b,va,vb,dt);assert(!rc);
 cycle.CYCCNT=CAP_DONE;mic_foc_irq_meter.cycles+=96909U;
 if(external_stop){run_fault=MA_STALE;timer.BDTR=0;}
 return rc;
}
static void host_publication_irq(){
 if(!checkpoint)return;checkpoint=false;cycle.CYCCNT=CAP_AT;
 sample.cycles=CAP_ADC;sample.sequence=52261478;sample.counts[0]=-3;sample.counts[1]=-8;sample.counts[2]=11;
 sample.valid=sample.zero=1;bin_cycles=CAP_BIN;
 if(timer.BDTR){irq_rc=ma_native_fast(0);if(irq_rc)timer.BDTR=0;}
}
static void setup(uint32_t input,uint32_t prior){
 timer.BDTR=0;selected=MA_FOC;profile_ready=1;qualification=FE_ESTIMATED;
 running=1;run_fault=first_fault=0;fe_complete=1;fe_started=1;fe_fault=0;fe_case=64;
 id_profile_attempted=1;id_profile_running=0;fe_trial_done=0;
 ma_reset(&observer,&controller);observer.steps=49;
 memset(&ma_first_runtime,0,sizeof(ma_first_runtime));memset(&ma_perf,0,sizeof(ma_perf));
 memset(&mic_foc_irq_meter,0,sizeof(mic_foc_irq_meter));ma_perf_off=0;
 SEED_ESTIMATE
 cycle.CYCCNT=CAP_BEGIN;sample={};sample.valid=sample.zero=1;sample_coherent=1;
 sample.cycles=CAP_BEGIN-4064;sample.counts[0]=-3;sample.counts[1]=-8;sample.counts[2]=11;
 bin_cycles=input;bin_va=bin_vb=0;telemetry_seq=0;fake_bus=323;timer.BDTR=1;
 start_cycles=fe_trial_begin=CAP_AT-8500000U;checkpoint=true;external_stop=false;irq_rc=0;
}
int main(){
 setup(CAP_INPUT,CAP_OLD);ma_native_service();
 CAPTURE_ASSERT
 ADDITIONAL_CHECKS
 puts("actual native C recorded timeline and2ms safety checks OK");
}
'''
 results={}
 for label,folder in [('legacy',p.BASE),('candidate',p.OUT)]:
  if label=='legacy':
   seed='estimate_seq=0;for(auto&v:estimate)v=0;estimate_cycles=prior;cached_estimate_cycles=prior;memset(cached_estimate,0,sizeof(cached_estimate));'
   assertion='assert(irq_rc==MC_SW_ERROR&&run_fault==MA_STALE&&!timer.BDTR&&ma_first_runtime.word[0]==FT_ESTIMATE_AGE);'
   extra=''
  else:
   seed='ma_estimate_reset(prior);'
   assertion='assert(!irq_rc&&!run_fault&&timer.BDTR&&estimate_cycles==CAP_INPUT&&ma_first_runtime.state==0);'
   extra=r'''
 // A2ms old NEW result still trips; no timestamp refresh or grace window.
 setup(CAP_AT-340000U,CAP_AT-510000U);ma_native_service();
 assert(irq_rc==MC_SW_ERROR&&run_fault==MA_STALE&&!timer.BDTR);
 assert(ma_first_runtime.word[0]==FT_ESTIMATE_AGE&&ma_first_runtime.word[14]==1);
 assert(ma_first_runtime.word[15]==EP_ACCOUNTING);
 auto frozen=ma_first_runtime;ma_fail_at(MA_CURRENT,FT_CONTROL,0,nullptr,0,0,0);
 assert(memcmp(&frozen,&ma_first_runtime,sizeof(frozen))==0);
 // The actual six-page packet carries the frozen publication context.
 uint8_t packet[UV3_FRAME];ft_receiver receiver={};
 for(unsigned page=0;page<FT_PAGES;++page){
  ma_timing_diag(packet,2026103010,page);assert(ft_receive(&receiver,packet,2026103010,true,10));
 }
 assert(ft_fresh(&receiver,true,10)&&receiver.mask==63);
 assert(receiver.words[28]==1&&receiver.words[29]==EP_ACCOUNTING);
 packet[10]^=1;assert(!ft_receive(&receiver,packet,2026103010,true,10));
 ma_timing_diag(packet,2026103010,0);assert(!ft_receive(&receiver,packet,2026103008,true,10));
 packet[3]=1;uv3_seal(packet);assert(!ft_receive(&receiver,packet,2026103010,true,10));
 FILE*file=fopen("publication_wire_words.txt","w");assert(file);
 for(auto v:receiver.words)fprintf(file,"%u ",v);fclose(file);
 setup(CAP_INPUT,CAP_OLD);external_stop=true;checkpoint=false;ma_native_service();
 assert(!timer.BDTR&&estimate_cycles==CAP_OLD&&ma_observer_stage==EP_ABORTED);
 FILE*rcf=fopen("regular_publication_words.txt","w");assert(rcf);
 for(unsigned sub=1;sub<=7;++sub){
  memset(&ma_first_runtime,0,sizeof(ma_first_runtime));
  uint32_t words[14]={FT_REGULAR_ADC,sub,CAP_AT,CAP_INPUT,0,CAP_AT-CAP_INPUT};
  ma_native_regular_fault(words);assert(ma_first_runtime.state==2);
  ft_receiver wire={};
  for(unsigned page=0;page<FT_PAGES;++page){ma_timing_diag(packet,2026103010,page);assert(ft_receive(&wire,packet,2026103010,true,10));}
  assert(ft_fresh(&wire,true,10));for(auto v:wire.words)fprintf(rcf,"%u ",v);fprintf(rcf,"\n");
 }
 fclose(rcf);
'''
  code=pre+'\n#include <cstdio>\n#include "foc_timing_wire.h"\n'+prototype+native_source(folder)+constants+body.replace('SEED_ESTIMATE',seed).replace('CAPTURE_ASSERT',assertion).replace('ADDITIONAL_CHECKS',extra)
  cwd=__import__('os').getcwd()
  try:
   __import__('os').chdir(out)
   results[label]=common.compile_run(out,'recorded_'+label,code).strip()
  finally:__import__('os').chdir(cwd)

 # Interrupt every payload store, the stamp store, and the atomic handoff.
 src=p.read(p.OUT/'nucleo/Src/multi_native.c')
 publish=function(src,'ma_estimate_publish')
 publish=publish.replace('for(unsigned i=0;i<6;++i)estimate_slot[next].x[i]=x[i];',
  'for(unsigned i=0;i<6;++i){estimate_slot[next].x[i]=x[i];read_irq();}')
 publish=publish.replace('estimate_slot[next].stamp=stamp;','estimate_slot[next].stamp=stamp;read_irq();')
 publish=publish.replace('__atomic_store_n(&estimate_index,next,__ATOMIC_RELEASE);',
  '__atomic_store_n(&estimate_index,next,__ATOMIC_RELEASE);read_irq();')
 slot_pre=r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
static void __DMB(){__asm__ volatile("":::"memory");}
struct Timer{};static Timer timer;static auto TIM1=&timer;
static bool enabled=1,run_fault;static int LL_TIM_IsEnabledAllOutputs(Timer*){return enabled;}
static struct{uint32_t CYCCNT=1000;}clock_;static auto DWT=&clock_;
typedef struct{float x[6];uint32_t stamp;}ma_estimate_slot;
static ma_estimate_slot estimate_slot[2];static uint32_t estimate_index,estimate_cycles;
enum {EP_COPY=2,EP_COMMITTED=3};static uint32_t ma_observer_stage,ma_commit_mark_cycles;
static void read_irq();static uint32_t reads,old_stamp,new_stamp;static float old_x[6],new_x[6];
'''
 slot_body=r'''
static void read_irq(){
 float x[6];auto stamp=ma_estimate_read(x);++reads;
 bool old=stamp==old_stamp;assert(old||stamp==new_stamp);
 for(unsigned i=0;i<6;++i)assert(x[i]==(old?old_x[i]:new_x[i]));
}
int main(){
 for(unsigned epoch=1;epoch<=10000;++epoch){
  old_stamp=estimate_slot[estimate_index].stamp;memcpy(old_x,estimate_slot[estimate_index].x,sizeof(old_x));
  new_stamp=epoch*169984U;for(unsigned i=0;i<6;++i)new_x[i]=(float)(epoch*10+i);
  assert(ma_estimate_publish(new_x,new_stamp));read_irq();
 }
 assert(reads==90000);printf("whole snapshots checked:%u\n",reads);
}
'''
 common.compile_run(out,'slot_interruptions',slot_pre+function(src,'ma_estimate_read')+publish+slot_body)
 words=list(map(int,p.read(out/'publication_wire_words.txt').split()));assert len(words)==42
 server=p.read(p.OUT/'web_hmi/server.py');scope={}
 start=server.index('def foc_runtime_status(kv):');end=server.index('\ndef sd_live_status',start)
 exec(server[start:end],scope);decode=scope['foc_runtime_status']
 kv={'foc_runtime_valid':'1','foc_runtime_flags':'1',**{'foc_runtime_w'+str(i):str(v) for i,v in enumerate(words)}}
 decoded=decode(kv)['foc_runtime'];assert decoded['available']
 assert decoded['first_fault']['publication']['stage_name']=='accounting'
 assert decoded['first_fault']['estimate_age_us']==2000
 bad=dict(kv);bad['foc_runtime_w29']='6';assert not decode(bad)['foc_runtime']['available']
 for line in p.read(out/'regular_publication_words.txt').splitlines():
  rcf=list(map(int,line.split()));assert len(rcf)==42
  data={'foc_runtime_valid':'1','foc_runtime_flags':'1',**{'foc_runtime_w'+str(i):str(v) for i,v in enumerate(rcf)}}
  d=decode(data)['foc_runtime'];assert d['available'] and d['first_fault']['regular_adc']['reason_code']==rcf[15]
  assert d['first_fault']['publication']['schema']==1
 compile(server,'server.py','exec');subprocess.run(['node','--check',str(p.OUT/'web_hmi/static/app.js')],check=True,capture_output=True)
 for h in ('motor_control.h','current_core.h','current_adc_deadline.h','current_adc_window_plan.h','foc_experiment.h','local_stop.h'):
  assert (p.OUT/'nucleo/Inc'/h).read_bytes()==(p.BASE/'nucleo/Inc'/h).read_bytes(),h
 report=dict(passed=True,hardware_commands=0,recorded_interleaving_reproduced=True,
  actual_legacy_C_trips=True,actual_candidate_C_accepts_newer_completed_estimate=True,
  historical_exact_publication_stage_not_proven=True,checkpoint_is_injected_not_observed_instruction=True,
  historical_observer_state_not_restored=True,terminal_counts_and_timestamps_transferred=True,
  unchanged_2ms_guard_rejects_stale_new_result=True,external_stop_prevents_commit=True,
  atomic_snapshot_checks=90000,first_fault_immutable=True,six_pages_CRC_peer_validated=True,
  publication_metadata_HMI_validated=True,seven_regular_ADC_reasons_with_publication_metadata=True,
  trip_A=1.35,ADC_guard_ticks=2048,
  physical_5s_not_proven=True,results=results)
 p.write(out/'selftest.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
