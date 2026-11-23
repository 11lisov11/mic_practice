#include "encoder_core.h"
#include "uno_encoder_adapter.h"
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <cstring>
#include <utility>
static unsigned checks;
static void check(bool v){++checks;if(!v){std::fprintf(stderr,"failed check%u\n",checks);std::exit(1);}}
struct Mock {
  uint32_t flags=0;unsigned begun=0,writes=0,read_begin=0,resets=0,clears=0,index=0;
  uint8_t data[3]={0x20,8,0};
};
static uint32_t stat(void*p){return static_cast<Mock*>(p)->flags;}
static void begin(void*p){++static_cast<Mock*>(p)->begun;}
static void write(void*p,uint8_t v){check(v==0x0b);++static_cast<Mock*>(p)->writes;}
static void rbegin(void*p){++static_cast<Mock*>(p)->read_begin;}
static uint8_t read(void*p){auto*m=static_cast<Mock*>(p);check(m->index<3);return m->data[m->index++];}
static void clear(void*p){++static_cast<Mock*>(p)->clears;}
static void reset(void*p){++static_cast<Mock*>(p)->resets;}
static ec_io make_io(Mock*m){return {m,stat,begin,write,rbegin,read,clear,reset,nullptr};}
static void good(ec_state&e,Mock&m,uint32_t ms,uint16_t raw=2048,uint8_t status=0x20,uint32_t cyc=0){
  auto io=make_io(&m);m.index=0;m.data[0]=status;m.data[1]=raw>>8;m.data[2]=raw&255;
  m.flags=0;ec_poll(&e,&io,ms,cyc,170000000);check(e.state==1);
  m.flags=EC_TXIS;ec_poll(&e,&io,ms,cyc+170,170000000);check(e.state==2);
  m.flags=EC_TC;ec_poll(&e,&io,ms,cyc+340,170000000);check(e.state==3);
  for(unsigned i=0;i<3;++i){m.flags=EC_RXNE;ec_poll(&e,&io,ms,cyc+510+i*170,170000000);}
  check(e.state==4);m.flags=EC_STOPF;ec_poll(&e,&io,ms,cyc+1020,170000000);
  check(e.state==0&&e.bus_ok&&e.cause==0);
}
static void seal(uint8_t*p){uv3_seal(p);}
int main(){
  ec_state e;Mock m;auto io=make_io(&m);ec_init(&e,170000000,true);
  ec_poll(&e,&io,4,0,170000000);check(m.begun==0);
  good(e,m,5);check(e.raw==2048&&e.angle_ok&&e.reads==1&&!e.speed_ok&&m.resets==0);
  for(unsigned i=1;i<45;++i)good(e,m,5+5*i,(uint16_t)((2048+102*i)&4095));
  check(e.speed_ok&&e.rpm>250&&e.rpm<310);
  uint32_t errors=e.errors;m.flags=0;ec_poll(&e,&io,250,0,170000000);
  m.flags=EC_NACKF;ec_poll(&e,&io,250,170,170000000);
  check(e.errors==errors+1&&e.cause==EC_NACK&&!e.angle_ok&&!e.speed_ok&&m.resets==1);
  m.flags=0;ec_poll(&e,&io,269,0,170000000);check(e.state==0);
  good(e,m,270);check(!e.speed_ok);
  good(e,m,275,2048,0x30);check(e.bus_ok&&!e.angle_ok&&!e.speed_ok);
  good(e,m,280,2048,0x28);check(!e.angle_ok);
  for(auto pair:{std::pair<uint32_t,uint8_t>{EC_ARLOF,EC_ARLO},{EC_BERR,EC_BUS},{EC_OVRF,EC_OVR}}){
    ec_init(&e,170000000,true);m.flags=0;ec_poll(&e,&io,5,0,170000000);
    m.flags=pair.first;ec_poll(&e,&io,5,100,170000000);check(e.cause==pair.second&&!e.bus_ok&&e.errors==1);
  }
  ec_init(&e,170000000,true);m.flags=EC_BUSYF;ec_poll(&e,&io,5,0,170000000);
  check(e.cause==EC_BUSY&&e.state==0);
  ec_init(&e,170000000,true);m.flags=0;ec_poll(&e,&io,5,0xffff0000U,170000000);
  ec_poll(&e,&io,6,0xffff0000U+509999U,170000000);check(e.state==1);
  ec_poll(&e,&io,8,0xffff0000U+510000U,170000000);check(e.cause==EC_DEADLINE&&e.timeouts==1);
  ec_init(&e,170000000,true);m.flags=0;ec_poll(&e,&io,5,0,170000000);
  ec_poll(&e,&io,8,0,170000000);check(e.cause==EC_DEADLINE); // DWT stalled: HAL deadline still works.
  ec_init(&e,170000000,true);m.flags=0;ec_poll(&e,&io,5,0,170000000);
  m.flags=EC_STOPF;ec_poll(&e,&io,5,100,170000000);check(e.cause==EC_SHORT&&e.reads==0);
  ec_init(&e,170000000,false);m.flags=EC_TXIS;unsigned begun=m.begun;
  for(unsigned i=0;i<100;++i)ec_poll(&e,&io,100+i,0,170000000);
  check(m.begun==begun&&e.cause==EC_SETUP);
  uint8_t p[UV3_FRAME]={0};p[0]=0x55;p[1]=0xaa;p[2]=EW_VERSION;p[3]=15;p[4]=1;
  ew_p32(p+6,EW_PEER);ew_p16(p+10,3);p[12]=0x20;ew_p16(p+14,2048);
  ew_p16(p+16,(uint16_t)(int16_t)-300);ew_p32(p+18,55);p[36]=3;p[37]=1;p[38]=EW_FORMAT;seal(p);
  check(ew_receive(&g_remote_encoder,p,EW_PEER,true,100));
  auto s=remote_encoder_snapshot(101,true);check(s.angle_ok&&s.speed_ok&&s.rpm==-300&&s.raw==2048);
  check(!remote_encoder_snapshot(197,true).angle_ok);
  check(!remote_encoder_snapshot(101,false).bus_ok);
  check(!ew_receive(&g_remote_encoder,p,EW_PEER,true,190));check(g_remote_encoder.received_ms==100);
  for(unsigned i=0;i<UV3_FRAME;++i){uint8_t bad[UV3_FRAME];std::memcpy(bad,p,sizeof p);bad[i]^=1;
    check(!ew_receive(&g_remote_encoder,bad,EW_PEER,true,110));}
  for(unsigned kind=0;kind<9;++kind){uint8_t bad[UV3_FRAME];std::memcpy(bad,p,sizeof p);
    switch(kind){case 0:ew_p32(bad+6,123);break;case 1:bad[3]=4;break;case 2:bad[12]=0x30;break;
      case 3:ew_p16(bad+10,100);break;case 4:bad[37]=0;break;case 5:bad[36]=4;break;
      case 6:bad[5]=2;break;case 7:ew_p16(bad+14,4096);break;case 8:bad[38]=2;break;}
    seal(bad);check(!ew_receive(&g_remote_encoder,bad,EW_PEER,true,110));}
  check(!ew_receive(&g_remote_encoder,p,123,true,110));check(!ew_receive(&g_remote_encoder,p,EW_PEER,false,110));
  p[3]=8;p[4]=2;p[5]=2;p[12]=0;ew_p16(p+14,0);ew_p32(p+22,1);seal(p);
  check(ew_receive(&g_remote_encoder,p,EW_PEER,true,200));s=remote_encoder_snapshot(200,true);
  check(!s.bus_ok&&!s.angle_ok&&!s.speed_ok&&s.errors==1&&s.diag_cause==2);
  std::printf("{\"passed\":true,\"checks\":%u}\n",checks);
}
