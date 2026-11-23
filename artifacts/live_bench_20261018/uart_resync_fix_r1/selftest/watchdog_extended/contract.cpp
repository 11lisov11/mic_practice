#include <cstdio>
#include <cstdlib>
#include <array>
#include <cstring>
#include "uart_reject_wire.h"
unsigned checks;
void check(bool v,const char *msg) {++checks;if(!v){fprintf(stderr,"FAIL %s\n",msg);exit(1);}}
using Frame=std::array<uint8_t,UV3_FRAME>;
Frame packet(unsigned seq,unsigned hz=15000,uint8_t flags=1) {
  Frame f{};f[0]=0xaa;f[1]=0x55;f[2]=3;f[3]=flags;f[4]=flags==8?0:3;f[5]=(uint8_t)seq;
  if(flags!=8){for(unsigned j=0;j<4;++j)f[6+j]=hz>>(8*j);f[10]=0xf4;f[11]=1;f[12]=0xc2;f[13]=0x5a;}
  uv3_seal(f.data());return f;
}
uv3_result feed(uv3_rx &rx,const Frame &f,uint32_t t,int noise=-1) {
  uv3_result result=UV3_WAIT;
  for(unsigned i=0;i<f.size();++i){
    auto v=uv3_byte(&rx,f[i],(int)i==noise?UV3_NE:0,t+i*87/1000);
    if(v!=UV3_WAIT)result=v;
    if(v==UV3_READY)uv3_commit(&rx,t+i*87/1000,true,rx.fault_latched,false);
  }
  return result;
}
void warm(uv3_rx &r,unsigned seq=100) {
  uv3_init(&r,true);for(unsigned i=0;i<4;++i)check(feed(r,packet(seq+i),10+50*i)==UV3_READY,"clean warm RUN");
}
int main(){
  uv3_rx r;warm(r);
  uint32_t committed=r.last_valid_ms;
  check(uv3_tick(&r,committed+300)==UV3_WAIT,"watchdog retains 300-ms boundary");
  check(uv3_tick(&r,committed+301)==UV3_LINK_TIMEOUT,"watchdog trips at 301 ms");
  for(unsigned error:{UV3_PE,UV3_FE,UV3_ORE}){warm(r);check(uv3_byte(&r,0,error,210)==UV3_HARD_UART,"hard errors trip immediately");}
  warm(r);
  const uint32_t before_damage=r.last_valid_ms;
  for(unsigned i=0;i<3;++i){auto f=packet(104+i);f[7]^=1;auto v=feed(r,f,210+50*i);
    check(v==(i<2?UV3_DROPPED:UV3_BAD_CRC),"third distinct damaged frame remains fatal");
    check(r.last_valid_ms==before_damage,"damaged packets never refresh committed deadline");}
  check(r.fault_latched && r.fatal_reject_valid && r.fatal_reject.meta[2]==43,"fatal raw full frame saved");
  check(r.fatal_reject.meta[12]!=r.fatal_reject.meta[13],"observed CRC mismatch distinguished");
  auto saved=r.fatal_reject;feed(r,packet(107),360);
  check(!memcmp(&saved,&r.fatal_reject,sizeof(saved)),"fatal data immutable after clean traffic");
  uint8_t raw[UR_BYTES];ur_serialize(raw,&r,BW_NUCLEO_BUILD);
  check(ur_record_valid(raw,BW_NUCLEO_BUILD),"serialized fatal record validates");
  FILE *file=fopen("fatal.bin","wb");check(file && fwrite(raw,1,UR_BYTES,file)==UR_BYTES,"save raw diagnostic");fclose(file);
  urw_receiver receiver{};
  for(unsigned page=0;page<URW_PAGES;++page){uint8_t p[UV3_FRAME]{};
    p[0]=0x55;p[1]=0xaa;p[2]=URW_VERSION;p[3]=page;p[4]=URW_PAGES;
    ur_put32(p+6,BW_NUCLEO_BUILD);ur_put32(p+10,uv3_crc32c(raw,UR_BYTES));
    unsigned offset=24*page,n=UR_BYTES-offset;if(n>24)n=24;memcpy(p+14,raw+offset,n);uv3_seal(p);
    check(urw_receive(&receiver,p,BW_NUCLEO_BUILD,true,100+page*200),"real Uno accepts valid D3 page");
  }
  check(receiver.complete && !memcmp(raw,receiver.data,UR_BYTES),"end-to-end D3 bytes identical");
  for(unsigned pos=0;pos<UV3_FRAME;++pos){
    uint8_t p[UV3_FRAME]{};p[0]=0x55;p[1]=0xaa;p[2]=URW_VERSION;p[4]=URW_PAGES;
    ur_put32(p+6,BW_NUCLEO_BUILD);ur_put32(p+10,uv3_crc32c(raw,UR_BYTES));memcpy(p+14,raw,24);uv3_seal(p);
    urw_reset(&receiver);p[pos]^=1;
    check(!urw_receive(&receiver,p,BW_NUCLEO_BUILD,true,0),"D3 corrupted frame rejected");
    p[pos]^=1;urw_reset(&receiver);
    check(!urw_receive(&receiver,p,BW_NUCLEO_BUILD,false,0),"D3 cannot accept stale or running peer");
    check(!urw_receive(&receiver,p,BW_NUCLEO_BUILD-2,true,0),"D3 cannot accept old identity");
  }
  uint8_t bad[UR_BYTES];const unsigned offsets[]={0,4,8,12,16,20,28,32+8,176+4,176+8,176+12,176+16,176+24,176+28,176+44,176+48,176+52,319};
  for(unsigned offset:offsets){memcpy(bad,raw,UR_BYTES);bad[offset]^=0x80;check(!ur_record_valid(bad,BW_NUCLEO_BUILD),"malformed diagnostic rejected");}
  warm(r);auto f=packet(104);f[42]=0xaa;feed(r,f,210);committed=r.last_valid_ms;
  check(r.index==1 && r.speculative_prefix==1,"retained AA is explicitly speculative");
  check(uv3_tick(&r,230)==UV3_WAIT && r.dropped_frames==1 && r.noise_used==1,"old suffix timeout is not a second damaged frame");
  check(r.last_valid_ms==committed && r.recoverable_losses==1,"discard neither refreshes watchdog nor grants extra sequence gap");
  check(feed(r,packet(105),260)==UV3_READY && !r.fault_latched,"clean next command recovers");
  warm(r);f=packet(104);f[42]=0xaa;feed(r,f,210);
  check(feed(r,packet(105),214)==UV3_READY && r.dropped_frames==1,"back-to-back AA overlap does not double-charge");
  warm(r);f=packet(104);f[7]^=1;feed(r,f,210);
  check(feed(r,packet(103),260)==UV3_BAD_SEQUENCE,"replay remains forbidden after a drop");
  warm(r);f=packet(104);f[7]^=1;feed(r,f,210);
  check(feed(r,packet(106),260)==UV3_BAD_SEQUENCE,"one true loss cannot authorize a two-command gap");
  warm(r);f=packet(104);for(unsigned i=0;i<10;++i)uv3_byte(&r,f[i],0,210);
  check(uv3_tick(&r,226)==UV3_DROPPED && r.dropped_frames==1,"new partial frame still costs a real discard");
  warm(r);for(unsigned i=0;i<30;++i)check(feed(r,packet(104+i),210+50*i,10)==UV3_READY,"intact NE advisory remains accepted");
  check(r.noise_used==0 && r.accepted_noise_frames==30,"intact NE never spends damaged-frame budget");
  warm(r);check(feed(r,packet(104,0,8),210,6)==UV3_DROPPED,"noisy CLEAR cannot clear a fault");
  warm(r,252);f=packet(0);f[7]^=1;feed(r,f,210);
  check(feed(r,packet(1),260)==UV3_READY,"sequence wrap retained");
  printf("{\"pass\":true,\"checks\":%u,\"hardware_commands\":0}\n",checks);
}
