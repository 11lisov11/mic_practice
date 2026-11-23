"""Exercise actual current math/receiver/HMI, with no physical measurements."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import prepare_current_shunt_monitor as package

CASES=r'''
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <initializer_list>
#include "current_core.h"
#include "current_wire.h"
static unsigned checks;
static void check(bool value){++checks;if(!value){fprintf(stderr,"check %u failed\n",checks);exit(1);}}
static const uint16_t offsets[4]={2048,2051,2043,2045};
static void calibrate(cm_core *s) {
 cm_init(s);
 for(unsigned i=0;i<10000;++i) {
  uint8_t pair=(i&1)?2:0;
  cm_sample(s,i/16,0,pair,offsets[cm_path1(pair)],offsets[cm_path2(pair)],0,1);
 }
 check(s->zero_ready && !s->zero_bad);
 for(unsigned j=0;j<4;++j)check(s->offset[j]==offsets[j] && s->count[j]==256);
}
int main() {
 cm_core s;calibrate(&s);
 for(int hz : {5,10,15,20,25,50}) {
  calibrate(&s);
  for(unsigned sample=0;sample<32000;++sample) {
   double t=sample/16000.0,angle=2*3.141592653589793*hz*t;
   int32_t currents[3]={(int)lround(100*sin(angle)),(int)lround(100*sin(angle-2*3.141592653589793/3)),0};
   currents[2]=-currents[0]-currents[1];
   uint32_t ccr[3];
   for(unsigned j=0;j<3;++j)ccr[j]=(uint32_t)((.5+.499*sin(angle+0.4-j*2*3.141592653589793/3))*5311);
   uint8_t pair=cm_choose_pair(ccr[0],ccr[1],ccr[2]);
   bool okay=cm_pair_window(pair,ccr[0],ccr[1],ccr[2],5312-384,772);
   check(okay);
   unsigned p=cm_path1(pair),q=cm_path2(pair),phase1=pair==2?1:0,phase2=pair==0?1:2;
   cm_sample(&s,1000+sample/16,1,pair,offsets[p]-currents[phase1],offsets[q]-currents[phase2],okay,0);
   check(s.window.last[0]+s.window.last[1]+s.window.last[2]==0);
  }
  check(cm_window_valid(&s.published));
  for(unsigned j=0;j<3;++j) {
   double rms=sqrt((double)s.published.square[j]/s.published.n);
   check(fabs(rms-100/sqrt(2.0))<1.0);check(s.published.peak[j]>=99 && s.published.peak[j]<=101);
  }
  cm_sample(&s,3000,0,0,2048,2043,0,1);
  check(s.published.flags&CM_FROZEN);
  auto frozen=s.published;
  for(unsigned i=0;i<1000;++i)cm_sample(&s,3001+i/16,0,0,2048,2043,0,1);
  check(memcmp(&frozen,&s.published,sizeof(frozen))==0);
 }
 cm_init(&s);
 for(unsigned i=0;i<20000;++i)cm_sample(&s,i/16,0,(i&1)?2:0,2048,2048,0,0);
 check(!s.zero_ready); // no automatic zero at a charged bus
 cm_init(&s);
 for(unsigned i=0;i<20000;++i)cm_sample(&s,i/16,0,(i&1)?2:0,3000,3000,0,1);
 check(s.zero_bad && !s.zero_ready);
 cm_init(&s);
 for(unsigned i=0;i<20000;++i)cm_sample(&s,i/16,0,(i&1)?2:0,2000+(i%80),2048,0,1);
 check(s.zero_bad && !s.zero_ready);
 calibrate(&s);
 for(unsigned i=0;i<4000;++i)cm_sample(&s,1000+i/16,1,0,2000,2100,0,0);
 check(!cm_window_valid(&s.published) && s.published.bad>0);
 calibrate(&s);
 for(unsigned i=0;i<4000;++i)cm_sample(&s,1000+i/16,1,0,4095,0,1,0);
 check(!cm_window_valid(&s.published) && (s.published.flags&CM_CLIP));
 cm_window sparse={};sparse.n=16;sparse.start_ms=1000;sparse.end_ms=1200;
 check(!cm_window_valid(&sparse));
 for(unsigned u=0;u<=5312;u+=83)for(unsigned v=0;v<=5312;v+=79)for(unsigned w=0;w<=5312;w+=89) {
  uint8_t pair=cm_choose_pair(u,v,w);unsigned excluded=pair==0?2:pair==1?1:0;
  uint32_t a[3]={u,v,w};check(a[excluded]>=a[(excluded+1)%3] && a[excluded]>=a[(excluded+2)%3]);
 }
 ct_receiver r;ct_reset(&r);uint8_t packet[UV3_FRAME]={};packet[0]=0x55;packet[1]=0xaa;packet[2]=CT_SUMMARY;packet[38]=1;
 uint32_t fw=CT_PEER_BUILD;for(unsigned i=0;i<4;++i)packet[6+i]=(uint8_t)(fw>>(8*i));
 packet[4]=1;uv3_seal(packet);check(ct_receive(&r,packet,fw,true,1000));
 check(!ct_receive(&r,packet,fw,true,1001));
 packet[4]=2;uv3_seal(packet);check(!ct_receive(&r,packet,fw,false,1002));
 check(!ct_receive(&r,packet,0,true,1002));
 packet[4]=2;uv3_seal(packet);check(ct_receive(&r,packet,fw,true,1003));
 uint8_t saved[UV3_FRAME];memcpy(saved,packet,sizeof(packet));
 for(unsigned bit=0;bit<UV3_FRAME*8;++bit) {
  memcpy(packet,saved,sizeof(packet));packet[bit/8]^=1U<<(bit%8);
  check(!ct_receive(&r,packet,fw,true,1004));
 }
 memcpy(packet,saved,sizeof(packet));packet[4]=0;uv3_seal(packet);check(ct_receive(&r,packet,fw,true,3000));
 printf("{\"passed\":true,\"checks\":%u,\"motor_frequencies_hz\":[5,10,15,20,25,50],\"physical_measurements\":false}",checks);
}
'''

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--candidate',type=Path)
    args=p.parse_args()
    if args.candidate:package.OUT=args.candidate.resolve()
    manifest=json.loads((package.OUT/'manifest.json').read_text())
    pair=tuple(manifest['pair_compatibility_ids'])
    out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    r=dict(passed=False,hardware_commands=0,physical_measurements_verified=False)
    try:
        with tempfile.TemporaryDirectory() as folder:
            exe=Path(folder)/'current.exe';src=out/'current_cases.cpp';src.write_text(CASES,encoding='utf-8')
            command=[shutil.which('g++'),'-std=c++17','-Wall','-Wextra','-Werror','-I',str(package.OUT/'nucleo/Inc'),'-I',str(package.OUT/'UNOQ_MOTOR'),str(src),'-o',str(exe)]
            build=subprocess.run(command,capture_output=True,text=True,timeout=60)
            (out/'host_compile.log').write_text(build.stdout+build.stderr,encoding='utf-8');assert build.returncode==0,'Host compilation failed'
            test=subprocess.run([str(exe)],capture_output=True,text=True,timeout=60);assert test.returncode==0,test.stderr
            r['core']=json.loads(test.stdout)
        spec=importlib.util.spec_from_file_location('shunt_hmi',package.OUT/'web_hmi/server.py')
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
        def packet(flags=11):
            raw=bytearray(43);raw[:3]=bytes((0x55,0xaa,manifest['summary_version']));raw[3]=flags;raw[4]=1;raw[5]=100
            raw[6:10]=pair[1].to_bytes(4,'little');raw[10:14]=(5000).to_bytes(4,'little')
            for offset,values in ((14,(707,708,706)),(20,(1000,1001,999)),(26,(500,-600,100))):
                for j,v in enumerate(values):raw[offset+2*j:offset+2*j+2]=v.to_bytes(2,'little',signed=offset==26)
            raw[32]=7;raw[34:36]=(200).to_bytes(2,'little');raw[38]=1
            raw[39:]=module.current_crc32c(raw[:39]).to_bytes(4,'little');return raw
        status=dict(fw_build=pair[0],mc_fw_build=pair[1],mc_age_ms=20,mc_current_age_ms=20,mc_current_packet_hex=packet().hex())
        decoded=module.with_shunt_currents(dict(status));assert decoded['mc_current_telemetry_valid']==1 and decoded['mc_current_rms_a']==[.707,.708,.706]
        assert decoded['mc_current_instant_a']==[.5,-.6,.1]
        checks=2
        for change in ({'mc_current_age_ms':750},{'mc_age_ms':300},{'mc_fw_build':0},{'mc_current_packet_hex':'00'},{'mc_current_packet_hex':'-'},
                       {'mc_current_packet_hex':packet(1).hex()},{'mc_current_packet_hex':packet(17).hex()}):
            bad=module.with_shunt_currents(dict(status,**change));assert bad['mc_current_telemetry_valid']==0 and bad['mc_current_rms_a'] is None;checks+=1
        frozen=module.with_shunt_currents(dict(status,mc_current_packet_hex=packet(7).hex()));assert frozen['mc_current_frozen']==1;checks+=1
        for age in (-1, 1500):
            stale=module.with_shunt_currents(dict(status,mc_current_detail_age_ms=age,
                mc_current_detail_hex='-',mc_current_raw_adc=[2048]*4,mc_current_offsets_adc=[2048]*4))
            assert stale['mc_current_telemetry_valid']==1 and stale['mc_current_raw_adc'] is None
            assert stale['mc_current_offsets_adc'] is None;checks+=1
        stored=dict(fw_build=2026102403,mc_fw_build=2026102402,rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
        assert module._vbus_calibration_identity_matches(stored,dict(stored,fw_build=pair[0],mc_fw_build=pair[1]))
        assert module.manual_scalar_supported(dict(status,manual_scalar_capable=1));checks+=2
        js=package.OUT/'web_hmi/static/app.js'
        parsed=subprocess.run(['node','--check',str(js)],capture_output=True,text=True,timeout=20)
        assert parsed.returncode==0,parsed.stderr
        # The entire V/f and power PWM implementation must remain byte-identical.
        vf='nucleo/MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLibACIM/Any/Src/'
        for name in ('acim_vf_control.c','pwm.c'):
            assert (package.OUT/(vf+name)).read_bytes()==(package.NUC/(vf+name)).read_bytes()
        assert (package.OUT/'UNOQ_MOTOR/uart_v3_transport.h').read_bytes()==(package.BASE/'UNOQ_MOTOR/uart_v3_transport.h').read_bytes()
        r.update(passed=True,hmi_checks=checks,frontend_syntax_pass=True,modulation_and_uart_command_code_unchanged=True)
    except Exception as exc:r.update(passed=False,error=str(exc))
    (out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r));return 0 if r['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
