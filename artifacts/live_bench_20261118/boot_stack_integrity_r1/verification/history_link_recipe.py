"""Full history packet path through the actual Uno FIFO adapter; offline only."""
import json,subprocess,shutil
import prepare_boot_stack_integrity as p
from replay_observer_pair_noise import replay_pair_record
def main():
 out=p.OUT/'verification/history_link_r1';out.mkdir(parents=True,exist_ok=False)
 fixture=p.BASE.parent/'observer_start_history_r1/verification/synthetic_ARM_fixture.bin'
 previous=p.OUT/'verification/Uno_RX_kernel_r1';pre=p.read(previous/'actual_Uno.cpp').split('int main(){',1)[0]
 code=pre+r'''
#include <fstream>
#include <string>
#include "observer_start_history.h"
namespace peer {
#include "observer_start_history_wire.h"
}
static peer::nh_receiver receiver;
static uint8_t packet_in[43];static unsigned fill;
static NucleoBufferedSerial*port;
static void collect(){
 while(port->available()){
  packet_in[fill++]=(uint8_t)port->read();
  if(fill==43){assert(peer::nhr_receive(&receiver,packet_in,2026111810U,2026111810U));fill=0;}
 }
}
static unsigned wire_count,commands;
static void transmit(nh_capture&c){
 uint8_t packet[43];assert(nh_packet(&c,packet,1));
 for(unsigned i=0;i<43;++i){arrive(packet[i]);++wire_count;
  if(wire_count%8==0)fire();step_tx();}
 fire();collect();nh_sent(&c);
}
static void save(std::string name,const void*data,size_t n){std::ofstream f(name,std::ios::binary);f.write((const char*)data,n);assert(f.good());}
int main(int argc,char**argv){
 assert(argc==3);std::ifstream f(argv[1],std::ios::binary);std::vector<uint8_t>b((std::istreambuf_iterator<char>(f)),{});
 assert(b.size()==264+659*236);ma_observer initial;ma_motor m;
 memcpy(&initial,b.data(),204);memcpy(&m,b.data()+204,52);
 init();NucleoBufferedSerial serial(&dev);port=&serial;port->begin(921600);
 static nh_capture capture;nh_begin(&capture,&initial,&m,2026111810U,0x12345678U,0);
 uint8_t command[43]={0xaa,0x55,3};uv3_seal(command);
 const uint8_t*at=b.data()+264;
 for(unsigned i=0;i<659;++i,at+=236){
  float input[5];ma_observer post;memcpy(input,at,20);memcpy(&post,at+32,204);
  nh_step(&capture,&post,input,nh_u32(at+20),nh_u32(at+24),nh_u32(at+28),0xff000000U+i*170000U,0xff000000U+i*170000U+80000U);
  if(i%50==0){assert(port->write(command,43)==43);++commands;}
  transmit(capture);
 }
 for(unsigned page=0;page<NH_META_PAGES;++page)transmit(capture);
 for(unsigned i=0;i<100&&(!hwtx.empty()||(regs.CR1&128));++i)step_tx();
 assert(!fill&&peer::nhr_exact(&receiver)&&receiver.count==659);
 assert(!port->stats().errors&&!port->stats().dropped&&port->stats().max_batch<=8);
 assert(wire.size()==commands*43U);for(unsigned i=0;i<commands;++i)assert(!memcmp(wire.data()+i*43U,command,43));
 std::string dest=argv[2];save(dest+"/meta.bin",receiver.meta,524);save(dest+"/rows.bin",receiver.rows,receiver.count*22);
 save(dest+"/checkpoints.bin",receiver.checkpoints,receiver.count/16*4);
 printf("{\"passed\":true,\"rows\":659,\"received_bytes\":%u,\"full_duplex_OFF_frames\":%u,\"hardware_RX_errors\":0,\"software_RX_drops\":0,\"actual_recorder_and_Uno_adapter\":true,\"simulated_FIFO\":true,\"hardware_commands\":0}\n",wire_count,commands);
}
'''
 cpp=out/'link.cpp';p.write(cpp,code);exe=cpp.with_suffix('.exe')
 r=subprocess.run([shutil.which('g++'),'-O2','-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-misleading-indentation',
  '-I',str(previous/'stubs'),'-I',str(p.OUT/'nucleo/Inc'),'-I',str(p.OUT/'UNOQ_MOTOR'),str(cpp),'-o',str(exe)],capture_output=True,text=True)
 p.write(out/'build.log',r.stdout+r.stderr);r.check_returncode()
 record=out/'record';record.mkdir();r=subprocess.run([str(exe),str(fixture),str(record)],capture_output=True,text=True)
 p.write(out/'run.log',r.stdout+r.stderr);r.check_returncode();result=json.loads(r.stdout)
 original=p.BASE.parent/'observer_start_history_r1/verification/synthetic_record'
 for name in ('rows.bin','checkpoints.bin'):assert (record/name).read_bytes()==(original/name).read_bytes(),name
 assert (record/'meta.bin').read_bytes()[64:]==(original/'meta.bin').read_bytes()[64:]
 elf=p.OUT/'release/nucleo_2026111810_stack_guard.elf'
 real=p.ROOT/'artifacts/live_bench_20261118/exact_nis_input_release_r1/FOC_5Hz_r2/observer_trace.bin'
 replay=replay_pair_record(real.read_bytes(),elf,2026111802);assert replay['passed']
 result.update(rows_and_checkpoints_bit_exact=True,initial_terminal_state_model_bit_exact=True,real_saved_NIS_step_replay=replay)
 p.write(out/'report.json',json.dumps(result,indent=2)+'\n');print(json.dumps(result))

