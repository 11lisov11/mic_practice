
#include <cassert>
#include <cstdio>
#include <cstring>
#include "observer_trace_core.h"
#include "observer_trace_wire.h"
int main(){
 unsigned tests=0;
 assert(sizeof(od_sample)==96&&sizeof(od_blob)==1696);++tests;
 assert(od_reasons(1,1,500,0,.2f,.25f,0)==0);++tests;
 assert(od_reasons(1,1,500,0,.125f,.25f,0)==OD_FLUX);++tests;
 assert(od_reasons(1,1,500,0,.2f,.25f,25)==OD_NIS);++tests;
 assert(od_reasons(1,1,499,0,.2f,.25f,0)==OD_WARMUP);++tests;
 assert(od_reasons(1,1,500,0,NAN,.25f,0)==(OD_FLUX|OD_NONFINITE));++tests;
 od_capture c={};od_begin(&c,2026103016U);
 for(unsigned i=1;i<=5000;++i){
   od_sample r={};r.steps=i;r.cycles=i*170000U;r.rpm=300;r.flux_alpha=.2f;
   r.nis=i>=700&&i<750?26.f:0.f;r.reasons=od_reasons(1,1,i,0,.2f,.25f,r.nis);
   r.id=.4f;r.iq=.1f;r.id_ref=.5f;r.iq_ref=.2f;r.reference_hz=5;r.dt=.001f;r.published=1;
   od_push(&c,&r);++tests;
 }
 assert(c.blob.header.first_loss_present&&c.blob.header.first_loss_step==700);
 assert(c.blob.first_loss.reasons==OD_NIS);++tests;
 od_freeze(&c,0);assert(c.blob.header.count==16&&c.blob.header.oldest==0);++tests;
 assert(c.blob.sample[0].steps==1&&c.blob.sample[15].steps==5000);++tests;
 c.blob.header.crc=uv3_crc32c((uint8_t*)&c.blob,OD_BYTES);
 od_blob saved=c.blob;od_begin(&c,2026103016U);od_push(&c,&c.latest);od_freeze(&c,3);
 assert(memcmp(&saved,&c.blob,sizeof(saved))==0);++tests;
 auto packet=[&](unsigned page,uint8_t*p){
  memset(p,0,43);p[0]=0x55;p[1]=0xaa;p[2]=OD_WIRE;p[3]=p[4]=1;p[5]=page;p[6]=OD_PAGES;
  p[7]=page==56?16:30;memcpy(p+8,((uint8_t*)&saved)+page*30,p[7]);p[38]=1;uv3_seal(p);
 };
 od_receiver rx={};uint8_t bytes[43];
 for(int i=56;i>=0;--i){packet(i,bytes);assert(odw_receive(&rx,bytes,2026103016U,2026103016U,true));++tests;}
 assert(rx.complete&&memcmp(rx.data,&saved,OD_BYTES)==0);++tests;
 packet(0,bytes);assert(!odw_receive(&rx,bytes,2026103016U,2026103016U,false));++tests;
 assert(!odw_receive(&rx,bytes,0,2026103016U,true));++tests;
 for(unsigned bit=0;bit<43*8;++bit){uint8_t damaged[43];memcpy(damaged,bytes,43);damaged[bit/8]^=1<<(bit%8);
  assert(!odw_receive(&rx,damaged,2026103016U,2026103016U,true));++tests;}
 bytes[8]^=1;uv3_seal(bytes);assert(!odw_receive(&rx,bytes,2026103016U,2026103016U,true));++tests;
 printf("{\"checks\":%u,\"trace_hex\":\"",tests);
 for(unsigned i=0;i<OD_BYTES;++i)printf("%02x",rx.data[i]);printf("\"}\n");
}
