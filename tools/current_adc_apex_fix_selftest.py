"""Actual IRQ tests: post-apex JEOS, exact saved raw replay, epoch and RMS model."""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
import current_adc_window_fix_selftest as previous
import current_shunt_irq_selftest as irq_test
import current_peak_capture_selftest as peak_test
import audit_production_pwm_filters as code
import prepare_current_adc_apex_fix as p
from collect_current_peak import decoder

EXTRA_TESTS=r'''
static void apex_tests(){
 // Independent whole-period deadline oracle; the apex is not a UEV here.
 for(unsigned phase=0;phase<10624;++phase){
  unsigned cnt=phase>=5312?10624-phase:phase,down=phase>=5312?16:0;
  bool expected=phase>=5184 && 10624-phase>2048;
  check(bool(mic_adc_publish_in_time(5312,cnt,down,5184))==expected);
 }
 check(mic_adc_publish_in_time(5312,5138,16,5184));
 check(!mic_adc_publish_in_time(5312,2048,16,5184));
 check(!mic_adc_publish_in_time(5312,6000,0,5184));
 check(!mic_adc_publish_in_time(0,0,0,0));
 check(!mic_adc_bottom_update(5312,5200,16));
 // OFF calibration must also work when MCSDK masks UIE, as on STOP/fault.
 // Timer/ADC still run; the ADC queue is freshly consumed, but no epoch IRQ.
 reset_test();state.zero_ready=0;timer.BDTR=0;bus=10;
 for(unsigned k=0;k<10000;++k){
  for(unsigned j=0;j<4;++j)active_ccr[j]=j==3?4928:2656;
  timer.CCR1=timer.CCR2=timer.CCR3=2656;timer.CCR4=4928;
  conversion(k,0,0);
 }
 check(state.zero_ready && state.zero_stable==3 && !state.zero_bad);
 // High bus NEVER becomes a zero reference even though power PWM is off.
 reset_test();state.zero_ready=0;timer.BDTR=0;bus=320;
 for(unsigned k=0;k<10000;++k){update(2656,2656,2656);conversion(k,0,0);}
 check(!state.zero_ready && state.zero_attempts==0);
 // A completed context from a different full32-bit update epoch is rejected.
 reset_test();update(2656,2656,2656);conversion(0);update(2656,2656,2656);
 --pending_epoch;unsigned n=state.window.n;conversion(1);
 check(state.window.n==n && !lost_sync);
 check(peak.blob.samples[(peak.write+11)%12].flags&4096);
 // An apex UEV (wrong RCR phasing) is not accepted as a bottom update.
 reset_test();update(2656,2656,2656);conversion(0);update(2656,2656,2656);
 peak_update_cnt=5200;peak_update_cr1=16;n=state.window.n;conversion(1);
 check(!pending_valid && state.window.n==n);
 // Epoch wrap is defined unsigned arithmetic, not a loss of synchronization.
 reset_test();peak_epoch=0xfffffffeU;pending_epoch=0xffffffffU;
 update(2656,2656,2656);conversion(0);
 update(2656,2656,2656);check(peak_epoch==0);conversion(1);
 check(!lost_sync && (peak.blob.samples[(peak.write+11)%12].flags&64));
 // JQM=1 must have consumed the previous sequence before another is queued.
 reset_test();update(2656,2656,2656);conversion(0);update(2656,2656,2656);
 timer.CNT=5138;timer.CR1=16;adc1.ISR=adc2.ISR=1;adc1.JSQR=0x105;adc2.JSQR=0;
 mic_current_adc_irq();check(lost_sync);
 check(peak.blob.samples[(peak.write+11)%12].flags&8192);
 // A preemption causing UEV between CH4 and JSQR publication invalidates NEXT.
 reset_test();update(2656,2656,2656);conversion(0);update(2656,2656,2656);
 ch4_hook=[](){++peak_epoch;};conversion(1);check(!pending_valid);ch4_hook=nullptr;
 // Replay the12 measured2508 samples at their ORIGINAL timestamps/CCRs.
 // Do not relabel old rejected raw values as measurements at a new time.
 reset_test();FILE *csv=fopen("saved_window_plans.csv","w");check(csv!=nullptr);
 fprintf(csv,"frame,old_plan_valid,new_plan_valid,old_recorded_trigger,new_planned_trigger,recorded_raw1,recorded_raw2\n");
 unsigned index=0;
 for(auto &x:saved){
  auto a=mic_plan_current_window(x.ccr[0],x.ccr[1],x.ccr[2],4928,771,112);
  auto b=mic_plan_current_window(x.ccr[0],x.ccr[1],x.ccr[2],5184,771,112);
  check(b.valid && mic_current_window_safe(b.pair,x.ccr[0],x.ccr[1],x.ccr[2],b.trigger,771,112));
  fprintf(csv,"%u,%u,%u,%u,%u,%u,%u\n",index++,a.valid,b.valid,x.ccr[3],b.trigger,x.raw[0],x.raw[1]);
  for(unsigned j=0;j<4;++j){peak_active_ccr[j]=x.ccr[j];state.offset[j]=x.offsets[j];}
  peak_epoch=pending_epoch=x.epoch;pending_pair=0;pending_valid=bool(x.flags&2);pending_active=bool(x.flags&4);
  peak_update_cnt=x.update_cnt;peak_update_cr1=x.update_dir;
  timer.CCR1=x.next[0];timer.CCR2=x.next[1];timer.CCR3=x.next[2];timer.CCR4=x.ccr[3];
  timer.CNT=x.cnt;timer.CR1=x.dir;timer.BDTR=(x.flags&1)?32768:0;
  tick=2000;dwt.CYCCNT=x.cycles;vf.fFlux_Freq_Hz=50;
  adc1.JDR1=x.raw[0]<<4;adc2.JDR1=x.raw[1]<<4;adc1.ISR=adc2.ISR=1;adc1.JSQR=adc2.JSQR=0;
  mic_current_adc_irq();
 }
 fclose(csv);
 check(peak.frozen && peak.blob.header.flags==PC_NO_PEAK && peak.blob.header.count==12);
 unsigned accepted=0;
 for(auto &x:peak.blob.samples)accepted+=bool(x.flags&64);
 check(accepted==10); // the2previously unsafe raw frames are STILL rejected
 uint8_t packet[UV3_FRAME];timer.BDTR=0;check(mic_current_peak_packet(packet,0,CT_PEER_BUILD));
 FILE *f=fopen("saved2508_replayed.bin","wb");check(f!=nullptr);
 check(fwrite(&peak.blob,1,1024,f)==1024);fclose(f);
 // Actual production PWM/Vf functions drive the shadow/update model at the
 // requested high frequencies. ADC currents here are explicitly synthetic.
 FILE *rms=fopen("synthetic_rms.csv","w");check(rms!=nullptr);
 fprintf(rms,"field_hz,valid_windows,accepted_samples,total_samples,rms_u_counts,rms_v_counts,rms_w_counts\n");
 for(float hz:{40.f,45.f,50.f}){
  reset_test();vf.fFlux_Freq_Hz=hz;
  production::TIM_TypeDef next_timer;production::PWM_Handle_t pwm{&next_timer};
  production::ACIM_VF_Handle_t controller{&pwm};controller.fVoutMax_PWM_Mod_V=159;controller.fFlux_Freq_Hz=hz;
  unsigned accepted_samples=0,valid_windows=0,previous_end=0;
  for(unsigned k=0;k<16000;++k){
   controller.fFlux_Angle_rad=float(std::fmod((k+1)*hz*10624.0/170000000*(2*PI),2*PI));
   check(production::ACIM_VF_Controller(&controller)==0);
   update(next_timer.CCR1,next_timer.CCR2,next_timer.CCR3);
   double angle=(k*10624.0+active_ccr[3])*hz/170000000*(2*PI)+.4;
   int i[3]={int(std::lround(120*std::sin(angle))),int(std::lround(120*std::sin(angle-2*PI/3))),0};i[2]=-i[0]-i[1];
   unsigned pair=pending_pair;conversion(k,i[pair==2?1:0],i[pair==0?1:2]);
   auto &sample=peak.blob.samples[(peak.write+11)%12];
   if(k>1 && !(sample.flags&64))fprintf(stderr,"model hz=%g k=%u flags=%u ccr=%u,%u,%u,%u pending_epoch=%u epoch=%u\n",hz,k,sample.flags,active_ccr[0],active_ccr[1],active_ccr[2],active_ccr[3],pending_epoch,peak_epoch);
   if(k>1)check(sample.flags&64);
   accepted_samples+=bool(sample.flags&64);
   check(mic_adc_publish_in_time(5312,timer.CNT,timer.CR1&16,active_ccr[3]));
   if(state.published.end_ms!=previous_end){previous_end=state.published.end_ms;
    check(cm_window_valid(&state.published));++valid_windows;
    for(unsigned j=0;j<3;++j){double value=std::sqrt(double(state.published.square[j])/state.published.n);
     check(std::abs(value-120/std::sqrt(2.0))<1.5);}
   }
  }
  check(valid_windows>=4 && accepted_samples>=15998 && !lost_sync);
  fprintf(rms,"%.0f,%u,%u,16000,%.6f,%.6f,%.6f\n",hz,valid_windows,accepted_samples,
      std::sqrt(double(state.published.square[0])/state.published.n),
      std::sqrt(double(state.published.square[1])/state.published.n),
      std::sqrt(double(state.published.square[2])/state.published.n));
 }
 fclose(rms);
}
int main(){regression_tests();apex_tests();
 printf("{\"passed\":true,\"checks\":%u,\"hardware_commands\":0,\"actual_irq\":true,\"post_apex_jeos\":true,\"full_epoch_and_wrap_checks\":true,\"raw_capture_frames_replayed\":24,\"new_currents_are_synthetic\":true}\n",checks);
}
'''

