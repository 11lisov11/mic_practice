"""Actual zero core, target packet encoder and HMI tests; no hardware access."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PREAMBLE=r'''
#include <cstdio>
#include <cstdlib>
#include <math.h>
#include "current_core.h"
#include "current_wire.h"
#define ADC_REFERENCE_VOLTAGE 3.3f
#define RSHUNT 0.04f
#define AMPLIFICATION_GAIN 2.1f
static cm_core state;
static uint32_t packets;
static uint32_t tick;
static uint32_t HAL_GetTick(){return tick;}
static uint32_t __get_PRIMASK(){return 0;}
static void __disable_irq(){}
static void __set_PRIMASK(uint32_t){}
static unsigned checks;
static void check(bool x){++checks;if(!x){fprintf(stderr,"zero check %u failed\n",checks);exit(1);}}
static uint32_t index_;
static const uint16_t bias[4]={2048,2051,2043,2045};
static void prime(cm_core *s) {
 cm_init(s);for(index_=0;index_<8000;++index_) {
  uint8_t pair=(index_&1)?2:0;cm_sample(s,index_/16,0,pair,bias[cm_path1(pair)],bias[cm_path2(pair)],0,1);
 }
 check(!s->zero_ready && !s->zero_attempts);
}
static void block(cm_core *s,int delta=0,bool spike=false,bool invalid_bias=false) {
 for(unsigned j=0;j<512;++j,++index_) {
  uint8_t pair=(j&1)?2:0;unsigned p=cm_path1(pair),q=cm_path2(pair);
  uint16_t a=invalid_bias?3000:bias[p]+delta,b=invalid_bias?3000:bias[q]+delta;
  if(spike && p==1 && s->count[p]==100)a+=49;
  cm_sample(s,index_/16,0,pair,a,b,0,1);
 }
}
'''
CASES=r'''
int main() {
 cm_core s;prime(&s);block(&s,0,true);
 check(!s.zero_ready && !s.zero_bad && s.zero_attempts==1 && s.zero_last_bad==1);
 check(s.zero_high[1]-s.zero_low[1]==49);
 block(&s);block(&s);check(!s.zero_ready && s.zero_stable==2);
 block(&s);check(s.zero_ready && !s.zero_bad && s.zero_attempts==4 && s.zero_stable==3);
 for(unsigned i=0;i<4;++i)check(s.offset[i]==bias[i] && s.count[i]==256);
 state=s;uint8_t summary[UV3_FRAME],detail[UV3_FRAME],quality[UV3_FRAME];
 mic_current_packet(summary,0,CT_PEER_BUILD);mic_current_packet(detail,1,CT_PEER_BUILD);mic_current_packet(quality,2,CT_PEER_BUILD);
 check(quality[2]==CT_QUALITY && quality[5]==4 && quality[30]==3 && quality[32]==3 && quality[33]==8 && quality[34]==40 && quality[35]==2);
 check(uv3_crc_ok(summary) && uv3_crc_ok(detail) && uv3_crc_ok(quality));
 ct_receiver rx;ct_reset(&rx);check(ct_receive(&rx,quality,CT_PEER_BUILD,true,1010));check(rx.has_quality);
 check(!ct_receive(&rx,quality,CT_PEER_BUILD,true,1011));
 uint8_t damaged[UV3_FRAME];memcpy(damaged,quality,sizeof(damaged));damaged[14]^=1;
 check(!ct_receive(&rx,damaged,CT_PEER_BUILD,true,1012));
 prime(&s);for(unsigned i=0;i<8;++i)block(&s,0,true);
 check(s.zero_bad && !s.zero_ready && s.zero_attempts==8 && s.zero_stable==0 && s.zero_last_bad==1);
 for(unsigned i=0;i<2;++i){block(&s);}
 check(s.zero_attempts==8 && !s.zero_ready);
 prime(&s);for(unsigned i=0;i<8;++i)block(&s,0,false,true);
 check(s.zero_bad && !s.zero_ready && s.zero_last_bad==2);
 prime(&s);for(unsigned i=0;i<8;++i)block(&s,4*i);
 check(s.zero_bad && !s.zero_ready && s.zero_stable==1 && s.zero_last_bad==4);
 prime(&s);block(&s,0);block(&s,1);block(&s,2);
 check(s.zero_ready && s.offset[0]==bias[0]+1);
 prime(&s);block(&s);check(s.zero_stable==1);
 cm_sample(&s,index_/16,0,0,2048,2043,0,0);check(!s.zero_stable && !s.count[0]);
 check(!s.zero_ready && !s.zero_bad);
 prime(&s);block(&s);cm_sample(&s,index_/16,1,0,2048,2043,1,0);
 check(!s.zero_stable && !s.count[0] && !s.zero_ready);
 printf("{\"passed\":true,\"checks\":%u,\"summary\":\"",checks);
 for(unsigned i=0;i<UV3_FRAME;++i){printf("%02x",summary[i]);}
 printf("\",\"detail\":\"");
 for(unsigned i=0;i<UV3_FRAME;++i){printf("%02x",detail[i]);}
 printf("\",\"quality\":\"");
 for(unsigned i=0;i<UV3_FRAME;++i){printf("%02x",quality[i]);}
 printf("\"}");
}
'''
OLD=r'''
#include <cstdio>
#include "current_core.h"
int main(){cm_core s;cm_init(&s);for(unsigned n=0;n<16000;++n){unsigned p=(n&1)?2:0;
 unsigned raw=2048;if(n==8201)raw+=49;cm_sample(&s,n/16,0,p,raw,2048,0,1);}
 printf("{\"old_failure_reproduced\":%s}",s.zero_bad&&!s.zero_ready?"true":"false");}
'''

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--outdir',type=Path,required=True)
    args=p.parse_args();c=args.candidate.resolve();out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    r=dict(passed=False,hardware_commands=0,physical_measurements_verified=False)
    try:
        source=(c/'nucleo/Src/current_shunt.c').read_text()
        encoder=source[source.index('static uint16_t ma_u'):]
        # Test the actual current encoder; a later independent diagnostic
        # packet function requires hardware/capture globals outside this unit.
        if '\nuint8_t mic_current_peak_packet(' in encoder:
            encoder=encoder[:encoder.index('\nuint8_t mic_current_peak_packet(')]
        unit=out/'actual_zero_and_encoder.cpp';unit.write_text(PREAMBLE+encoder+CASES)
        with tempfile.TemporaryDirectory() as folder:
            exe=Path(folder)/'zero.exe'
            command=[shutil.which('g++'),'-std=c++17','-Wall','-Wextra','-Werror','-I',str(c/'nucleo/Inc'),'-I',str(c/'UNOQ_MOTOR'),str(unit),'-o',str(exe)]
            compile_=subprocess.run(command,capture_output=True,text=True,timeout=60)
            (out/'compile.log').write_text(compile_.stdout+compile_.stderr);assert compile_.returncode==0,'Zero/encoder compilation failed'
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20);assert run.returncode==0,run.stderr
            encoded=json.loads(run.stdout);r.update(passed=encoded['passed'],zero_checks=encoded['checks'])
            old=out/'old_one_block.cpp';old.write_text(OLD)
            old_build=subprocess.run([shutil.which('g++'),'-std=c++17','-I',str(c.parent/'current_shunt_monitor_r3/nucleo/Inc'),str(old),'-o',str(exe)],capture_output=True,text=True,timeout=60)
            assert old_build.returncode==0,old_build.stderr
            replay=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
            assert replay.returncode==0
            r.update(json.loads(replay.stdout));assert r['old_failure_reproduced']
        spec=importlib.util.spec_from_file_location('zero_quality_hmi',c/'web_hmi/server.py')
        h=importlib.util.module_from_spec(spec);sys.modules[spec.name]=h;spec.loader.exec_module(h)
        pair=json.loads((c/'manifest.json').read_text())['pair_compatibility_ids']
        s=dict(fw_build=pair[0],mc_fw_build=pair[1],mc_age_ms=10,mc_current_age_ms=10,mc_current_detail_age_ms=10,
               mc_current_quality_age_ms=10,mc_current_packet_hex=encoded['summary'],mc_current_detail_hex=encoded['detail'],mc_current_quality_hex=encoded['quality'])
        d=h.with_shunt_currents(s.copy())
        assert d['mc_current_zero_ready']==1 and d['mc_current_zero_attempts']==4 and d['mc_current_zero_stable']==3
        assert d['mc_current_zero_spans']==[0]*4 and d['mc_current_offsets_adc']==[2048,2051,2043,2045]
        assert d['mc_current_telemetry_valid']==0 and d['mc_current_rms_a'] is None
        for age in (-1,1500):
            stale=h.with_shunt_currents(dict(s,mc_current_quality_age_ms=age))
            assert stale['mc_current_zero_spans'] is None
        r.update(passed=True,hmi_quality_checks=5,actual_encoder_roundtrip=True)
    except Exception as exc:r.update(passed=False,error=str(exc))
    (out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r));return 0 if r['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
