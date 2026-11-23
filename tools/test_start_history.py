"""PC-only recorder/wire faults and full-sequence replay of the actual ARM kernel."""
import json,struct,subprocess,shutil
from pathlib import Path
import prepare_start_history_release as p
from replay_start_history import ArmObserver,replay

def main():
 out=p.OUT/'verification';out.mkdir(exist_ok=False)
 elf=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
 saved=json.loads(p.read(p.BASE/'FOC_5Hz_r2/observer_trace_decoded.json'))['first_nis_replay']
 # Model copied exactly from the real record; sequence is SYNTHETIC, not a new
 # measurement and not a reconstruction of the missing historical startup.
 record=(p.BASE/'FOC_5Hz_r2/observer_trace.bin').read_bytes()
 motor=record[1432+176:1432+228]
 initial=bytearray(204)
 for i,v in enumerate((.0025,.0025,.0025,.0025,900.,.0025)):struct.pack_into('<f',initial,24+(i*6+i)*4,v)
 arm=ArmObserver(elf);prior=bytes(initial);fixture=bytes(initial)+motor+struct.pack('<II',0,659)
 for index in range(659):
  # Nonuniform dt, all153 real pair compositions and a control-mode change.
  # Zero-state prediction is exact until a deliberate final current innovation.
  counts=__import__('replay_start_history').pair_counts(index%153)
  values=struct.pack('<5f',.30 if index==658 else 0.,.0,0.,0.,.001+(index%3-1)*1e-7)
  fpscr=0x01000000 if index>=200 else 0
  rc,post,_=arm.step(prior,motor,values,fpscr,counts)
  nis=struct.unpack_from('<f',post,168)[0]
  assert (nis>=25)==(index==658),(index,nis)
  fixture+=values+struct.pack('<III',counts,fpscr,rc)+post;prior=post
 (out/'synthetic_ARM_fixture.bin').write_bytes(fixture)
 code=r'''
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <fstream>
#include "observer_start_history.h"
namespace peer {
#include "observer_start_history_wire.h"
}
static unsigned tests;
#define CHECK(x) do{assert(x);++tests;}while(0)
static bool drain(nh_capture&c,peer::nh_receiver&r){
 uint8_t packet[UV3_FRAME];if(!nh_packet(&c,packet,1))return false;
 CHECK(uv3_crc_ok(packet));CHECK(peer::nhr_receive(&r,packet,2026111804U,2026111804U));nh_sent(&c);return true;
}
static void save(const char*path,const void*data,size_t n){FILE*f=fopen(path,"wb");assert(f);assert(fwrite(data,1,n,f)==n);fclose(f);}
int main(int argc,char**argv){
 assert(argc==3);std::ifstream file(argv[1],std::ios::binary);
 std::vector<uint8_t>b((std::istreambuf_iterator<char>(file)),{});assert(b.size()>264);
 ma_observer initial;ma_motor m;memcpy(&initial,b.data(),204);memcpy(&m,b.data()+204,52);
 uint32_t count=nh_u32(b.data()+260);CHECK(count==659U);
 for(unsigned code=0;code<153;++code)CHECK(nh_pair_code(nh_pair_counts(code))==code);
 CHECK(nh_pair_code(0)==255);CHECK(nh_pair_counts(153)==0);
 static nh_capture c;static peer::nh_receiver r;
 nh_begin(&c,&initial,&m,2026111804U,0x12345678U,0);
 const uint8_t*ptr=b.data()+264;ma_observer post=initial;
 for(unsigned index=0;index<count;++index,ptr+=236){
  float input[5];memcpy(input,ptr,20);memcpy(&post,ptr+32,204);
  int event=nh_step(&c,&post,input,nh_u32(ptr+20),nh_u32(ptr+24),(int)nh_u32(ptr+28),
   0xff000000U+index*170000U,0xff000000U+index*170000U+80000U);
  CHECK(event==(index==658U));CHECK(c.frozen==(index==658U));
  CHECK(drain(c,r)); // deterministic transport, not target UART timing
 }
 CHECK(c.frozen&&c.meta.count==659&&c.meta.event_count==659&&c.meta.flags==NH_EVENT);
 CHECK(!r.complete);for(unsigned page=0;page<NH_META_PAGES;++page)CHECK(drain(c,r));
 CHECK(peer::nhr_exact(&r));CHECK(r.count==count);CHECK(!memcmp(&c.meta,r.meta,NH_META_BYTES));
 CHECK(!memcmp(&post,r.meta+320,204));
 nh_meta before=c.meta;nh_begin(&c,&initial,&m,2026111804U,7,0);nh_freeze(&c,&post,NH_STOP);
 CHECK(!memcmp(&before,&c.meta,sizeof(before))); // STOP/CLEAR/next prepare never overwrites first history
 float zero[5]={0,0,0,0,.001f};CHECK(!nh_step(&c,&post,zero,16U,0,0,1,2));
 std::string dest=argv[2];save((dest+"/meta.bin").c_str(),r.meta,NH_META_BYTES);
 save((dest+"/rows.bin").c_str(),r.rows,r.count*NH_ROW);
 save((dest+"/checkpoints.bin").c_str(),r.checkpoints,r.count/16U*4U);
 // Corrupt wire CRC, foreign firmware, changed epoch and missing/reordered row.
 static nh_capture f;static peer::nh_receiver bad;
 ma_observer step=initial;step.steps=1;nh_begin(&f,&initial,&m,2026111804U,2,0);
 CHECK(!nh_step(&f,&step,zero,16U,0,0,100,200));uint8_t packet[UV3_FRAME];CHECK(nh_packet(&f,packet,0));
 packet[12]^=1;CHECK(!peer::nhr_receive(&bad,packet,2026111804U,2026111804U));CHECK(bad.gap);
 packet[12]^=1;memset(&bad,0,sizeof(bad));CHECK(!peer::nhr_receive(&bad,packet,1,2026111804U));
 memset(&bad,0,sizeof(bad));packet[5]=1;uv3_seal(packet);
 CHECK(!peer::nhr_receive(&bad,packet,2026111804U,2026111804U));CHECK(bad.gap);
 // Queue pressure is nonblocking and reports a GAP, never wraps old rows.
 memset(&f,0,sizeof(f));nh_begin(&f,&initial,&m,2026111804U,3,0);
 for(unsigned i=0;i<NH_QUEUE+1U;++i){step.steps=i+1;nh_step(&f,&step,zero,16U,0,0,i,i);}
 CHECK(f.head-f.tail==NH_QUEUE);CHECK(f.meta.flags&NH_GAP);CHECK(f.meta.count==5);
 // First event during warmup is captured, with no qualification shortcut.
 memset(&f,0,sizeof(f));nh_begin(&f,&initial,&m,2026111804U,4,0);step.steps=1;step.nis=25;
 CHECK(nh_step(&f,&step,zero,16U,0,0,1,2));CHECK(f.meta.event_count==1&&f.frozen);
 // No NIS event -> STOP seals complete prefix. Capacity exhaustion explicit.
 memset(&f,0,sizeof(f));nh_begin(&f,&initial,&m,2026111804U,5,0);step.nis=0;
 nh_step(&f,&step,zero,16U,0,0,1,2);nh_freeze(&f,&step,NH_STOP);CHECK(f.frozen&&f.meta.flags==NH_STOP);
 memset(&f,0,sizeof(f));nh_begin(&f,&initial,&m,2026111804U,6,0);
 for(unsigned i=0;i<NH_CAPACITY+1U;++i){step.steps=i+1;nh_step(&f,&step,zero,16U,0,0,i,i);f.tail=f.head;}
 CHECK(f.frozen&&f.meta.count==NH_CAPACITY&&f.meta.flags==NH_OVERFLOW);
 printf("{\"passed\":true,\"checks\":%u,\"rows\":%u,\"nucleo_capture_bytes\":%u,\"uno_capture_bytes\":%u,\"synthetic_fixture\":true,\"target_timing_measured\":false}\n",
  tests,count,(unsigned)sizeof(nh_capture),(unsigned)sizeof(peer::nh_receiver));
}
'''
 cpp=out/'codec.cpp';p.write(cpp,code)
 exe=cpp.with_suffix('.exe')
 result=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',
  '-Wno-unused-function','-Wno-misleading-indentation','-I',str(p.OUT/'nucleo/Inc'),
  '-I',str(p.OUT/'UNOQ_MOTOR'),str(cpp),'-o',str(exe)],capture_output=True,text=True)
 p.write(out/'codec_build.log',result.stdout+result.stderr);result.check_returncode()
 record_dir=out/'synthetic_record';record_dir.mkdir()
 result=subprocess.run([str(exe),str(out/'synthetic_ARM_fixture.bin'),str(record_dir)],capture_output=True,text=True)
 p.write(out/'codec_run.log',result.stdout+result.stderr);result.check_returncode();codec=json.loads(result.stdout)
 replayed=replay(record_dir,elf,p.NEW[1],out/'reconstructed_states.jsonl')
 assert replayed['rows']==659 and replayed['first_NIS_ge25']==659 and replayed['terminal_51_words_bit_exact']
 negative=[]
 for label,part,mutate in (
  ('truncated_rows','rows.bin',lambda b:b[:-22]),
  ('changed_input','rows.bin',lambda b:b[:220]+bytes([b[220]^1])+b[221:]),
  ('changed_checkpoint','checkpoints.bin',lambda b:bytes([b[0]^1])+b[1:]),
  ('changed_metadata','meta.bin',lambda b:b[:320]+bytes([b[320]^1])+b[321:])):
  directory=out/label;shutil.copytree(record_dir,directory)
  path=directory/part;path.write_bytes(mutate(path.read_bytes()))
  try:replay(directory,elf,p.NEW[1])
  except ValueError as exc:negative.append(dict(case=label,rejected=str(exc)))
  else:raise AssertionError('Corrupt record accepted: '+label)
 report=dict(passed=True,codec=codec,replay=replayed,corruptions_rejected=negative,
  hardware_commands=0,physical_startup_not_recovered=True,new_physical_NIS_cause_NOT_proven=True)
 p.write(out/'report.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
