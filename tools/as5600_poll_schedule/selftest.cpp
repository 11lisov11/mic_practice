#include "as5600_poll_section.h"
#include <cassert>
#include <cstdio>
#include <vector>
using namespace encdiag;
struct Scheduler {
  static bool locked;static unsigned locks,unlocks,irqs;
  static void lock(){assert(!locked);locked=true;++locks;}
  static void unlock(){assert(locked);locked=false;++unlocks;}
  static void irq(){++irqs;} // Scheduling scope does NOT mask interrupt work.
};
bool Scheduler::locked=false;unsigned Scheduler::locks=0,Scheduler::unlocks=0,Scheduler::irqs=0;
struct TimedIo {
  uint32_t t=0,due=0,web_delay=4132;int phase=0;
  unsigned waits=0,bytes_read=0,resets=0;uint32_t forced_error=0;
  bool stall=false,long_irq=false;
  uint32_t now_us(){return t;}
  uint32_t status(){
    t+=1;
    if(forced_error&&phase==4)return forced_error|RXNE;
    if(phase==4&&stall)return 0;
    if(t<due)return 0;
    if(phase==1)return TXIS;
    if(phase==2)return TC;
    if(phase>=3&&phase<=5)return RXNE;
    if(phase==6)return STOPF;
    return 0;
  }
  bool lines_high(){return true;}
  void clear(){if(phase==6)phase=0;}
  void begin_write(){phase=1;due=t+80;}
  void write_data(uint8_t b){assert(b==0x0b);phase=2;due=t+80;}
  void begin_read(){phase=3;due=t+160;}
  uint8_t read_data(){static const uint8_t data[]={0x20,0x01,0xa5};++phase;due=t+80;return data[bytes_read++];}
  void wait_step(){
    ++t;++waits;
    if(waits%16==0){Scheduler::irq();t+=long_irq?4000:2;}
    // Reproduce the OLD cooperative yield when another same-priority task
    // holds CPU for the actual observed interval. New adapter has no yield;
    // scope also protects against an implicit20ms time-slice handover.
    if(phase==4&&waits%32==0&&!Scheduler::locked)t+=web_delay;
  }
  void reset(){++resets;phase=0;}
};
int main(){
 unsigned cases=0;
 for(uint32_t gap:{3772U,3959U,4132U,4810U,20000U}){
  TimedIo old;old.web_delay=gap;PollReader<TimedIo> baseline(old);uint8_t bytes[3];auto a=baseline.read(bytes);
  assert(a.transfer.cause==DEADLINE&&a.error_isr&RXNE&&old.resets==1);++cases;
  TimedIo fixed;fixed.web_delay=gap;PollReader<TimedIo> reader(fixed);
  auto b=scheduled_read<Scheduler>(reader,bytes);
  assert(b.transfer.cause==NONE&&b.transfer.duration_us<1000&&fixed.resets==0);
  assert(bytes[0]==0x20&&bytes[1]==1&&bytes[2]==0xa5&&!Scheduler::locked);++cases;
 }
 for(uint32_t fault:{NACKF,BERR,ARLO,OVR}){
  TimedIo io;io.forced_error=fault;PollReader<TimedIo> r(io);uint8_t b[3];auto x=scheduled_read<Scheduler>(r,b);
  assert(x.transfer.cause!=NONE&&x.error_isr&fault&&io.resets==1&&!Scheduler::locked&&b[0]==0);++cases;
 }
 {
  TimedIo io;io.stall=true;PollReader<TimedIo> r(io);uint8_t b[3];auto x=scheduled_read<Scheduler>(r,b);
  assert(x.transfer.cause==DEADLINE&&x.transfer.duration_us>=3000&&x.transfer.duration_us<3020);
  assert(io.resets==1&&!Scheduler::locked);++cases;
 }
 {
  TimedIo io;io.long_irq=true;PollReader<TimedIo> r(io);uint8_t b[3];auto x=scheduled_read<Scheduler>(r,b);
  assert(x.transfer.cause==DEADLINE&&x.transfer.duration_us>4000&&!Scheduler::locked);++cases;
 }
 assert(Scheduler::locks==Scheduler::unlocks&&Scheduler::locks==11&&Scheduler::irqs>0);
 std::printf("PASS: %u cases, observed scheduling delays, real bus failures, ISR activity, guaranteed scope release\n",cases);
}
