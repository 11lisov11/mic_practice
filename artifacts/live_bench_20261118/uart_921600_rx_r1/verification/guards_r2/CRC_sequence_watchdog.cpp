#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "uart_v3_transport.h"
#include "captured.inc"

static unsigned checks;
static void check(bool ok,const char *why) {
  ++checks;if(!ok){fprintf(stderr,"FAIL %s\n",why);exit(1);}
}
using Frame=std::array<uint8_t,UV3_FRAME>;
static Frame frame(unsigned seq,unsigned hz=15000,uint8_t flags=1) {
  Frame f{};f[0]=0xaa;f[1]=0x55;f[2]=3;f[3]=flags;f[4]=flags==1?3:0;f[5]=(uint8_t)seq;
  if(flags==1){for(unsigned j=0;j<4;++j)f[6+j]=hz>>(8*j);f[10]=0xf4;f[11]=1;f[12]=0xc2;f[13]=0x5a;}
  uv3_seal(f.data());return f;
}
static uv3_result feed(uv3_rx &r,const uint8_t *f,const uint8_t *marks,uint32_t t,bool commit=true) {
  uv3_result result=UV3_WAIT;
  for(unsigned i=0;i<UV3_FRAME;++i){
    auto v=uv3_byte(&r,f[i],marks?marks[i]:0,t);
    if(v!=UV3_WAIT)result=v;
    if(v==UV3_READY && commit)uv3_commit(&r,t,true,r.fault_latched,false);
  }
  return result;
}
static uv3_result feed(uv3_rx &r,Frame f,uint32_t t){return feed(r,f.data(),nullptr,t);}
static void warm(uv3_rx &r,unsigned start=209,uint32_t last=65867) {
  uv3_init(&r,true);
  for(unsigned i=0;i<4;++i)check(feed(r,frame(start+i),last-150+50*i)==UV3_READY,"clean qualification");
}
static void used_budget(uv3_rx &r,uint32_t t) {
  r.noise_used=2;r.noise_times[0]=t-200;r.noise_times[1]=t-100;
}
int main(){
  uv3_rx r;warm(r);used_budget(r,65918);
  check(uv3_crc_ok(captured_fatal),"independent captured complete fatal frame passes real C CRC");
  check(!uv3_crc_ok(captured_recovered),"captured recovered frame is genuinely corrupt");
  auto result=feed(r,captured_fatal,captured_fatal_marks,65918);
#ifdef SOURCE_OLD
  check(result==UV3_NOISE_REJECTED && r.fault_latched,"old receiver reproduces captured fatal NE rejection");
  printf("{\"pass\":true,\"old_fatal_reproduced\":true,\"checks\":%u}\n",checks);return 0;
#else
  check(result==UV3_DROPPED && !r.fault_latched && r.confirm_pending,"captured noisy frame is withheld without executing or latching");
  check(r.previous[5]==212 && r.previous[6]==(15000&255) && r.last_valid_ms==65867,
        "withheld 20-Hz command cannot change committed 15-Hz command or watchdog");
  check(r.noise_used==2 && r.recoverable_losses==0,"withheld verified frame cannot reset or spend CRC-loss budget");
  check(feed(r,frame(214,20000),65968)==UV3_READY && !r.confirm_pending && r.clean_confirmations==1,
        "only a subsequent fresh clean command confirms control");
  check(r.noise_used==2 && r.previous[5]==214,"clean confirmation retains both prior damaged-packet events");
  unsigned pairs=0;
  for(unsigned a=0;a<UV3_FRAME;++a)for(unsigned b=a+1;b<UV3_FRAME;++b){
    warm(r);used_budget(r,65918);auto f=frame(213,20000);uint8_t m[UV3_FRAME]{};m[a]=m[b]=UV3_NE;
    check(feed(r,f.data(),m,65918)==UV3_DROPPED && r.confirm_pending && r.previous[5]==212,
          "every two-byte noise position is withheld");
    check(feed(r,frame(214,20000),65968)==UV3_READY && !r.fault_latched,"every two-byte position recovers only on clean fresh command");++pairs;
  }
  // Continuous NE, including a single NE on the second packet, never confirms.
  for(unsigned n=1;n<=UV3_FRAME;++n){warm(r);uint8_t m[UV3_FRAME]{};m[6]=m[7]=UV3_NE;
    auto f=frame(213,20000);feed(r,f.data(),m,65918);memset(m,0,sizeof(m));
    for(unsigned i=0;i<n;++i)m[i]=UV3_NE;
    f=frame(214,20000);
    check(feed(r,f.data(),m,65968)==UV3_NOISE_REJECTED && r.fault_latched,"another noisy frame cannot confirm");}
  uint8_t two[UV3_FRAME]{};two[6]=two[7]=UV3_NE;
  warm(r);feed(r,captured_fatal,two,65918);auto deadline=r.confirm_started_ms;
  check(uv3_tick(&r,deadline+100)==UV3_WAIT,"confirmation boundary inclusive 100 ms");
  check(uv3_tick(&r,deadline+101)==UV3_NOISE_REJECTED && r.fault_latched,"missing clean confirmation stops at 101 ms");
  warm(r);feed(r,captured_fatal,two,65918);
  check(feed(r,frame(213,20000),65968)==UV3_BAD_SEQUENCE,"replayed withheld sequence cannot confirm");
  warm(r);feed(r,captured_fatal,two,65918);
  check(feed(r,frame(215,20000),65968)==UV3_BAD_SEQUENCE,"unobserved gap cannot confirm");
  warm(r);feed(r,captured_fatal,two,65918);
  auto stop=frame(214,0,0);
  check(feed(r,stop,65919)==UV3_READY && !r.confirm_pending,"clean STOP reaches owner immediately without waiting");
  // A new clean command may supersede the withheld one; it is checked by the owner.
  warm(r);feed(r,captured_fatal,two,65918);
  check(feed(r,frame(214,10000),65968)==UV3_READY && r.previous[6]==(10000&255),"latest clean target supersedes withheld target");
  warm(r);auto old_valid=r.last_valid_ms;feed(r,captured_fatal,two,65918);
  auto corrupt=frame(214,20000);corrupt[7]^=1;
  check(feed(r,corrupt,65940)==UV3_DROPPED && r.last_valid_ms==old_valid,"real corruption while pending stays rejected");
  check(feed(r,frame(215,20000),65968)==UV3_READY,"exactly one observed corrupt packet permits exactly one sequence gap");
  warm(r);used_budget(r,65918);feed(r,captured_fatal,two,65918);
  check(feed(r,corrupt,65940)==UV3_BAD_CRC && r.fault_latched,"third real CRC failure is fatal even while awaiting confirmation");
  for(unsigned bit=0;bit<UV3_FRAME*8;++bit){
    warm(r);auto bad=frame(213,20000);bad[bit/8]^=1U<<(bit%8);
    check(feed(r,bad.data(),two,65918)!=UV3_READY && !r.confirm_pending,"corrupted noisy frame never enters verified confirmation path");}
  for(unsigned err:{UV3_PE,UV3_FE,UV3_ORE}){warm(r);feed(r,captured_fatal,two,65918);
    check(uv3_byte(&r,0,err,65920)==UV3_HARD_UART && r.fault_latched,"PE FE ORE immediately stop during confirmation");}
  warm(r);r.run_anchor=false;used_budget(r,65918);
  check(feed(r,captured_fatal,two,65918)==UV3_NOISE_REJECTED,"unstarted motor cannot use running confirmation path");
  warm(r);r.clean_run_frames=2;used_budget(r,65918);
  check(feed(r,captured_fatal,two,65918)==UV3_NOISE_REJECTED,"unqualified link cannot defer");
  warm(r);r.bounded_noise=false;
  check(feed(r,captured_fatal,two,65918)==UV3_NOISE_REJECTED,"strict receiver remains strict");
  warm(r);auto clear=frame(213,0,8);used_budget(r,65918);
  check(feed(r,clear.data(),two,65918)==UV3_NOISE_REJECTED,"noisy CLEAR cannot defer or release faults");
  warm(r);auto last=r.last_valid_ms;
  check(uv3_tick(&r,last+300)==UV3_WAIT && uv3_tick(&r,last+301)==UV3_LINK_TIMEOUT,"original 300-ms watchdog retained");
  // Wrap of sequence and tick arithmetic is still bounded.
  warm(r,252,0xfffffff0U);auto f=frame(0,20000);
  check(feed(r,f.data(),two,0x20U)==UV3_DROPPED,"pending sequence and clock wrap");
  check(feed(r,frame(1,20000),0x52U)==UV3_READY,"clean confirmation across wraps");
  printf("{\"pass\":true,\"old_fatal_reproduced\":false,\"checks\":%u,\"two_NE_position_pairs\":%u,\"hardware_commands\":0}\n",checks,pairs);
#endif
}
