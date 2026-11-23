#include "as5600_poll_reader.h"
#include "timed_run.h"
#include "mcsdk_supervisory.h"
#include <cassert>
#include <cstdio>
#include <vector>
using namespace encdiag;
struct Io {
  uint32_t t=0, fault=0; int phase=0, fail_phase=-1, stall_phase=-1, delayed_phase=-1;
  unsigned resets=0,starts=0,read_bytes=0,writes=0; bool high=true;
  uint32_t now_us(){return t;}
  uint32_t status(){
    t+=1;
    if(phase==delayed_phase){t+=500001;delayed_phase=-1;}
    if(phase==fail_phase)return fault;
    if(phase==stall_phase)return 0;
    if(phase==1)return TXIS;
    if(phase==2)return TC;
    if(phase>=3&&phase<=5)return RXNE;
    if(phase==6)return STOPF;
    return 0;
  }
  bool lines_high(){return high;}
  void clear(){if(phase==6)phase=0;}
  void begin_write(){++starts;phase=1;}
  void write_data(uint8_t b){assert(b==0x0b);++writes;phase=2;}
  void begin_read(){phase=3;}
  uint8_t read_data(){static const uint8_t data[]={0x20,0x01,0xa5};++phase;return data[read_bytes++];}
  void wait_step(){t+=1;}
  void reset(){++resets;phase=0;}
};
int main(){
  unsigned cases=0;
  for(uint32_t start:{0U,UINT32_MAX-20U}){
    Io io;io.t=start;PollReader<Io> r(io);uint8_t b[3];auto x=r.read(b);
    assert(x.transfer.cause==NONE&&x.transfer.stage==OK&&!x.controller_reset);
    assert(b[0]==0x20&&b[1]==1&&b[2]==0xa5&&io.starts==1&&io.writes==1&&io.resets==0);
    ++cases;
  }
  for(int phase:{1,2,3,4,5,6})for(uint32_t flag:{NACKF,BERR,ARLO,OVR}){
    Io io;io.fail_phase=phase;io.fault=flag|TXIS|RXNE|STOPF;
    PollReader<Io> r(io);uint8_t b[3];auto x=r.read(b);
    assert(x.transfer.cause==(flag==NACKF?NACK:flag==BERR?BUS_ERROR:flag==ARLO?ARBITRATION:OVERRUN));
    assert(x.error_isr==io.fault&&x.controller_reset&&io.resets==1&&io.starts==1);
    assert(b[0]==0&&b[1]==0&&b[2]==0);++cases;
  }
  for(int phase:{1,2,3,4,5,6})for(uint32_t start:{0U,UINT32_MAX-1500U}){
    Io io;io.stall_phase=phase;io.t=start;PollReader<Io> r(io);uint8_t b[3];auto x=r.read(b);
    assert(x.transfer.cause==DEADLINE&&x.transfer.duration_us>=3000&&x.transfer.duration_us<3020);
    assert(io.resets==1&&io.starts==1&&b[0]==0&&b[1]==0&&b[2]==0);++cases;
  }
  {
    Io io;io.high=false;PollReader<Io> r(io);uint8_t b[3];auto x=r.read(b);
    assert(x.transfer.cause==BUS_BUSY&&io.starts==0&&io.resets==1);++cases;
  }
  {
    Io io;io.fail_phase=0;io.fault=BUSY;PollReader<Io> r(io);uint8_t b[3];auto x=r.read(b);
    assert(x.transfer.cause==BUS_BUSY&&io.starts==0&&x.error_isr==BUSY);++cases;
  }
  {
    Io io;io.delayed_phase=3;PollReader<Io> r(io);uint8_t b[3];auto x=r.read(b);
    // Scheduler delay is observable, NOT falsely described as a hard3ms bound.
    assert(x.transfer.cause==DEADLINE&&x.transfer.duration_us>500000&&io.read_bytes==0);++cases;
  }
  for(uint32_t start:{0U,UINT32_MAX-4999U,UINT32_MAX-2000U}){
    TimedRun run;run.start(start,5000);assert(!run.due(start+4999));assert(run.due(start+5000));
    run.finish(start+5000,TimedRun::LIMIT);assert(!run.active&&run.reason==TimedRun::LIMIT&&run.elapsed(start+9000)==5000);
    run.finish(start+7000,TimedRun::STOP);assert(run.reason==TimedRun::LIMIT&&run.elapsed(start+9000)==5000);
    auto id=run.id;run.start(start+10000,0);assert(run.id==id+1&&!run.due(start+20000));
    run.finish(start+11000,TimedRun::STOP);assert(run.reason==TimedRun::STOP&&run.elapsed(0)==1000);++cases;
  }
  std::printf("PASS: %u hardware-reader fault/deadline and timed-run cases\n",cases);
}
