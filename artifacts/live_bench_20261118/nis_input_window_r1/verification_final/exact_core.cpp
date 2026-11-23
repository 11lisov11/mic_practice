
#include <cassert>
#include "peak_core.h"
extern "C" __declspec(dllexport) unsigned sizes(){return sizeof(pc_capture);}
static pc_sample point(uint32_t origin,unsigned n,unsigned corrupt){
 pc_sample s={};s.cycles=origin+n*10624U;s.epoch_before=s.epoch_after=n;
 s.raw[0]=(uint16_t)(2070U+n%13U);s.raw[1]=(uint16_t)(2050U+n%17U);
 s.pair=(uint8_t)(n%3U);s.flags=111;s.arr=5312;s.bus_v=320;
 for(unsigned i=0;i<4;++i){s.offset[i]=(uint16_t)(2060U+i);s.active_ccr[i]=(uint16_t)(2000U+300U*i+n%9U);}
 s.active_ccr[3]=5184;
 if(corrupt==1&&n==95)s.flags|=128;
 if(corrupt==2&&n==95)s.cycles+=100000U;
 if(corrupt==3&&n>=98)s.offset[0]++;
 if(corrupt==4&&n==95)s.active_ccr[1]=9000;
 return s;
}
extern "C" __declspec(dllexport) unsigned fixture(uint32_t origin,unsigned late,unsigned corrupt,unsigned wrong,uint8_t*blob){
 pc_capture c;pc_init(&c);
 for(unsigned n=1;n<=100U+late;++n){auto s=point(origin,n,corrupt);pc_push(&c,&s,n,1,1,0);}
 pc_request_observer(&c,origin+85U*10624U+(wrong==1),origin+100U*10624U+(wrong==2),503);
 for(unsigned n=101U+late;n<=108U+late&&!c.frozen;++n){auto s=point(origin,n,corrupt);pc_push(&c,&s,n,1,1,0);}
 assert(c.frozen);auto frozen=c.blob;
 pc_request_observer(&c,origin+85U*10624U+(wrong==1),origin+100U*10624U+(wrong==2),503);
 auto later=point(origin,500,0);pc_push(&c,&later,500,1,1,10000);
 assert(!memcmp(&frozen,&c.blob,sizeof(frozen)));
 c.blob.header.firmware=2026111716U;c.blob.header.crc=pc_crc((const uint8_t*)&c.blob);
 memcpy(blob,&c.blob,1024);return c.blob.header.flags;
}
extern "C" __declspec(dllexport) unsigned peak_stop(uint8_t*blob){
 unsigned checks=0;pc_capture c;pc_init(&c);auto s=point(0,1,0);
 pc_push(&c,&s,0,0,1,1000);assert(!c.frozen&&!c.count);++checks;
 for(unsigned n=1;n<=100;++n){s=point(0,n,0);pc_push(&c,&s,n,1,1,n==50?626:0);}
 assert(c.frozen&&c.total==56&&c.blob.header.flags==PC_PEAK);++checks;
 auto before=c.blob;pc_request_observer(&c,85U*10624U,100U*10624U,503);
 assert(!memcmp(&before,&c.blob,sizeof(before)));++checks;
 pc_init(&c);s=point(0,1,0);pc_push(&c,&s,1,1,1,0);s=point(0,2,0);pc_push(&c,&s,2,0,1,0);
 assert(c.frozen&&c.blob.header.flags==PC_NO_PEAK);++checks;
 memcpy(blob,&c.blob,1024);return checks;
}
