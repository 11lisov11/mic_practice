
#include <cassert>
#include <cstdio>
#include "peak_core.h"
#include "peak_wire.h"

static pc_sample sample(unsigned n){pc_sample s={};s.cycles=n*10625;s.pair=0;s.next_pair=0;s.arr=5312;s.raw[0]=2048;s.raw[1]=2048;
 for(unsigned i=0;i<4;++i)s.offset[i]=2048;return s;}
int main(){
 pc_capture c={};for(unsigned n=0;n<30;++n){auto s=sample(n);pc_push(&c,&s,n,1,1,20);}
 pc_request_observer(&c);for(unsigned n=30;n<37;++n){auto s=sample(n);pc_push(&c,&s,n,1,0,20);}
 assert(c.frozen&&c.blob.header.flags==PC_OBSERVER&&c.count==12);
 c.blob.header.firmware=2026111602;c.blob.header.crc=pc_crc((uint8_t*)&c.blob);
 auto before=c;pc_request_observer(&c);auto s=sample(100);pc_push(&c,&s,100,1,1,900);
 assert(!memcmp(&c,&before,sizeof(c)));
 FILE*f=fopen("C:/mic_practice/artifacts/live_bench_20261116/observer_adc_delivery_r1/verification/observer_loss_ADC.bin","wb");assert(f);assert(fwrite(&c.blob,1,1024,f)==1024);fclose(f);
 pc_receiver rx={};
 for(unsigned page=0;page<35;++page){uint8_t p[43]={0x55,0xaa,0xd8,1,1,(uint8_t)page,35};
  p[7]=page==34?4:30;memcpy(p+8,((uint8_t*)&c.blob)+30*page,p[7]);p[38]=1;uv3_seal(p);
  assert(pc_receive(&rx,p,2026111602,true,100));}
 assert(rx.complete&&!memcmp(rx.data,&c.blob,1024));
 pc_capture shortc={};pc_request_observer(&shortc);
 for(unsigned n=0;n<3;++n){auto s=sample(n);pc_push(&shortc,&s,n,n<2,1,1);}
 assert(shortc.frozen&&shortc.blob.header.flags==(PC_OBSERVER|PC_SHORT));
 pc_capture threshold={};for(unsigned n=0;n<8;++n){auto s=sample(n);pc_push(&threshold,&s,n,1,1,626);}
 assert(threshold.frozen&&threshold.blob.header.flags==PC_PEAK);
 pc_capture no={};for(unsigned n=0;n<5;++n){auto s=sample(n);pc_push(&no,&s,n,n<4,1,20);}
 assert(no.frozen&&no.blob.header.flags==PC_NO_PEAK);
 puts("{\"capture_requests\":true,\"frozen_immutable\":true,\"threshold626_unchanged\":true,\"raw1024_wire_roundtrip\":true}");
}
