"""Execute candidate IRQ/planner, real raw trace replay, and C4-preload model."""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
import current_shunt_irq_selftest as irq_test
import current_peak_capture_selftest as peak_test
import prepare_current_adc_window_fix as p
from audit_production_pwm_filters import function
from collect_current_peak import decoder

CASES=r'''
static void reset_test(){
 cm_init(&state);state.zero_ready=1;pc_init(&peak);peak_sealed=0;
 for(unsigned i=0;i<4;++i)state.offset[i]=2067;
 lost_sync=0;pending_pair=0;pending_valid=0;pending_active=0;peak_epoch=0;
 initialized=1;bus=320;timer={2656,2656,2656,4928,0,0,5312,32768};
 bus_hook=nullptr;
}
// CCR fields model readable preload registers. 'active' only changes on UEV.
// Writing CH4 while counting MUST leave the current cycle's active CCR alone.
static uint16_t active_ccr[4];
static void update(unsigned u,unsigned v,unsigned w){
 active_ccr[0]=(uint16_t)timer.CCR1;active_ccr[1]=(uint16_t)timer.CCR2;
 active_ccr[2]=(uint16_t)timer.CCR3;active_ccr[3]=(uint16_t)timer.CCR4;
 timer.CNT=110;timer.CR1=0;mic_current_update_epoch();
 timer.CCR1=u;timer.CCR2=v;timer.CCR3=w;
}
static void conversion(unsigned n,int ia=78,int ib=-39,bool second=true){
 tick=1000+n/16;timer.CNT=active_ccr[3]+302;timer.CR1=0;dwt.CYCCNT+=10624;
 unsigned x=cm_path1(pending_pair),y=cm_path2(pending_pair);
 adc1.JDR1=(state.offset[x]-ia)<<4;adc2.JDR1=(state.offset[y]-ib)<<4;
 adc1.ISR=1;adc2.ISR=second?1:0;
 unsigned power[3]={timer.CCR1,timer.CCR2,timer.CCR3};
 unsigned old_active=active_ccr[3];
 mic_current_adc_irq();
 check(timer.CCR1==power[0] && timer.CCR2==power[1] && timer.CCR3==power[2]);
 check(active_ccr[3]==old_active); // no immediate CH4/trigger change
 check(timer.CCR4<=4928 && timer.CCR4>0);
 check((adc1.JSQR>>8)==(pending_pair==2?7U:1U));
 check((adc2.JSQR>>8)==(pending_pair==0?7U:6U));
}
int main(){
 // Independent brute-force interval oracle on a dense small-integer domain.
 for(unsigned u=0;u<=30;u+=2)for(unsigned v=0;v<=30;v+=2)
 for(unsigned w=0;w<=30;w+=2){
  auto plan=mic_plan_current_window(u,v,w,30,5,2);
  unsigned c[3]={u,v,w};unsigned excluded=u>=v&&u>=w?0:v>=w?1:2;
  bool found=false;
  for(unsigned t=1;t<=30;++t){
   bool okay=t>5;
   for(unsigned j=0;j<3;++j){
    if(j!=excluded && (c[j]+5>=t))okay=false;
    if(c[j]+5>=t && c[j]<=t+2)okay=false;
   }
   found|=okay;
   check(mic_current_window_safe(plan.pair,u,v,w,t,5,2)==okay);
  }
  check(bool(plan.valid)==found);
  if(found)check(mic_current_window_safe(plan.pair,u,v,w,plan.trigger,5,2));
 }
 check(!mic_current_window_safe(3,0,0,0,100,5,2));
 check(!mic_current_window_safe(0,0,0,0,0xffffffffU,5,2));
 check(!mic_plan_current_window(5000,5000,5000,4928,771,112).valid);
 // The physical trigger frame must fail the NEW geometry check, while a
 // counterfactual different trigger is safe. It is not a remeasured ADC value.
 FILE *csv=fopen("window_replay.csv","w");check(csv!=nullptr);
 fprintf(csv,"frame,old_trigger,new_trigger,new_pair,u_compare,v_compare,w_compare,old_safe,new_safe,raw1,raw2\n");
 unsigned ordinal=0;
 for(auto &x:replay){
  check(cm_pair_window(0,x.ccr[0],x.ccr[1],x.ccr[2],x.ccr[3],771));
  check(!mic_current_window_safe(0,x.ccr[0],x.ccr[1],x.ccr[2],x.ccr[3],771,112));
  auto plan=mic_plan_current_window(x.ccr[0],x.ccr[1],x.ccr[2],4928,771,112);
  check(plan.valid && plan.trigger!=4928);
  check(mic_current_window_safe(plan.pair,x.ccr[0],x.ccr[1],x.ccr[2],plan.trigger,771,112));
  fprintf(csv,"%u,%u,%u,%u,%u,%u,%u,0,1,%u,%u\n",ordinal++,x.ccr[3],plan.trigger,plan.pair,x.ccr[0],x.ccr[1],x.ccr[2],x.raw[0],x.raw[1]);
 }
 fclose(csv);
 // Replay the ACTUAL raw pairs/CCRs, not a fabricated shifted waveform.
 reset_test();
 for(unsigned n=0;n<12;++n){auto &x=replay[n];
  for(unsigned j=0;j<4;++j)peak_active_ccr[j]=x.ccr[j];
  peak_epoch=n+1;pending_pair=0;pending_valid=1;pending_active=1;
  timer.CCR1=x.next[0];timer.CCR2=x.next[1];timer.CCR3=x.next[2];timer.CCR4=x.ccr[3];
  timer.CNT=x.cnt;timer.CR1=0;tick=2000;dwt.CYCCNT=x.cycles;
  adc1.ISR=1;adc2.ISR=1;adc1.JDR1=x.raw[0]<<4;adc2.JDR1=x.raw[1]<<4;
  mic_current_adc_irq();
 }
 check(state.window.n==0 && state.window.bad==12);
 check((state.window.flags&CM_TIMING)!=0);
 check(peak.frozen && peak.blob.header.flags==PC_PEAK && peak.blob.header.count==12);
 auto &trigger=peak.blob.samples[peak.blob.header.trigger_slot];
 check(trigger.raw[0]==1719 && trigger.raw[1]==1665);
 check((trigger.flags&1024)!=0 && (trigger.flags&64)==0);
 uint8_t packet[UV3_FRAME];timer.BDTR=0;
 pc_receiver rx{};
 for(int page=34;page>=0;--page){
  check(mic_current_peak_packet(packet,page,CT_PEER_BUILD));
  check(pc_receive(&rx,packet,CT_PEER_BUILD,true,1));
 }
 check(rx.complete && memcmp(rx.data,&peak.blob,1024)==0);
 FILE *f=fopen("replayed_trace.bin","wb");check(f!=nullptr);
 check(fwrite(&peak.blob,1,1024,f)==1024);fclose(f);
 // Cycle pipeline: current sample uses the previously committed tuple;
 // plan for NEXT shadows is not treated as though already active.
 reset_test();
 for(unsigned n=0;n<8000;++n){
  unsigned w=4600+(n%60)*5;
  update(700,2500,w);conversion(n);
  if(n>2)check(mic_current_window_safe(pending_pair,700,2500,w,timer.CCR4,771,112));
 }
 check(cm_window_valid(&state.published) && state.published.bad==0);
 check(state.window.last[0]==78 && state.window.last[1]==-39 && state.window.last[2]==-39);
 // Rotate all three shadows, including changes of reconstructed phase.
 // Encode known currents through the PREVIOUS queued mux tuple.
 reset_test();
 for(unsigned n=0;n<10000;++n){
  unsigned u=500+n%4000,v=500+(n+1333)%4000,w=500+(n+2666)%4000;
  update(u,v,w);
  unsigned captured=pending_pair,valid=pending_valid,active=pending_active;
  bool expected=valid && active && mic_current_window_safe(captured,
      active_ccr[0],active_ccr[1],active_ccr[2],active_ccr[3],771,112);
  int currents[3]={100,-40,-60};
  conversion(n,currents[captured==2?1:0],currents[captured==0?1:2]);
  auto &sample=peak.blob.samples[(peak.write+11)%12];
  check(sample.pair==captured && bool(sample.flags&64)==expected);
  for(unsigned j=0;j<4;++j)check(sample.active_ccr[j]==active_ccr[j]);
  const auto &latest=state.published.end_ms==tick?state.published:state.window;
  if(expected)for(unsigned j=0;j<3;++j)check(latest.last[j]==currents[j]);
 }
 // Genuine large counts in a safe window are preserved, never amplitude-clipped.
 reset_test();
 for(unsigned n=0;n<20;++n){update(2656,2656,2656);conversion(n);}
 update(2656,2656,2656);conversion(20,1162,-581);
 check(peak.triggered && state.window.peak[1]==1162);
 for(unsigned n=21;n<27;++n){update(2656,2656,2656);conversion(n);}
 check(peak.frozen && peak.blob.header.flags==PC_PEAK);
 // Even frozen diagnostic storage must not stop epoch tracking for monitoring.
 unsigned ep=peak_epoch;update(2656,2656,2656);check(peak_epoch==ep+1);
 unsigned old_n=state.window.n;conversion(27);check(state.window.n==old_n+1);
 // Wrong context, missing ADC2, JQ overflow, and no safe window fail closed.
 reset_test();update(2656,2656,2656);conversion(0);
 update(2656,2656,2656);++peak_active_ccr[3];old_n=state.window.n;conversion(1);
 check(state.window.n==old_n && state.window.bad>0);
 reset_test();update(2656,2656,2656);conversion(0);
 update(2656,2656,2656);conversion(1,78,-39,false);check(lost_sync);
 old_n=state.window.n;update(2656,2656,2656);conversion(2);check(state.window.n==old_n);
 reset_test();update(5000,5000,5000);conversion(0);check(!pending_valid);
 update(5000,5000,5000);old_n=state.window.n;conversion(1);check(state.window.n==old_n);
 reset_test();update(2656,2656,2656);conversion(0);update(2656,2656,2656);
 bus_hook=[](){++peak_epoch;};old_n=state.window.n;conversion(1);
 check(!pending_valid && state.window.n==old_n);bus_hook=nullptr;
 reset_test();update(2656,2656,2656);conversion(0);update(2656,2656,2656);
 timer.CNT=5230;adc1.ISR=1|ADC_ISR_JQOVF;adc2.ISR=1;mic_current_adc_irq();check(lost_sync);
 // Real OFF IRQ path still alternates four ADC paths and completes the same
 // three-block zero sequence at low bus; no power PWM or trace trigger.
 reset_test();state.zero_ready=0;timer.BDTR=0;bus=10;
 for(unsigned n=0;n<10000;++n){update(2656,2656,2656);conversion(n,0,0);}
 check(state.zero_ready && !state.zero_bad && state.zero_stable==3 && state.zero_attempts==3);
 for(unsigned j=0;j<4;++j)check(state.offset[j]==2067 && state.count[j]==256);
 check(!peak.running && !peak.frozen && peak.count==0);
 check(packets==0);
 printf("{\"passed\":true,\"checks\":%u,\"actual_irq\":true,\"real_trace_frames_replayed\":12,\"new_waveform_synthetic\":true,\"preload_epoch_pipeline_model\":true,\"hardware_commands\":0}\n",checks);
}
'''

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--outdir',type=Path,default=p.OUT/'window_selftest_r1')
    args=ap.parse_args();out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=True)
    assert not json.loads((p.OUT/'manifest.json').read_text())['built']
    trace=json.loads((p.BASE/'peak_capture_30_to_50_r1/decoded.json').read_text())
    src=(p.OUT/'nucleo/Src/current_shunt.c').read_text()
    globals_=src[src.index('static cm_core state;'):src.index('void mic_current_init(void)')]
    irq=src[src.index('void mic_current_adc_irq(void)'):src.index('static uint16_t ma_u')]
    from prepare_current_zero_noise import REPORT_DECL
    pre=irq_test.PREAMBLE.replace('#include "current_core.h"',REPORT_DECL+'#include "current_core.h"\n#include "current_adc_window_plan.h"')
    pre=pre.replace('enum {CM_SETTLE_TICKS=771};','enum {CM_SETTLE_TICKS=771,CM_BEFORE_TOP=384,CM_ACQUIRE_TICKS=112};')
    pre=pre.replace('static void check(bool okay)', 'static void check_at(bool okay,unsigned line)')
    pre=pre.replace('"IRQ check %u failed\\n",checks','"IRQ check %u failed at line%u\\n",checks,line')
    pre+='\n#define check(value) check_at((value),__LINE__)\n'
    pre=pre.replace('static uint16_t VBS_GetAvBusVoltage_V(int*){return bus;}',
        'static void(*bus_hook)();\nstatic uint16_t VBS_GetAvBusVoltage_V(int*){if(bus_hook)bus_hook();return bus;}')
    pre+='\nstatic void LL_TIM_OC_SetCompareCH4(Timer*t,uint32_t v){t->CCR4=v;}\n'
    replay='\nstruct Frame{unsigned ccr[4],next[4],raw[2],cnt,cycles;};static Frame replay[]={\n'
    for x in trace['samples']:
        replay+='{'+','.join('{'+','.join(map(str,x[k]))+'}' for k in ('ccr_at_update','ccr_preload','raw_adc'))+','+str(x['timer_cnt_entry'])+','+str(x['cycles'])+'U},\n'
    replay+='};\n'
    source=pre+peak_test.EXTRA+globals_+irq+'\n'+function(src,'mic_current_peak_packet')+replay+CASES
    unit=out/'actual_window_irq.cpp';unit.write_text(source)
    with tempfile.TemporaryDirectory() as temp:
        exe=Path(temp)/'test.exe'
        b=subprocess.run([shutil.which('g++'),'-std=c++17','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers',
            '-I',str(p.OUT/'nucleo/Inc'),'-I',str(p.OUT/'UNOQ_MOTOR'),str(unit),'-o',str(exe)],capture_output=True,text=True,timeout=60)
        (out/'build.log').write_text(b.stdout+b.stderr);b.check_returncode()
        t=subprocess.run([str(exe)],cwd=out,capture_output=True,text=True,timeout=30)
        (out/'run.log').write_text(t.stdout+t.stderr);t.check_returncode()
    result=json.loads(t.stdout)
    h=decoder(p.OUT);raw=(out/'replayed_trace.bin').read_bytes();d=h.decode_adc_peak_hex(raw.hex())
    assert d['sample_count']==12 and d['peak_seen'] and not d['post_short']
    assert all(not x['accepted_by_monitor'] and x['three_leg_window_rejected'] for x in d['samples'])
    trigger=next(x for x in d['samples'] if x['is_trigger'])
    assert trigger['raw_adc']==[1719,1665] and trigger['counts_uvw']==[348,402,-750]
    for corrupt in (raw[:-1],bytes([raw[0]^1])+raw[1:]):
        try:h.decode_adc_peak_hex(corrupt.hex())
        except ValueError:pass
        else:raise AssertionError('Corrupted ADC record accepted')
    result.update(raw_peak_evidence_preserved=True,raw_record_wire_hmi_roundtrip=True,
        geometry_rejection_not_claimed_as_physical_current_fix=True,shifted_sample_current_unknown=True)
    (out/'decoded.json').write_text(json.dumps(d,indent=2)+'\n')
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
