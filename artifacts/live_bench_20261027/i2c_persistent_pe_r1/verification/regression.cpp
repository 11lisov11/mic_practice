#include "encoder_core.h"
#include "encoder_health_wire.h"
#include "fault_wire.h"
#include "record_fixture.h"
#include <cstdio>
#include <cstdlib>
#include <initializer_list>
static unsigned checks;
#define REQUIRE(x) do{++checks;if(!(x)){std::fprintf(stderr,"line %u: %s\n",__LINE__,#x);std::abort();}}while(0)
// Event-driven peripheral model: W1C clears ONLY requested flags; a NACK
// schedules hardware STOP independently of the application's poll schedule.
// Subsequent injected events are a model, not an inferred physical waveform.
struct Model {
 ec_state e{};uint32_t isr=1,now=0,stop_at=0;uint8_t pins=3,pos=0;
 bool pe=false,start_pending=false,stop_pending=false,lost=false,auto_stop=true;
 unsigned starts=0,stops=0,resets=0,parks=0,faults=0,terminal_count=0,premature=0;
 uint32_t before_isr=0,terminal_isr=0;uint8_t terminal_flags=0;
 uint8_t bytes[3]={0x20,8,0};
 Model(){ec_init(&e,170000000,true);}
};
static uint32_t status(void*p){return ((Model*)p)->isr;}
static void begin(void*p){auto&b=*(Model*)p;REQUIRE(b.pe&&!b.lost&&!(b.isr&EC_BUSYF)&&b.pins==3);b.starts++;b.pos=0;b.start_pending=true;b.isr=EC_BUSYF|1;}
static void write(void*p,uint8_t v){auto&b=*(Model*)p;REQUIRE(v==0x0b);b.isr&=~EC_TXIS;}
static void begin_read(void*p){auto&b=*(Model*)p;REQUIRE((b.isr&EC_TC)&&!b.start_pending);b.isr&=~EC_TC;}
static uint8_t read(void*p){auto&b=*(Model*)p;REQUIRE(b.pos<3&&(b.isr&EC_RXNE));b.isr&=~EC_RXNE;return b.bytes[b.pos++];}
static void clear(void*p){auto&b=*(Model*)p;b.isr&=~(EC_NACKF|EC_STOPF|EC_BERR|EC_ARLOF|EC_OVRF);}
static void park(void*p){auto&b=*(Model*)p;if(b.stop_at&&b.now<b.stop_at)b.premature++;b.pe=false;b.isr=1;b.start_pending=false;b.stop_pending=false;b.stop_at=0;b.parks++;}
static void reset(void*p){auto&b=*(Model*)p;b.resets++;park(p);}
static void fault(void*p,uint8_t,uint32_t isr,uint32_t,uint32_t){auto&b=*(Model*)p;b.faults++;b.before_isr=isr;REQUIRE(!b.e.recovering);}
static uint8_t lines(void*p){return ((Model*)p)->pins;}
static void enable(void*p){auto&b=*(Model*)p;REQUIRE(!b.pe);b.pe=true;}
static void clear_berr(void*p){((Model*)p)->isr&=~EC_BERR;}
static void clear_nack(void*p){((Model*)p)->isr&=~EC_NACKF;}
static bool ready(void*p){auto&b=*(Model*)p;return !b.start_pending&&!b.stop_pending;}
static void request(void*p){auto&b=*(Model*)p;REQUIRE(!b.lost&&b.pe&&ready(p));b.stops++;b.stop_pending=true;if(b.auto_stop)b.stop_at=b.now+10;}
static void flush(void*p){auto&b=*(Model*)p;REQUIRE(!b.pe||!(b.isr&EC_BUSYF));}
static void terminal(void*p,uint8_t f){auto&b=*(Model*)p;b.terminal_count++;b.terminal_isr=b.isr;b.terminal_flags=f;}
static void completed(void*p){auto&b=*(Model*)p;REQUIRE(b.pe&&!(b.isr&EC_BUSYF));}
static ec_io io(Model&b){return {&b,status,begin,write,begin_read,read,clear,reset,fault,lines,enable,park,clear_berr,clear_nack,ready,request,flush,terminal,completed};}
static void poll(Model&b,uint32_t us,uint32_t ms=5){
 b.now=us;
 if(b.stop_at&&us>=b.stop_at){b.stop_at=0;b.start_pending=false;b.stop_pending=false;b.isr=(b.isr&~EC_BUSYF)|EC_STOPF;b.pins=3;}
 auto i=io(b);ec_poll(&b.e,&i,ms,us*170U,170000000);
 REQUIRE(b.e.n<=3);
 if(b.e.recovering)REQUIRE(!b.e.bus_ok&&!b.e.angle_ok&&!b.e.speed_ok);
}
static void start(Model&b,uint32_t base=0,uint32_t ms=5){
 poll(b,base,ms);poll(b,base+5,ms);poll(b,base+10,ms);poll(b,base+15,ms);
 REQUIRE(b.e.state==1&&b.starts>0&&b.pe);b.start_pending=false;
}
static void normal(Model&b,uint32_t base,uint32_t ms,bool berr=false,bool coincident=false){
 start(b,base,ms);uint32_t flag=berr?EC_BERR:0;
 b.isr=EC_BUSYF|EC_TXIS|flag;poll(b,base+20,ms);REQUIRE(b.e.state==2);
 b.isr=EC_BUSYF|EC_TC|flag;poll(b,base+25,ms);REQUIRE(b.e.state==3);
 for(unsigned n=0;n<3;n++){b.isr=EC_RXNE|flag|(n==2&&coincident?EC_STOPF:EC_BUSYF);poll(b,base+30+5*n,ms);}
 b.isr=EC_STOPF|flag;poll(b,base+45,ms);
 REQUIRE(b.e.bus_ok&&b.e.angle_ok&&b.e.raw==2048&&!b.e.state&&b.pe);
}
static void abort_case(unsigned stage,uint32_t flag,unsigned delay,unsigned gap){
 Model b;start(b);b.e.state=(uint8_t)stage;b.e.n=stage==4?3:0;b.isr=EC_BUSYF|flag;
 b.e.bus_ok=b.e.angle_ok=b.e.speed_ok=true;
 if(flag&EC_ARLOF)b.lost=true;
 if(!(flag&EC_ARLOF))b.stop_at=50+delay;
 poll(b,50);REQUIRE(b.e.errors==1&&b.faults==1&&b.resets==0&&!b.e.bus_ok);
 for(unsigned t=50+gap;t<=1050&&b.e.recovering;t+=gap){
  if((flag&EC_ARLOF)&&t>=50+delay){b.isr=1;b.pins=3;}
  poll(b,t);
 }
 REQUIRE(!b.e.recovering&&b.e.errors==1&&b.faults==1&&b.terminal_count==1&&!b.pe&&b.stops<=1);
 if(flag&EC_ARLOF)REQUIRE(b.stops==0);
 if(delay<100&&gap<100&&!(flag&EC_ARLOF))REQUIRE(b.resets==0&&b.premature==0&&(b.terminal_isr&EC_STOPF));
 REQUIRE(b.e.reads==0&&!b.e.speed_ok&&!b.e.angle_ok);
}
int main(){
 // Exact first fault entry from recorded2702 run; only the continuation is modeled.
 Model b;b.e.state=(record[4]>>16)&255;b.e.n=record[4]>>24;b.e.stage=(record[4]>>8)&255;
 b.e.reads=record[27];b.e.errors=record[26];b.e.begin_cycles=record[3]-record[25];b.e.last_start_ms=record[2];
 b.pe=record[9]&1;b.isr=record[5];b.pins=(record[7]>>8)&3;b.start_pending=true;
 auto i=io(b);ec_poll(&b.e,&i,record[2],record[3],170000000);
 REQUIRE(b.e.cause==EC_NACK&&b.e.recovering&&b.resets==0&&b.pe&&b.before_isr==0x8011&&!(b.isr&EC_NACKF));
 b.start_pending=false;b.isr=1|EC_STOPF;ec_poll(&b.e,&i,record[2],record[3]+1700,170000000);
 REQUIRE(!b.e.recovering&&b.resets==0&&!b.pe&&(b.terminal_isr&EC_STOPF)&&b.e.errors==record[26]+1);
 // Full normal transaction, last RXNE+STOPF collision, and sole-master BERR.
 for(bool berr:{false,true})for(bool co:{false,true}){Model q;normal(q,0,5,berr,co);REQUIRE(q.e.reads==1&&q.e.errors==0&&q.resets==0);if(berr)REQUIRE(q.e.berr_clears==6);}
 for(unsigned stage=1;stage<=4;stage++)for(uint32_t flag:{(uint32_t)EC_NACKF,(uint32_t)EC_ARLOF,(uint32_t)EC_OVRF,(uint32_t)(EC_NACKF|EC_STOPF),(uint32_t)(EC_ARLOF|EC_NACKF|EC_BERR)})
  for(unsigned d:{0U,10U,90U,200U,700U})for(unsigned g:{1U,7U,40U,482U})abort_case(stage,flag,d,g);
 // Missing STOP: one request, one forced reset. No new START while recovery active.
 {Model q;start(q);q.auto_stop=false;q.isr=EC_BUSYF|EC_NACKF;poll(q,50);poll(q,149);REQUIRE(q.stops==0);poll(q,150);REQUIRE(q.stops==1);poll(q,549);REQUIRE(q.pe);poll(q,550);REQUIRE(q.resets==1&&q.e.cleanup_expired==1&&q.e.errors==1&&q.starts==1);}
 // START still pending prohibits software STOP even when the grace expired.
 {Model q;start(q);q.start_pending=true;q.isr=EC_BUSYF|EC_NACKF;poll(q,50);poll(q,200);poll(q,550);REQUIRE(q.stops==0&&q.resets==1);}
 // Acquisition deadline does not become an accepted late data sample.
 {Model q;start(q);q.isr=EC_BUSYF|EC_BERR;poll(q,3000,8);REQUIRE(q.e.cause==EC_DEADLINE&&q.e.timeouts==1&&q.e.berr_clears==0);poll(q,3010,8);REQUIRE(q.e.reads==0&&!q.e.bus_ok&&!q.e.recovering);}
 // Configuration failure still completes cleanup after configured becomes false.
 {Model q;start(q);q.isr=EC_BUSYF;auto k=io(q);ec_finish(&q.e,&k,5,50*170,170000000,EC_SETUP,q.isr);q.e.configured=0;poll(q,60);poll(q,70);REQUIRE(!q.e.recovering&&!q.pe&&q.e.primary_setup==1);}
 for(uint8_t pins:{(uint8_t)0,(uint8_t)1,(uint8_t)2}){Model q;q.pins=pins;poll(q,0);poll(q,3000,8);REQUIRE(q.e.cause==EC_BUSY&&q.starts==0&&q.stops==0&&q.e.errors==1&&q.resets==0);}
 {Model q;start(q);q.isr=EC_STOPF;poll(q,50);REQUIRE(q.e.cause==EC_SHORT&&q.e.reads==0&&q.e.clean_stops==1);}
 {Model q;start(q);q.e.state=4;q.e.n=3;q.isr=EC_RXNE|EC_STOPF;poll(q,50);REQUIRE(q.e.cause==EC_SHORT&&q.e.reads==0);}
 // Partial receive followed by NACK discards every byte of this acquisition.
 for(unsigned partial=0;partial<3;partial++){
  Model q;start(q);q.e.state=3;
  for(unsigned n=0;n<partial;n++){q.isr=EC_RXNE|EC_BUSYF;poll(q,30+5*n);}
  q.isr=EC_NACKF|EC_STOPF|EC_RXNE;poll(q,50);
  REQUIRE(q.e.reads==0&&q.e.errors==1&&!q.e.bus_ok&&!q.e.angle_ok&&!q.e.speed_ok&&q.e.clean_stops==1);
 }
 // STOPF remains set while the final RXDR byte is drained; a short frame
 // cannot be accepted merely because STOP is present alongside RXNE.
 for(unsigned count=1;count<=3;count++){
  Model q;start(q);q.e.state=3;
  for(unsigned n=0;n<count;n++){q.isr=EC_RXNE|(n+1==count?EC_STOPF:EC_BUSYF);poll(q,30+5*n);}
  q.isr=EC_STOPF;poll(q,55);
  REQUIRE(q.e.reads==(count==3?1U:0U)&&q.e.errors==(count==3?0U:1U));
 }
 // Stop+NACK before the data deadline never counts as success; BERR alone
 // must not mask a concurrent fatal event. Counters saturate instead of wrap.
 {Model q;start(q);q.e.errors=UINT32_MAX;q.e.primary_nack=UINT32_MAX;q.isr=EC_NACKF|EC_STOPF|EC_BERR;poll(q,50);REQUIRE(q.e.errors==UINT32_MAX&&q.e.primary_nack==UINT32_MAX&&q.e.berr_clears==0&&q.e.reads==0);}
 // Recovery across both hardware cycle and millisecond rollover.
 {Model q;start(q);auto k=io(q);q.isr=EC_BUSYF|EC_NACKF;q.auto_stop=false;ec_finish(&q.e,&k,UINT32_MAX,UINT32_MAX-100,170000000,EC_NACK,q.isr);ec_poll(&q.e,&k,0,85000,170000000);REQUIRE(!q.e.recovering&&q.resets==1);}
 // Backoff preserved; no retry of the aborted sample; speed needs fresh continuity.
 {Model q;normal(q,0,5);normal(q,5000,10);normal(q,10000,15);normal(q,15000,20);normal(q,20000,25);REQUIRE(q.e.speed_ok);start(q,25000,30);q.isr=EC_NACKF|EC_STOPF;poll(q,25050,30);REQUIRE(!q.e.speed_ok);unsigned s=q.starts;poll(q,30000,35);REQUIRE(q.starts==s);normal(q,45000,50);REQUIRE(!q.e.speed_ok);}
 // Two-page category counters never publish a partial, mixed or expired snapshot.
 uint32_t values[14];for(unsigned n=0;n<14;n++)values[n]=n*100+7;
 uint8_t p0[UV3_FRAME],p1[UV3_FRAME];eh_packet(p0,values,0,255);eh_packet(p1,values,1,255);eh_receiver rx{};
 REQUIRE(!eh_receive(&rx,p1,EH_PEER,true,1));REQUIRE(eh_receive(&rx,p0,EH_PEER,true,2)&&!rx.valid);
 REQUIRE(eh_receive(&rx,p1,EH_PEER,true,3)&&eh_fresh(&rx,true,3)&&!memcmp(values,rx.values,sizeof(values)));
 REQUIRE(!eh_fresh(&rx,false,3)&&!eh_fresh(&rx,true,2003));
 for(unsigned n=0;n<UV3_FRAME;n++){p0[n]^=1;eh_receiver r{};REQUIRE(!eh_receive(&r,p0,EH_PEER,true,0));p0[n]^=1;}
 REQUIRE(!eh_receive(&rx,p0,2026102702,true,3));REQUIRE(!eh_receive(&rx,p0,EH_PEER,false,3)&&!rx.valid);
 eh_packet(p0,values,0,0);eh_packet(p1,values,1,1);REQUIRE(eh_receive(&rx,p0,EH_PEER,true,UINT32_MAX-10));REQUIRE(!eh_receive(&rx,p1,EH_PEER,true,5));
 eh_packet(p1,values,1,0);REQUIRE(eh_receive(&rx,p1,EH_PEER,true,5)&&eh_fresh(&rx,true,6));
 eh_packet(p0,values,0,4);eh_packet(p1,values,1,4);REQUIRE(eh_receive(&rx,p0,EH_PEER,true,100));REQUIRE(!eh_receive(&rx,p1,EH_PEER,true,2100));
 // First-fault new format carries terminal state and cleanup flags under CRC.
 uint32_t rec[40]{};memcpy(rec,record,sizeof(rec));rec[1]=FC_PEER;rec[4]|=(uint32_t)(EC_CL_STOP|EC_CL_REQUESTED)<<26;
 fc_receiver fr{};uint8_t fp[UV3_FRAME];uint32_t crc=uv3_crc32c((uint8_t*)rec,FC_BYTES);
 for(unsigned page=0;page<FC_PAGES;page++){fc_packet(fp,rec,1,page,crc);REQUIRE(fc_receive(&fr,fp,FC_PEER,true));}
 REQUIRE(fr.slot[1].valid);fp[38]=1;uv3_seal(fp);REQUIRE(!fc_receive(&fr,fp,FC_PEER,true));
 std::printf("{\"passed\":true,\"checks\":%u,\"event_cases\":400,\"exact_record_entry\":true,\"modeled_continuation\":true,\"hardware_validated\":false}\n",checks);
}
