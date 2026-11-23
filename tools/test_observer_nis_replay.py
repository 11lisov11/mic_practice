"""Capture immutability, complete covariance, schema/CRC and exact ARM replay.

Everything is synthetic/offline. No fixture is labelled a physical motor record.
"""
import ctypes as ct
import importlib.util
import json
import shutil
import struct
import subprocess

import prepare_observer_nis_replay as p
from check_observer_equations_offline import Motor,Observer
from replay_observer_nis import arm_step,replay,record_payload,crc
from analyze_observer_nis import sha


def main():
    out=p.OUT/'verification';out.mkdir(exist_ok=True)
    source=out/'capture_test.cpp';dll=out/'capture_test.dll'
    source.write_text(r'''
#include <cassert>
#include "observer_trace_core.h"
#include "observer_trace_wire.h"
#include "foc_experiment.h"
static od_sample row(const ma_observer*o,const float*v){
 od_sample r={};r.steps=o->steps;r.reasons=OD_NIS;r.nis=o->nis;
 r.ia=v[0];r.ib=v[1];r.va=v[2];r.vb=v[3];r.dt=v[4];
 r.cycles=310000;r.control_adc_cycles=r.observer_adc_cycles=r.bin_cycles=300000;
 r.observation_cycles=220320;r.window_first_cycles=140640;r.window_count=16;r.forecast_dt=79680.f/170000000.f;
 return r;
}
extern "C" __declspec(dllexport) int capture(const ma_observer*prior,const ma_observer*post,
 const ma_motor*m,const float*v,int rc,uint8_t*blob){
 od_capture c={};od_begin(&c,2026111714U);
 int staged=od_replay_stage(&c,prior,m,v[0],v[1],v[2],v[3],v[4]);
 od_replay_commit(&c,post,rc,staged);od_sample r=row(post,v);od_push(&c,&r);od_freeze(&c,rc);
 c.blob.header.crc=odw_crc((const uint8_t*)&c.blob);memcpy(blob,&c.blob,OD_BYTES);
 return c.replay_latched;
}
extern "C" __declspec(dllexport) unsigned checks(){
 unsigned n=0;ma_motor m=FE_ESTIMATED_MOTOR;ma_observer prior={};
 for(unsigned i=0;i<6;++i){prior.x[i]=.01f*(i+1);for(unsigned j=0;j<6;++j)prior.p[i][j]=.001f*(i*6+j+1);}
 prior.steps=499;prior.rejected=3;
 float v[5]={.9f,-.5f,8.f,4.f,.001f};od_capture c={};od_begin(&c,2026111714U);
 int staged=od_replay_stage(&c,&prior,&m,v[0],v[1],v[2],v[3],v[4]);assert(staged);++n;
 ma_observer post=prior;post.steps=500;post.nis=25.f;post.x[0]+=.1f;post.p[0][5]+=.2f;
 od_replay_commit(&c,&post,0,staged);assert(c.replay_latched&&!c.seen_valid);++n;
 assert(!memcmp(c.blob.replay.prior_x,prior.x,sizeof(prior.x)));++n;
 assert(!memcmp(c.blob.replay.prior_p,prior.p,sizeof(prior.p)));++n;
 assert(!memcmp(c.blob.replay.post_x,post.x,sizeof(post.x)));++n;
 assert(!memcmp(c.blob.replay.post_p,post.p,sizeof(post.p)));++n;
 assert(!memcmp(&c.blob.replay.motor,&m,sizeof(m)));++n;
 assert(!memcmp(c.blob.replay.input,v,sizeof(v)));++n;
 auto first=c.blob.replay;od_begin(&c,123);assert(!memcmp(&first,&c.blob.replay,sizeof(first)));++n;
 assert(!od_replay_stage(&c,&post,&m,0,0,0,0,.001f));++n;
 post.nis=100;od_replay_commit(&c,&post,5,1);assert(!memcmp(&first,&c.blob.replay,sizeof(first)));++n;
 od_sample r=row(&post,v);od_push(&c,&r);od_freeze(&c,5);assert(c.blob.header.schema==4&&(c.blob.header.flags&4));++n;
 auto frozen=c;od_begin(&c,999);od_push(&c,&r);od_freeze(&c,0);
 assert(!memcmp(&frozen,&c,sizeof(c)));++n;
 od_capture no_loss={};od_begin(&no_loss,2026111714U);post.nis=24.999f;
 staged=od_replay_stage(&no_loss,&prior,&m,1,2,3,4,.001f);od_replay_commit(&no_loss,&post,0,staged);
 assert(!no_loss.replay_latched);++n;
 od_push(&no_loss,&r);od_freeze(&no_loss,0);od_replay zero={};
 assert(!(no_loss.blob.header.flags&4)&&!memcmp(&zero,&no_loss.blob.replay,sizeof(zero)));++n;
 prior.steps=498;od_capture warm={};assert(!od_replay_stage(&warm,&prior,&m,1,2,3,4,.001f));++n;
 assert(sizeof(od_blob)==1888&&sizeof(od_replay)==456&&sizeof(od_capture)==2052);++n;
 // Receive all63 pages in reverse order, reject transmission while ON,
 // detect conflicting duplicates and corrupted bytes with correct packet CRC.
 c.blob.header.crc=odw_crc((const uint8_t*)&c.blob);od_receiver rx={};
 for(int page=OD_PAGES-1;page>=0;--page){
  uint8_t packet[43]={};packet[0]=0x55;packet[1]=0xaa;packet[2]=OD_WIRE;packet[3]=4;packet[4]=1;
  packet[5]=(uint8_t)page;packet[6]=OD_PAGES;packet[7]=page==62?28:30;packet[38]=1;
  memcpy(packet+8,(const uint8_t*)&c.blob+page*30,packet[7]);uv3_seal(packet);
  assert(!odw_receive(&rx,packet,2026111714U,2026111714U,false));++n;
  assert(odw_receive(&rx,packet,2026111714U,2026111714U,true));++n;
 }
 assert(rx.complete&&!memcmp(rx.data,&c.blob,1888));++n;
 uint8_t bad[43]={};bad[0]=0x55;bad[1]=0xaa;bad[2]=OD_WIRE;bad[3]=4;bad[4]=1;
 bad[5]=0;bad[6]=OD_PAGES;bad[7]=30;bad[38]=1;memcpy(bad+8,&c.blob,30);bad[8]^=1;uv3_seal(bad);
 assert(!odw_receive(&rx,bad,2026111714U,2026111714U,true));++n;
 bad[8]^=1;bad[3]=3;uv3_seal(bad);assert(!odw_receive(&rx,bad,2026111714U,2026111714U,true));++n;
 bad[3]=4;uv3_seal(bad);assert(!odw_receive(&rx,bad,2026111712U,2026111714U,true));++n;
 return n;
}
''',encoding='utf8')
    run=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-shared','-Wall','-Wextra','-Werror',
                         '-I',str(p.OUT/'nucleo/Inc'),str(source),'-o',str(dll)],capture_output=True,text=True)
    (out/'capture_build.log').write_text(run.stdout+run.stderr,encoding='utf8');run.check_returncode()
    lib=ct.CDLL(str(dll));lib.capture.argtypes=[ct.POINTER(Observer),ct.POINTER(Observer),ct.POINTER(Motor),ct.POINTER(ct.c_float),ct.c_int,ct.POINTER(ct.c_ubyte)]
    checks=lib.checks()
    elf=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
    modelbytes=struct.pack('<7fI5f',12.23,11.00442222558575,.528093860573909,.528093860573909,.4944775988161633,.0002,.00014790613961630187,1,.25,.8,1.35,400,12)
    model=Motor.from_buffer_copy(modelbytes)
    matrix=[0.]*36
    for i in range(6):matrix[6*i+i]=[.0025,.0025,.0025,.0025,900,.0025][i]
    matrix[1]=matrix[6]=.0001;matrix[4]=matrix[24]=.002
    priorbytes=struct.pack('<49f2I',*([.3,-.1,.2,.03,15.,0.]+matrix+[0.]*7),499,0)
    inputbytes=struct.pack('<5f',.9,-.5,8,4,.001)
    rc,postbytes=arm_step(elf,priorbytes,modelbytes,inputbytes,0)
    before=Observer.from_buffer_copy(priorbytes);after=Observer.from_buffer_copy(postbytes)
    inputs=(ct.c_float*5).from_buffer_copy(inputbytes);raw=(ct.c_ubyte*1888)()
    assert lib.capture(ct.byref(before),ct.byref(after),ct.byref(model),inputs,rc,raw)==1
    blob=bytes(raw);record=out/'synthetic_ARM_first_NIS.bin';record.write_bytes(blob)
    payload=record_payload(blob,p.NEW[1]);result=replay(payload,elf)
    assert result['passed'] and result['bit_exact'];checks+=1
    (out/'ARM_replay_report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    # Corrupt record must fail before executing ARM. Corrupt post covariance
    # with a fresh CRC must produce a precise word mismatch, not be accepted.
    corrupt=bytearray(blob);corrupt[1500]^=1
    try:record_payload(corrupt,p.NEW[1])
    except ValueError:checks+=1
    else:raise AssertionError('corrupt capture accepted')
    changed=bytearray(payload);changed[248+24+4]^=1
    mismatch=replay(changed,elf);assert not mismatch['passed'] and mismatch['differences'][0]['observer_word']==7;checks+=1
    # MCU FPSCR controls are part of the replay, not host ambient settings.
    fz=1<<24;rc2,post2=arm_step(elf,priorbytes,modelbytes,inputbytes,fz)
    changed=bytearray(payload);changed[248:444]=post2[:196];struct.pack_into('<3I',changed,444,fz,struct.unpack_from('<I',post2,200)[0],rc2)
    assert replay(changed,elf)['passed'];checks+=1
    spec=importlib.util.spec_from_file_location('replay_hmi',p.OUT/'web_hmi/server.py')
    hmi=importlib.util.module_from_spec(spec);spec.loader.exec_module(hmi)
    dec=hmi.decode_observer_trace_hex(blob.hex(),p.NEW[1]);assert dec['first_nis_replay']['nis']==after.nis;checks+=1
    for cap,fw in [(p.BASE/'FOC_5Hz_20261117_r1',2026111612),
                   (p.ROOT/'artifacts/live_bench_20261116/rpc_hmi_admission_r1/FOC_trial_r1',2026111606)]:
        old=(cap/'observer_trace.bin').read_bytes()
        olddec=hmi.decode_observer_trace_hex(old.hex(),fw)
        assert olddec['schema'] in (2,3) and olddec['first_nis_replay'] is None;checks+=1
    for rel,h in json.loads(p.read(p.BASE/'source_hashes.json')).items():assert sha(p.BASE/rel)==h,rel
    report=dict(passed=True,checks=checks,synthetic_fixture=True,hardware_commands=0,
        complete_covariance_not_diagonal_only=True,ARM_replay_bit_exact=result['bit_exact'],
        ARM_observer_words_compared=51,wire_bytes=1888,pages=63,
        prior_capture_survives_STOP_CLEAR_later_start=True,target_timing_measured=False)
    (out/'capture_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report))


if __name__=='__main__':main()