def production_model():
    base=p.OUT/'nucleo'
    pwm,vf,math=[(base/q).read_text(encoding='utf-8-sig') for q in (code.PWM,code.VF,Path('Src/mc_math.c'))]
    pre=re.sub(r'^\s*#include.*$', '', code.PREAMBLE,flags=re.M)
    s='namespace production {\n'+pre+code.function(vf,'mic_float_isfinite')+'\n'
    s+=re.search(r'#define SIN_FLOAT_0_90_TABLE.*?\}',math,re.S)[0]+'\nconst float fSin_Table[256]=SIN_FLOAT_0_90_TABLE;\n'
    for text,name in ((math,'MCM_floatTrig_Functions'),(pwm,'PWM_SetPhasePWMOutputs'),(vf,'ACIM_VF_Controller')):s+=code.function(text,name)+'\n'
    return s+'}\n'

def main():
    out=p.OUT/'apex_selftest_r1';out.mkdir(exist_ok=True)
    assert not json.loads((p.OUT/'manifest.json').read_text(encoding='utf-8'))['built']
    src=(p.OUT/'nucleo/Src/current_shunt.c').read_text(encoding='utf-8')
    globals_=src[src.index('static cm_core state;'):src.index('void mic_current_init(void)')]
    irq=src[src.index('void mic_current_adc_irq(void)'):src.index('static uint16_t ma_u')]
    from prepare_current_zero_noise import REPORT_DECL
    pre=irq_test.PREAMBLE.replace('#include "current_core.h"',REPORT_DECL+'#include "current_core.h"\n#include "current_adc_window_plan.h"\n#include "current_adc_deadline.h"')
    pre=pre.replace('enum {CM_SETTLE_TICKS=771};','enum {CM_SETTLE_TICKS=771,CM_BEFORE_TOP=128,CM_IDLE_BEFORE_TOP=384,CM_ACQUIRE_TICKS=112};')
    pre=pre.replace('static void check(bool okay)','static void check_at(bool okay,unsigned line)').replace('"IRQ check %u failed\\n",checks','"IRQ check %u failed at line%u\\n",checks,line')
    pre+='\n#define check(value) check_at((value),__LINE__)\n'
    pre=pre.replace('static uint16_t VBS_GetAvBusVoltage_V(int*){return bus;}',
        'static void(*bus_hook)();\nstatic uint16_t VBS_GetAvBusVoltage_V(int*){if(bus_hook)bus_hook();return bus;}')
    pre+='\nstatic void(*ch4_hook)();static void LL_TIM_OC_SetCompareCH4(Timer*t,uint32_t v){t->CCR4=v;if(ch4_hook)ch4_hook();}\n'
    pre+='#include <cassert>\n#include <cmath>\n#include <cstring>\n#include <algorithm>\n#include <initializer_list>\n'
    trace=json.loads((p.BASE.parent/'current_zero_noise_r1/peak_capture_30_to_50_r1/decoded.json').read_text(encoding='utf-8'))
    replay='\nstruct Frame{unsigned ccr[4],next[4],raw[2],cnt,cycles;};static Frame replay[]={\n'
    for x in trace['samples']:
        replay+='{'+','.join('{'+','.join(map(str,x[k]))+'}' for k in ('ccr_at_update','ccr_preload','raw_adc'))+','+str(x['timer_cnt_entry'])+','+str(x['cycles'])+'U},\n'
    replay+='};\n'
    trace2=json.loads((p.BASE/'peak_capture_30_to_50_r1/decoded.json').read_text(encoding='utf-8'))
    replay+='struct Saved{unsigned ccr[4],next[4],raw[2],offsets[4],cnt,dir,epoch,cycles,update_cnt,update_dir,flags;};static Saved saved[]={\n'
    for x in trace2['samples']:
        replay+='{'+','.join('{'+','.join(map(str,x[k]))+'}' for k in ('ccr_at_update','ccr_preload','raw_adc','offsets_adc'))+','
        fields=(x['timer_cnt_entry'],16*x['timer_dir_entry'],x['epoch_before'],x['cycles'],x['timer_cnt_at_update'],16*x['timer_dir_at_update'],x['flags'])
        replay+=','.join(str(int(v))+'U' for v in fields)+'},\n'
    replay+='};\n'
    cases=previous.CASES.replace('int main(){','static void regression_tests(){')
    cases=cases[:cases.rfind(' printf(')]+'}\n'
    cases=cases.replace(' bus_hook=nullptr;',' bus_hook=nullptr;ch4_hook=nullptr;pending_epoch=0;')
    cases=cases.replace(' tick=1000+n/16;timer.CNT=active_ccr[3]+302;timer.CR1=0;dwt.CYCCNT+=10624;',
        ' tick=1000+n/16;unsigned phase=active_ccr[3]+302;timer.CNT=phase>=5312?10624-phase:phase;timer.CR1=phase>=5312?16:0;dwt.CYCCNT+=10624;adc1.JSQR=adc2.JSQR=0;')
    cases=cases.replace('timer.CCR4<=4928','timer.CCR4<=5184')
    cases=cases.replace('peak_epoch=n+1;pending_pair=0;', 'peak_epoch=n+1;pending_epoch=peak_epoch;adc1.JSQR=adc2.JSQR=0;pending_pair=0;')
    source=pre+peak_test.EXTRA+globals_+irq+'\n'+code.function(src,'mic_current_peak_packet')+production_model()+replay+cases+EXTRA_TESTS
    unit=out/'actual_apex_irq.cpp';unit.write_text(source,encoding='utf-8')
    with tempfile.TemporaryDirectory() as temp:
        exe=Path(temp)/'test.exe'
        b=subprocess.run([shutil.which('g++'),'-std=c++17','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers',
            '-I',str(p.OUT/'nucleo/Inc'),'-I',str(p.OUT/'UNOQ_MOTOR'),str(unit),'-o',str(exe)],capture_output=True,text=True,timeout=60)
        (out/'build.log').write_text(b.stdout+b.stderr,encoding='utf-8');b.check_returncode()
        t=subprocess.run([str(exe)],cwd=out,capture_output=True,text=True,timeout=30)
        (out/'run.log').write_text(t.stdout+t.stderr,encoding='utf-8');t.check_returncode()
    result=json.loads(t.stdout)
    h=decoder(p.OUT)
    for name,original in (('replayed_trace.bin',trace),('saved2508_replayed.bin',trace2)):
        raw=(out/name).read_bytes();d=h.decode_adc_peak_hex(raw.hex())
        assert d['sample_count']==12
        assert [x['raw_adc'] for x in d['samples']]==[x['raw_adc'] for x in original['samples']]
        if name.startswith('saved'):
            assert d['no_peak'] and sum(x['accepted_by_monitor'] for x in d['samples'])==10
        else:assert d['peak_seen'] and not any(x['accepted_by_monitor'] for x in d['samples'])
        for bad in (raw[:-1],bytes([raw[0]^1])+raw[1:]):
            try:h.decode_adc_peak_hex(bad.hex())
            except ValueError:pass
            else:raise AssertionError('Corrupt trace accepted')
    result.update(original_bad_raw_not_relabelled_as_good=True,raw_wire_hmi_roundtrip=True,
        synthetic_rms_valid_40_45_50_hz=True,physical_rms_verified=False)
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))

if __name__=='__main__':main()
