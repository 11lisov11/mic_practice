"""Replay measured zero ranges and adversarial signals on actual firmware core/encoders."""
import importlib.util
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import prepare_current_zero_noise as p
from audit_production_pwm_filters import function

PREAMBLE=r'''
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <algorithm>
using std::isfinite;
static uint32_t tick;
static uint32_t HAL_GetTick(){return tick;}
'''
CASES=r'''
static unsigned checks;
static const uint16_t bias[4]={2068,2068,2067,2069};
static const uint16_t measured_low[4]={2054,2052,2052,2056};
static const uint16_t measured_high[4]={2103,2085,2082,2102};
static unsigned sample_index;
static void check(bool b){++checks;if(!b){fprintf(stderr,"zero-noise check%u failed\n",checks);exit(1);}}
static uint16_t value(unsigned path,unsigned ordinal,int mode,int delta) {
 int raw=bias[path]+delta;
 if(mode==1) {
  if(ordinal==10)raw=measured_low[path];
  if(ordinal==100)raw=measured_high[path];
 } else if(mode==2)raw=ordinal%7<2?measured_high[path]:measured_low[path];
 else if(mode==3)raw+=(ordinal&1)?12:-12;
 else if(mode==4)raw=3000;
 else if(mode==5 && ordinal==100)raw=4095;
 else if(mode==6 && ordinal==100)raw+=1162;
 else if(mode==7)raw+=(ordinal&1)?10:-10;
 else if(mode==8)raw+=(ordinal&1)?11:-11;
 else if(mode==9)raw=0;
 else if(mode==10)raw=(ordinal&1)?4095:0;
 else if(mode==11)raw+=ordinal<128?3:-3;
 return (uint16_t)raw;
}
static void prime(){
 cm_init(&state);memset(zero_history,0,sizeof(zero_history));sample_index=0;
 for(;sample_index<8000;++sample_index){tick=sample_index/16;uint8_t pair=(sample_index&1)?2:0;
  cm_sample(&state,tick,0,pair,bias[cm_path1(pair)],bias[cm_path2(pair)],0,1);}
 check(!state.zero_ready && !state.zero_attempts);
}
static void block(int mode=0,int delta=0){
 for(unsigned j=0;j<512;++j,++sample_index){
  uint8_t pair=(j&1)?2:0;unsigned a=cm_path1(pair),b=cm_path2(pair);
  uint16_t x=value(a,state.count[a],mode,delta),y=value(b,state.count[b],mode,delta);
  tick=sample_index/16;cm_sample(&state,tick,0,pair,x,y,0,1);
 }
}
int main(){
 // Compare integer arithmetic with an independent two-pass long-double oracle,
 // including near-rail codes and correlated four-group signals.
 uint32_t seed=0x2176354U;
 for(unsigned trial=0;trial<3000;++trial){
  cm_core probe;cm_init(&probe);uint8_t expected_reject=0,expected_paths=0;long double max_variance=0;
  for(unsigned path=0;path<4;++path){
   uint16_t raw[256];seed=1664525U*seed+1013904223U;int center=1460+(seed%1220);
   seed=1664525U*seed+1013904223U;unsigned amp=seed%81;long double sum=0;bool clipped=false;
   for(unsigned i=0;i<256;++i){seed=1664525U*seed+1013904223U;
    int code=center+int(seed%(2*amp+1))-int(amp);
    if(trial%13==0)code=(seed&0x10000)?4095:0;
    raw[i]=(uint16_t)code;sum+=code;clipped|=code<16 || code>4079;
    cm_zero_sample(&probe,path,raw[i]);
   }
   long double mean=sum/256,raw_var=0,group_var=0;
   for(auto code:raw)raw_var+=(code-mean)*(code-mean);
   raw_var/=256*255;
   for(unsigned g=0;g<4;++g){long double group_mean=0;
    for(unsigned i=0;i<64;++i){group_mean+=raw[64*g+i];}group_mean/=64;
    group_var+=(group_mean-mean)*(group_mean-mean);
   }
   group_var/=4*3;long double variance=std::max(raw_var,group_var);
   max_variance=std::max(max_variance,variance);uint8_t reason=0;
   if(variance*9>4+1e-12L)reason|=1;
   if(floorl(mean+.5L)<1600 || floorl(mean+.5L)>2500)reason|=2;
   if(clipped)reason|=8;
   expected_reject|=reason;if(reason)expected_paths|=1U<<path;
  }
  cm_zero_finish_block(&probe);
  check(probe.zero_last_bad==expected_reject);
  check((zero_history[0].bytes[14]&15)==expected_paths);
  unsigned quant=(unsigned)floorl(max_variance*128+.5L);if(quant>255)quant=255;
  check(zero_history[0].bytes[13]==quant);
 }
 prime();block(1);block(1);check(!state.zero_ready && state.zero_stable==2);
 block(1);check(state.zero_ready && state.zero_stable==3 && state.zero_attempts==3);
 for(unsigned i=0;i<4;++i){check(abs((int)state.offset[i]-(int)bias[i])<=1);check(state.count[i]==256);}
 check(zero_history[0].bytes[8]==49 && zero_history[0].bytes[11]==46);
 check((zero_history[0].bytes[12]>>2)==0 && (zero_history[2].bytes[12]&3)==3);
 prime();for(unsigned i=0;i<8;++i)block(2);
 check(state.zero_bad && !state.zero_ready && state.zero_attempts==8 && (state.zero_last_bad&1));
 check((zero_history[7].bytes[14]&15)!=0);
 // A sustained24-count range passed the old span40 rule; noisy means must fail.
 prime();for(unsigned i=0;i<8;++i)block(3);
 check(state.zero_bad && state.zero_last_bad==1 && state.zero_high[0]-state.zero_low[0]==24);
 prime();block(7);block(7);block(7);check(state.zero_ready); //3sigma~1.879counts
 prime();for(unsigned i=0;i<8;++i)block(8);check(state.zero_bad && state.zero_last_bad==1); //3sigma~2.067
 prime();for(unsigned i=0;i<8;++i)block(4);check(state.zero_bad && (state.zero_last_bad&2));
 prime();for(unsigned i=0;i<8;++i)block(5);check(state.zero_bad && (state.zero_last_bad&8));
 prime();for(unsigned i=0;i<8;++i)block(6);check(state.zero_bad && (state.zero_last_bad&1));
 prime();for(unsigned i=0;i<8;++i)block(9);check(state.zero_bad && (state.zero_last_bad&8));
 prime();for(unsigned i=0;i<8;++i)block(10);check(state.zero_bad && (state.zero_last_bad&9)==9);
 prime();for(unsigned i=0;i<8;++i)block(11);check(state.zero_bad && state.zero_last_bad==1); //correlated6-count range
 prime();for(unsigned i=0;i<8;++i)block(0,4*i);check(state.zero_bad && state.zero_stable==1 && state.zero_last_bad==4);
 prime();block();cm_sample(&state,700,0,0,2068,2067,0,0);
 check(state.zero_stable==0 && state.count[0]==0 && !state.zero_ready);
 prime();block();cm_sample(&state,700,1,0,2068,2067,1,0);
 check(!state.zero_stable && !state.zero_ready);
 // Active current samples remain unaveraged and retain their raw1162-count peak.
 prime();block();block();block();
 for(unsigned i=0;i<3201;++i)cm_sample(&state,1000+i/16,1,0,bias[0]-(i==100?1162:100),bias[2]+40,1,0);
 check(state.published.peak[0]==1162 && state.published.last[0]==100);
 // Export both failed and successful actual history packets for Python/HMI tests.
 prime();for(unsigned i=0;i<8;++i)block(3);
 uint8_t packet[UV3_FRAME];FILE *file=fopen("failed_history.bin","wb");check(file!=nullptr);
 for(unsigned i=0;i<8;++i){packets=4*i;check(mic_zero_packet(packet,CT_PEER_BUILD));fwrite(packet,1,UV3_FRAME,file);}fclose(file);
 prime();block(1);block(1);block(1);
 zh_receiver receiver{};file=fopen("history.bin","wb");check(file!=nullptr);
 for(unsigned i=0;i<3;++i){packets=4*i;check(mic_zero_packet(packet,CT_PEER_BUILD));
  check(!zh_receive(&receiver,packet,2026102502,true));check(!zh_receive(&receiver,packet,CT_PEER_BUILD,false));
  check(zh_receive(&receiver,packet,CT_PEER_BUILD,true));fwrite(packet,1,UV3_FRAME,file);}
 fclose(file);check(receiver.complete);
 packet[10]^=1;check(!zh_receive(&receiver,packet,CT_PEER_BUILD,true));uv3_seal(packet);
 check(!zh_receive(&receiver,packet,CT_PEER_BUILD,true));
 timer.BDTR=32768;check(!mic_zero_packet(packet,CT_PEER_BUILD));timer.BDTR=0;
 uint8_t summary[43],detail[43],quality[43];
 mic_current_packet(summary,0,CT_PEER_BUILD);mic_current_packet(detail,1,CT_PEER_BUILD);mic_current_packet(quality,2,CT_PEER_BUILD);
 check(quality[34]==0 && quality[36]==3 && quality[37]==2);
 printf("{\"passed\":true,\"checks\":%u,\"summary\":\"",checks);
 for(unsigned i=0;i<43;++i){printf("%02x",summary[i]);}printf("\",\"detail\":\"");
 for(unsigned i=0;i<43;++i){printf("%02x",detail[i]);}printf("\",\"quality\":\"");
 for(unsigned i=0;i<43;++i){printf("%02x",quality[i]);}printf("\"}");
}
'''
OLD_TEST=r'''
#include <cstdio>
#include "current_core.h"
static const unsigned bias[4]={2068,2068,2067,2069},lo[4]={2054,2052,2052,2056},hi[4]={2103,2085,2082,2102};
int main(){cm_core s;cm_init(&s);
 for(unsigned i=0;i<8000+512*8;++i){unsigned pair=(i&1)?2:0,p=cm_path1(pair),q=cm_path2(pair);
 unsigned a=bias[p],b=bias[q];if(s.count[p]==10)a=lo[p];if(s.count[p]==100)a=hi[p];
 if(s.count[q]==10)b=lo[q];if(s.count[q]==100)b=hi[q];cm_sample(&s,i/16,0,pair,a,b,0,1);}
 printf("{\"failed\":%s,\"attempts\":%u,\"stable\":%u,\"u1_span\":%u,\"w2_span\":%u}",
 s.zero_bad&&!s.zero_ready?"true":"false",s.zero_attempts,s.zero_stable,s.zero_high[0]-s.zero_low[0],s.zero_high[3]-s.zero_low[3]);}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir',type=Path,default=p.OUT/'zero_noise_selftest_r1')
    args=parser.parse_args();out=args.outdir.resolve();out.mkdir(exist_ok=False)
    source=(p.OUT/'nucleo/Src/current_shunt.c').read_text(encoding='utf-8')
    encoder=source[source.index('static uint16_t ma_u'):source.index('uint8_t mic_current_peak_packet')]
    program=PREAMBLE+p.REPORT_DECL+'#include "current_core.h"\n#include "zero_wire.h"\n'+p.HISTORY+'''
