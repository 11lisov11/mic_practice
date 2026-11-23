#include "encoder_core.h"
#include "encoder_wire.h"
#include "record_fixture.h"
#include <cassert>
#include <cstdio>
#include <cstring>
static unsigned checks;
static void check(bool x){++checks;if(!x){std::fprintf(stderr,"check %u failed\n",checks);std::abort();}}
struct Bus {
 uint32_t isr=0,now=0;uint8_t pins=3,bytes[3]={0x20,8,0};unsigned pos=0,starts=0,reads=0,parks=0,enables=0,resets=0,faults=0,berrs=0;
 uint32_t fault_isr=0,errors_at_fault=0;bool pe=false,pe_at_fault=false;ec_state*state=nullptr;
};
static uint32_t status(void*p){return ((Bus*)p)->isr;}
static void begin(void*p){auto&b=*(Bus*)p;check(b.pe);++b.starts;b.pos=0;}
static void write(void*,uint8_t v){check(v==0x0b);}
static void read_begin(void*){}
static uint8_t read(void*p){auto&b=*(Bus*)p;check(b.pos<3);++b.reads;return b.bytes[b.pos++];}
static void clear(void*p){((Bus*)p)->isr&=~(EC_NACKF|EC_STOPF|EC_BERR|EC_ARLOF|EC_OVRF);}
static void reset(void*p){auto&b=*(Bus*)p;++b.resets;b.pe=false;b.isr=1;}
static void fault(void*p,uint8_t,uint32_t isr,uint32_t,uint32_t){auto&b=*(Bus*)p;++b.faults;b.fault_isr=isr;b.pe_at_fault=b.pe;b.errors_at_fault=b.state->errors;}
#ifdef PATCHED
static uint8_t lines(void*p){return ((Bus*)p)->pins;}
static void enable(void*p){auto&b=*(Bus*)p;b.pe=true;++b.enables;}
static void park(void*p){auto&b=*(Bus*)p;b.pe=false;b.isr=1;++b.parks;}
static void clear_berr(void*p){auto&b=*(Bus*)p;b.isr&=~EC_BERR;++b.berrs;}
#endif
static ec_io io(Bus*b){return {b,status,begin,write,read_begin,read,clear,reset,fault
#ifdef PATCHED
,lines,enable,park,clear_berr
#endif
};}
static void poll(ec_state&e,Bus&b,uint32_t ms,uint32_t cyc){b.state=&e;b.now=cyc;auto i=io(&b);ec_poll(&e,&i,ms,cyc,170000000);}
#ifdef PATCHED
static void start(ec_state&e,Bus&b,uint32_t ms,uint32_t cy=100000){
 b.isr=1;poll(e,b,ms,cy);check(e.state==0&&e.prepare==1&&!b.pe);
 poll(e,b,ms,cy+1700);check(e.prepare==2&&b.pe);
 poll(e,b,ms,cy+3400);check(e.state==0);
 poll(e,b,ms,cy+5100);check(e.state==1&&b.starts>0);
}
static void finish(ec_state&e,Bus&b,uint32_t ms,uint32_t cy=106000,bool berr=false){
 const uint32_t flag=berr?EC_BERR:0;
 b.isr=EC_TXIS|flag;poll(e,b,ms,cy);check(e.state==2);
 b.isr=EC_TC|flag;poll(e,b,ms,cy+1700);check(e.state==3);
 for(unsigned n=0;n<3;++n){b.isr=EC_RXNE|flag;poll(e,b,ms,cy+3400+n*1700);}
 check(e.state==4);b.isr=EC_STOPF|flag;poll(e,b,ms,cy+8500);
 check(e.state==0&&e.prepare==0&&e.bus_ok&&!b.pe&&e.cause==EC_NONE);
}
#endif
int main(){
 ec_state e;Bus b;ec_init(&e,170000000,true);
 // Reconstruct the ACTUAL first captured entry (not an invented waveform).
 e.reads=record[27];e.errors=record[26];e.state=(record[4]>>16)&255;e.n=record[4]>>24;
 e.stage=(record[4]>>8)&255;e.last_start_ms=record[2]-5;b.isr=record[5];b.pe=record[9]&1;b.pins=(record[7]>>8)&3;
 poll(e,b,record[2],record[3]);
#ifndef PATCHED
 check(e.cause==EC_BUSY&&e.errors==1&&b.resets==1&&b.pe_at_fault&&b.fault_isr==0x8001);
 std::printf("{\"passed\":true,\"original_immediate_reset_replayed\":true,\"checks\":%u}\n",checks);return 0;
#else
 check(e.errors==0&&b.resets==0&&e.prepare==1); // No immediate destructive reset.
 for(unsigned us=40;us<=3000;us+=40)poll(e,b,record[2]+us/1000,record[3]+us*170);
 check(e.cause==EC_BUSY&&e.errors==1&&b.resets==1&&b.faults==1&&b.pe_at_fault&&b.fault_isr==0x8001&&b.errors_at_fault==0);
 check(!b.pe&&b.starts==0); // Stale bytes cannot turn into a valid sample.
 auto initial_reads=e.reads;
 start(e,b,record[2]+20,record[3]+20*170000);finish(e,b,record[2]+20,record[3]+20*170000+6000);
 check(e.reads==initial_reads+1&&e.raw==2048&&e.errors==1&&b.resets==1);
 // Normal200Hz acquisition: peripheral is OFF during every idle interval.
 for(unsigned n=1;n<=200;++n){start(e,b,record[2]+20+n*5,1000000+n*850000);finish(e,b,record[2]+20+n*5,1006000+n*850000);check(!b.pe);}
 check(e.reads==initial_reads+201&&e.errors==1&&e.speed_ok);
 // BERR alone does not abort or erase RX/STOP, and all phases keep working.
 ec_init(&e,170000000,true);b=Bus{};start(e,b,5);finish(e,b,5,106000,true);
 check(e.reads==1&&e.errors==0&&b.resets==0&&b.berrs==6&&e.berr_clears==6);
 for(uint32_t flag:{(uint32_t)EC_NACKF,(uint32_t)EC_ARLOF,(uint32_t)EC_OVRF}){
  ec_init(&e,170000000,true);b=Bus{};start(e,b,5);b.isr=flag|EC_BERR;poll(e,b,5,110000);
  check(e.errors==1&&!e.bus_ok&&!e.angle_ok&&!e.speed_ok&&b.resets==1&&b.faults==1&&!b.pe);
  check(b.fault_isr==(flag|EC_BERR)&&b.berrs==0);
 }
 // BERR cannot extend the acquisition deadline indefinitely.
 ec_init(&e,170000000,true);b=Bus{};start(e,b,5);b.isr=EC_BERR;poll(e,b,8,610000);
 check(e.cause==EC_DEADLINE&&e.timeouts==1&&e.reads==0&&!b.pe);
 check(b.fault_isr==EC_BERR&&b.berrs==0);
 // Either physical line LOW: no START, finite error and no fabricated data.
 for(uint8_t pins:{(uint8_t)0,(uint8_t)1,(uint8_t)2}){
  ec_init(&e,170000000,true);b=Bus{};b.pins=pins;
  for(unsigned us=0;us<=3000;us+=30)poll(e,b,5+us/1000,100000+us*170);
  check(e.cause==EC_BUSY&&b.starts==0&&e.reads==0&&e.errors==1&&!e.speed_ok&&!b.pe);
 }
 // A temporary BUSY after PE enable can settle without reset/retry.
 ec_init(&e,170000000,true);b=Bus{};poll(e,b,5,100000);poll(e,b,5,101700);check(e.prepare==2);
 b.isr=EC_BUSYF|1;poll(e,b,5,103400);poll(e,b,5,120000);check(b.starts==0&&e.errors==0);
 b.isr=1;poll(e,b,5,122000);poll(e,b,5,124000);check(e.state==1&&e.errors==0&&b.resets==0);
 finish(e,b,5,126000);
 // STOP before three bytes rejects the whole acquisition.
 ec_init(&e,170000000,true);b=Bus{};start(e,b,5);b.isr=EC_STOPF;poll(e,b,5,110000);
 check(e.cause==EC_SHORT&&e.reads==0&&e.errors==1&&!b.pe);
 // Cycle and millisecond wrap do not prevent a finite preflight timeout.
 ec_init(&e,170000000,true);b=Bus{};b.pins=0;e.last_start_ms=UINT32_MAX-10;
 poll(e,b,UINT32_MAX-2,UINT32_MAX-1000);poll(e,b,0,509000);
 check(e.errors==1&&e.cause==EC_BUSY);
 // Format2 accepts a fresh, CRC-valid parked sample, rejects mixed/old data.
 uint8_t packet[UV3_FRAME]{};packet[0]=0x55;packet[1]=0xaa;packet[2]=EW_VERSION;packet[3]=15;
 packet[5]=0;ew_p32(packet+6,EW_PEER);ew_p16(packet+10,2);packet[12]=0x20;ew_p16(packet+14,2048);
 ew_p32(packet+18,1);packet[36]=3;packet[37]=0;packet[38]=EW_FORMAT;uv3_seal(packet);
 ew_receiver rx{};check(ew_receive(&rx,packet,EW_PEER,true,10));
 for(unsigned n=0;n<UV3_FRAME;++n){auto bad=packet[n];packet[n]^=1;ew_receiver q{};check(!ew_receive(&q,packet,EW_PEER,true,10));packet[n]=bad;}
 ew_receiver q{};check(!ew_receive(&q,packet,2026102604,true,10));
 packet[38]=1;uv3_seal(packet);check(!ew_receive(&q,packet,EW_PEER,true,10));
 std::printf("{\"passed\":true,\"checks\":%u,\"recorded_busy_replayed\":true,\"normal_samples\":200,\"physical_pwm_qualified\":false}\n",checks);
#endif
}
