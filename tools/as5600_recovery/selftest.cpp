#include "as5600_poll_reader.h"
#include "as5600_filter_timing.h"
#include "as5600_poll_section.h"
#include "baseline_poll_reader.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>
using namespace encdiag;
struct Scheduler {static unsigned locks;static void lock(){++locks;}static void unlock(){assert(locks);--locks;}};
unsigned Scheduler::locks=0;
struct Io {
  uint32_t t=0,fault=0;int phase=0,bad_phase=-1,berr_phase=-1,stall_phase=-1;
  uint32_t fault_at=0;bool delayed_stop=true,held=false,berr_cleared=false;
  unsigned resets=0,starts=0,writes=0,reads=0,quiesced=0;
  uint32_t now_us(){return t;}
  uint32_t status(){
    ++t;
    if(held&&phase==0)return BUSY;
    if(phase==bad_phase){
      if(!fault_at)fault_at=t;
      if(delayed_stop&&uint32_t(t-fault_at)>12)return fault==NACKF?STOPF:fault;
      return fault|BUSY;
    }
    if(phase==stall_phase)return 0;
    uint32_t s=phase==1?TXIS:phase==2?TC:phase>=3&&phase<=5?RXNE:phase==6?STOPF:0;
    if(phase==berr_phase&&!berr_cleared)s|=BERR;
    return s;
  }
  uint32_t control(){return uint32_t(phase)<<16;}
  uint32_t line_bits(){return held?2:3;}
  bool lines_high(){return !held;}
  void wait_step(){++t;}
  void clear_berr(){berr_cleared=true;}
  void clear(){if(phase==6||phase==bad_phase)phase=0;}
  void quiesce(){++quiesced;}
  void begin_write(){++starts;phase=1;}
  void write_data(uint8_t b){assert(b==0x0b);++writes;phase=2;}
  void begin_read(){phase=3;reads=0;}
  uint8_t read_data(){static const uint8_t a[]={0x20,1,0xa5};++phase;return a[reads++];}
  void reset(){++resets;phase=0;t+=2;}
};
int main(){
 unsigned cases=0;
 for(uint32_t time:{0U,UINT32_MAX-100U}){
  Io io;io.t=time;PollReader<Io> r(io);uint8_t b[3];auto x=scheduled_read<Scheduler>(r,b);
  assert(x.transfer.cause==NONE&&b[0]==0x20&&b[1]==1&&b[2]==0xa5&&io.starts==1&&!io.resets&&!Scheduler::locks);++cases;
 }
 for(int phase:{1,2,3,4,5,6}){
  Io io;io.berr_phase=phase;PollReader<Io> r(io);uint8_t b[3];auto x=r.read(b);
  assert(x.transfer.cause==NONE&&x.berr_events==1&&x.first_berr_isr&BERR&&io.resets==0&&io.reads==3);++cases;
 }
 for(int phase:{1,2,3,4,5,6}){
  Io io;io.bad_phase=phase;io.fault=NACKF;PollReader<Io> r(io);uint8_t b[3];auto x=scheduled_read<Scheduler>(r,b);
  assert(x.transfer.cause==NACK&&x.graceful_cleanup&&io.resets==0&&io.starts==1);
  assert(x.error_isr&NACKF&&x.error_cr2==uint32_t(phase)<<16&&x.error_lines==3);
  assert(b[0]==0&&b[1]==0&&b[2]==0&&!Scheduler::locks);++cases;
  io.bad_phase=-1;auto next=r.read(b);
  assert(next.transfer.cause==NONE&&io.starts==2&&io.resets==0&&b[0]==0x20&&b[2]==0xa5);++cases;
 }
 for(uint32_t flag:{ARLO,OVR}){
  Io io;io.bad_phase=4;io.fault=flag;PollReader<Io> r(io);uint8_t b[3];auto x=r.read(b);
  assert(x.transfer.cause==(flag==ARLO?ARBITRATION:OVERRUN)&&b[0]==0&&io.starts==1);
  assert(flag==ARLO?x.graceful_cleanup:bool(io.resets));++cases;
 }
 for(int phase:{1,2,3,4,5,6})for(uint32_t time:{0U,UINT32_MAX-1500U}){
  Io io;io.t=time;io.stall_phase=phase;PollReader<Io> r(io);uint8_t b[3];auto x=scheduled_read<Scheduler>(r,b);
  assert(x.transfer.cause==DEADLINE&&x.transfer.duration_us>=3000&&x.transfer.duration_us<3020);
  assert(io.resets==1&&io.starts==1&&b[0]==0&&!Scheduler::locks);++cases;
 }
 {
  Io io;io.bad_phase=3;io.fault=NACKF;io.delayed_stop=false;PollReader<Io> r(io);uint8_t b[3];auto x=r.read(b);
  assert(x.transfer.cause==NACK&&!x.graceful_cleanup&&x.controller_reset&&x.transfer.duration_us<160);++cases;
 }
 {
  Io io;io.held=true;PollReader<Io> r(io);uint8_t b[3];auto x=r.read(b);
  assert(x.transfer.cause==BUS_BUSY&&io.starts==0&&io.resets==1&&x.post_isr&BUSY&&x.error_lines==2);++cases;
 }
 // BERR+real error must never be accepted as the spurious-BERR workaround.
 for(uint32_t flag:{ARLO,OVR,NACKF}){
  Io io;io.fault=BERR|flag;io.bad_phase=3;PollReader<Io> r(io);uint8_t b[3];auto x=r.read(b);
  assert(x.transfer.cause!=NONE&&b[0]==0&&x.error_isr&BERR);++cases;
 }
 for(uint32_t hz=20000000;hz<=160000000;hz+=1000000){
  auto v=encfix::standard_filtered(hz);assert(v.valid&&v.dnf>0&&v.dnf<=15);
  double ck=1e9/hz,tick=(((v.word>>28)&15)+1)*ck;
  double lo=((v.word&255)+1)*tick,hi=(((v.word>>8)&255)+1)*tick;
  double setup=(((v.word>>20)&15)+1)*tick,hold=((v.word>>16)&15)*tick;
  assert(lo>=4999.99&&hi>=4999.99&&setup>=1499.99);
  assert(hold+1e-6>=300-50-(v.dnf+3)*ck);
  assert(hold<=3450-1000-260-(v.dnf+4)*ck);
  ++cases;
 }
 for(uint32_t hz:{0U,4000000U,16000000U,160000001U}){assert(!encfix::standard_filtered(hz).valid);++cases;}
 {
  Io io;io.berr_phase=4;baseline::PollReader<Io> old(io);uint8_t b[3];auto x=old.read(b);
  assert(x.transfer.cause==BUS_ERROR&&io.resets==1&&b[0]==0);++cases;
 }
 std::printf("PASS: %u recovery, BERR-workaround, full-frame, deadline, scheduler and filter-timing cases\n",cases);
}