static cm_core state;static uint32_t packets;
static uint32_t __get_PRIMASK(){return 0;}static void __disable_irq(){}static void __set_PRIMASK(uint32_t){}
static struct{unsigned BDTR;}timer;
#define TIM1 (&timer)
static unsigned LL_TIM_IsEnabledAllOutputs(decltype(timer)*t){return t->BDTR;}
#define ADC_REFERENCE_VOLTAGE 3.3f
#define RSHUNT .04f
#define AMPLIFICATION_GAIN 2.1f
'''+encoder+function(source,'mic_zero_packet')+'\n'+CASES
    report=dict(passed=False,hardware_commands=0,physical_measurements=False)
    try:
        with tempfile.TemporaryDirectory() as folder:
            exe=Path(folder)/'test.exe';unit=out/'actual_zero.cpp';unit.write_text(program,encoding='utf-8')
            cmd=[shutil.which('g++'),'-std=c++17','-Wall','-Wextra','-Werror','-I',str(p.OUT/'nucleo/Inc'),'-I',str(p.OUT/'UNOQ_MOTOR'),str(unit),'-o',str(exe)]
            b=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
            (out/'compile.log').write_text(b.stdout+b.stderr,encoding='utf-8');b.check_returncode()
            run=subprocess.run([str(exe)],cwd=out,capture_output=True,text=True,timeout=30)
            (out/'run.log').write_text(run.stdout+run.stderr,encoding='utf-8');run.check_returncode();encoded=json.loads(run.stdout)
            unit=out/'old_reproduction.cpp';unit.write_text(OLD_TEST,encoding='utf-8')
            b=subprocess.run([shutil.which('g++'),'-std=c++17','-I',str(p.BASE/'nucleo/Inc'),str(unit),'-o',str(exe)],capture_output=True,text=True,timeout=60)
            b.check_returncode();old=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30);old.check_returncode()
            replay=json.loads(old.stdout);assert replay==dict(failed=True,attempts=8,stable=0,u1_span=49,w2_span=46)
        spec=importlib.util.spec_from_file_location('zero_noise_hmi',p.OUT/'web_hmi/server.py')
        h=importlib.util.module_from_spec(spec);sys.modules[spec.name]=h;spec.loader.exec_module(h)
        fixture=dict(fw_build=p.NEW[0],mc_fw_build=p.NEW[1],bp_mcsdk_telemetry=1,mc_age_ms=10,
            mc_current_age_ms=10,mc_current_detail_age_ms=10,mc_current_quality_age_ms=10,
            mc_current_packet_hex=encoded['summary'],mc_current_detail_hex=encoded['detail'],mc_current_quality_hex=encoded['quality'],
            mc_zero_history_hex=(out/'history.bin').read_bytes().hex())
        status=h.with_zero_history(h.with_shunt_currents(dict(fixture)))
        from current_zero_quality import ready
        assert ready(status)
        for change in ({'mc_current_flags':17},{'mc_zero_history_valid':0},{'mc_age_ms':300},
                       {'mc_current_zero_attempts':8},{'mc_current_zero_ready':0}):
            assert not ready(dict(status,**change))
        assert status['mc_current_zero_ready']==1 and status['mc_current_zero_stable']==3
        assert status['mc_current_zero_spans']==[49,33,30,46]
        assert status['mc_zero_history_valid']==1 and len(status['mc_zero_history'])==3
        assert status['mc_zero_history'][0]['raw_spans_adc']==[49,33,30,46]
        assert status['mc_zero_history'][2]['stable']==3 and not status['mc_zero_history'][2]['reject_flags']
        failed=h.with_zero_history(dict(fixture,mc_zero_history_hex=(out/'failed_history.bin').read_bytes().hex()))
        assert failed['mc_zero_history_valid']==1 and len(failed['mc_zero_history'])==8
        assert all(x['reject_flags']==1 and x['failed_paths_mask']==15 for x in failed['mc_zero_history'])
        corrupt=bytearray((out/'history.bin').read_bytes());corrupt[11]^=1
        assert h.with_zero_history(dict(fixture,mc_zero_history_hex=corrupt.hex()))['mc_zero_history_valid']==0
        assert h.with_zero_history(dict(fixture,fw_build=0))['mc_zero_history_valid']==0
        assert h.with_shunt_currents(dict(fixture,mc_current_quality_age_ms=1500))['mc_current_zero_spans'] is None
        (out/'decoded.json').write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
        report.update(passed=True,checks=encoded['checks'],old_failure_reproduced=replay,
            replay_is_synthetic_matching_measured_extrema=True,actual_raw_time_series_available=False,
            sustained24count_noise_rejected=True,raw1162count_running_peak_preserved=True,
            saturation_and_bias_and_drift_rejected=True,history_encoder_wire_hmi_roundtrip=True,
            history_crc_negative_control=True,physical_zero_verified=False)
    except Exception as exc:
        report.update(passed=False,error=str(exc))
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
