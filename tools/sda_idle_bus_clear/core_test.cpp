#include "bus_clear.h"
#include <cassert>
#include <cstdio>
#include <vector>
struct Bus {
 bool scl_low=false,sda_low=false,ext_scl=false,ext_sda=true,entered=false;
 unsigned release_on=1,edges=0,enters=0,leaves=0,sda_drives=0;
 std::vector<unsigned> scl_edges;
 uint32_t now=0;
};
static uint8_t lines(void*x){auto&b=*(Bus*)x;return ((!b.scl_low&&!b.ext_scl)?1:0)|((!b.sda_low&&!b.ext_sda)?2:0);}
static void enter(void*x){auto&b=*(Bus*)x;b.entered=true;++b.enters;b.scl_low=b.sda_low=false;}
static void scl(void*x,bool low){auto&b=*(Bus*)x;assert(b.entered);if(b.scl_low&&!low){++b.edges;if(b.edges>=b.release_on)b.ext_sda=false;}b.scl_low=low;b.scl_edges.push_back(b.now);}
static void sda(void*x,bool low){auto&b=*(Bus*)x;assert(b.entered);if(low){assert(b.scl_low);++b.sda_drives;}b.sda_low=low;}
static void leave(void*x){auto&b=*(Bus*)x;++b.leaves;b.entered=false;b.scl_low=b.sda_low=false;}
static bc_io io(Bus&b){return {&b,lines,enter,scl,sda,leave};}
static unsigned checks;
static void trial(unsigned release_on,unsigned gap,bool wrap){
 Bus b;b.release_on=release_on;bc_state s{};auto i=io(b);unsigned now=wrap?0xfffff000:0;
 bc_begin(&s,&i,now);
 for(unsigned n=0;s.active&&n<50000;n++){
  now+=gap*170;b.now=now;bc_poll(&s,&i,now,170000000,true);
 }
 assert(!s.active&&s.attempted&&b.enters==1&&b.leaves==1&&!b.scl_low&&!b.sda_low);
 if(release_on<=9){assert(s.result==BC_CLEARED&&s.pulses==9&&s.after==3&&b.sda_drives==1);}
 else {assert(s.result==BC_SDA_LOW&&s.pulses==9&&b.sda_drives==0);}
 unsigned old=b.enters;bc_begin(&s,&i,now);assert(b.enters==old);
 for(unsigned n=1;n<b.scl_edges.size();n++)assert((uint32_t)(b.scl_edges[n]-b.scl_edges[n-1])>=5*170);
 ++checks;
}
int main(){
 for(unsigned r=1;r<=10;r++)for(unsigned gap:{1U,5U,24U,538U})for(bool wrap:{false,true})trial(r,gap,wrap);
 {Bus b;b.ext_scl=true;auto i=io(b);bc_state s{};bc_begin(&s,&i,0);bc_poll(&s,&i,500*170,170000000,true);assert(s.result==BC_SCL_LOW&&!b.edges);++checks;}
 {Bus b;auto i=io(b);bc_state s{};bc_begin(&s,&i,0);bc_poll(&s,&i,21000*170,170000000,true);assert(s.result==BC_TIMEOUT&&b.leaves==1);++checks;}
 {Bus b;b.ext_sda=false;auto i=io(b);bc_state s{};bc_begin(&s,&i,0);bc_poll(&s,&i,5*170,170000000,true);assert(s.result==BC_RELEASED&&!b.edges);++checks;}
 // Cancellation at each state must leave the bus released, no extra clocks.
 for(unsigned target=BC_CHECK;target<=BC_VERIFY;target++){
  Bus b;auto i=io(b);bc_state s{};bc_begin(&s,&i,0);unsigned now=0;
  for(unsigned n=0;s.active&&s.state!=target&&n<100;n++){now+=5*170;b.now=now;bc_poll(&s,&i,now,170000000,true);}
  assert(s.state==target);unsigned edges=b.edges;bc_poll(&s,&i,now+1,170000000,false);
  assert(s.result==BC_CANCELLED&&!s.active&&b.edges==edges&&b.leaves==1);++checks;
 }
 printf("{\"passed\":true,\"cases\":%u}\n",checks);
}
