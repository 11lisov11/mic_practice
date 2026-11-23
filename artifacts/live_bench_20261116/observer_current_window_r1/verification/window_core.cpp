
#include <cassert>
#include <initializer_list>
#include <cstdio>
#include "observer_current_window.h"
#include "observer_forecast.h"
#include "foc_experiment.h"
#include "observer_trace_core.h"
#include "observer_trace_wire.h"
int main(){
 unsigned checks=0;
 for(unsigned origin:{100000U,0xffff0000U}){
  ow_state s;ow_reset(&s,origin);ow_bin b={};unsigned now=origin;
  for(unsigned block=0;block<3;++block){
   for(unsigned i=0;i<16;++i){
    now+=10624;const float va=block*10.f+i,vb=-2.f*va;
    int rc=ow_push(&s,now,31875,1.f+.01f*i,-.5f,va,vb,&b);
    assert(rc==(i==15));++checks;
   }
   assert(b.end==now&&b.center==now-79680U&&b.first==now-159360U&&b.count==16);
   assert(fabsf(b.ia-1.075f)<1e-6f&&b.ib==-.5f);++checks;
   // Independent sum of ZOH integrals at the two half-interval boundaries.
   double head=0,tail=0,previous=0;
   for(unsigned i=0;i<16;++i){double v=block*10.+i;
    if(i<8)head+=v;else if(i==8){head+=v*.5;tail+=v*.5;}else tail+=v;
    if(block&&i>=8)previous+=((block-1)*10.+i)*(i==8?.5:1.);
   }
   double mean=(head+previous)/(block?16.:8.5);
   assert(fabs(b.va-mean)<3e-6&&fabs(b.tail_va-tail/7.5)<3e-6);++checks;
  }
 }
 for(unsigned bad=0;bad<6;++bad){
  ow_state s;ow_reset(&s,1000);ow_bin b={};unsigned t=11624;
  float ia=.1f,ib=.2f,va=1,vb=2;
  if(bad==0)t=1000;if(bad==1)t=1000+31875;
  if(bad==2)ia=NAN;if(bad==3)ib=INFINITY;if(bad==4)va=NAN;if(bad==5)vb=INFINITY;
  assert(ow_push(&s,t,31875,ia,ib,va,vb,&b)==-1&&s.n==0);++checks;
 }
 // Never complete a16-point measurement by padding a partial record.
 ow_state s;ow_reset(&s,0);ow_bin b={};
 for(unsigned i=1;i<=12;++i)assert(ow_push(&s,10624*i,31875,.1f,.2f,1,2,&b)==0);
 assert(s.n==12);++checks;
 ma_motor m=FE_ESTIMATED_MOTOR;float x[6]={.3f,-.1f,.2f,.04f,20.f,0},y[6],copy[6];
 memcpy(copy,x,sizeof(x));assert(ow_forecast(&m,x,2,3,.0005f,y)==MA_OK);
 assert(memcmp(x,copy,sizeof(x))==0&&memcmp(x,y,sizeof(x))!=0);++checks;
 assert(ow_forecast(&m,x,2,3,.00101f,y)==MA_INVALID);++checks;
 x[0]=NAN;assert(ow_forecast(&m,x,2,3,.0005f,y)==MA_OBSERVER);++checks;
 od_capture capture={};od_begin(&capture,2026111612);od_sample row={};
 row.steps=500;row.observation_cycles=100000;row.window_first_cycles=20320;
 row.observer_adc_cycles=row.bin_cycles=179680;row.window_count=16;row.forecast_dt=.0004687059f;
 od_push(&capture,&row);row.steps=501;row.reasons=OD_NIS;row.nis=42;od_push(&capture,&row);
 od_freeze(&capture,0);capture.blob.header.crc=odw_crc((const uint8_t*)&capture.blob);
 auto frozen=capture.blob;od_begin(&capture,999);row.steps=502;od_push(&capture,&row);od_freeze(&capture,2);
 assert(!memcmp(&frozen,&capture.blob,sizeof(frozen)));++checks;
 od_receiver rx={};uint8_t packet[43];
 for(int page=OD_PAGES-1;page>=0;--page){
  memset(packet,0,sizeof(packet));packet[0]=0x55;packet[1]=0xaa;packet[2]=OD_WIRE;
  packet[3]=3;packet[4]=1;packet[5]=page;packet[6]=OD_PAGES;packet[7]=page==62?28:30;packet[38]=1;
  memcpy(packet+8,(uint8_t*)&frozen+page*30,packet[7]);uv3_seal(packet);
  auto before=rx;assert(!odw_receive(&rx,packet,2026111612,2026111612,false));
  rx=before;assert(odw_receive(&rx,packet,2026111612,2026111612,true));++checks;
 }
 assert(rx.complete&&!memcmp(rx.data,&frozen,OD_BYTES));++checks;
 packet[9]^=1;assert(!odw_receive(&rx,packet,2026111612,2026111612,true));++checks;
 FILE*f=fopen("schema3.bin","wb");assert(f);fwrite(&frozen,1,sizeof(frozen),f);fclose(f);
 printf("{\"checks\":%u}\n",checks);
}
