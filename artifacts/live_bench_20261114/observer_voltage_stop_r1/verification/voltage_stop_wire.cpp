
#include <cassert>
#include <cstdio>
#include "observer_applied_voltage.h"
#include "observer_trace_core.h"
#include "observer_trace_wire.h"
#include "stop_evidence.h"
int main(){
 ma_geometry g={5312,5184,771,112,240,229};uint16_t c[3]={2600,2800,2500};float a,b;
 assert(!ma_applied_voltage(&g,c,5312,323,.3f,-.2f,&a,&b));
 float expected_a=((2600.f-(2600.f+2800+2500)/3.f)*323/5312);
 float loss=323.f*229/(2.f*5312);
 float p[3]={loss,loss*ma_clip((-.5f*.3f+.8660254038f*-.2f)/.05f,-1,1),loss*ma_clip((-.5f*.3f-.8660254038f*-.2f)/.05f,-1,1)};
 expected_a-=(2*p[0]-p[1]-p[2])/3;
 assert(fabsf(a-expected_a)<1.e-5f);
 assert(ma_applied_voltage(&g,c,0,323,.3f,-.2f,&a,&b)==MA_BUS);
 c[1]=6000;assert(ma_applied_voltage(&g,c,5312,323,.3f,-.2f,&a,&b)==MA_WINDOW);
 StopEvidence stop;stop.capture(1,842,1,3,0,99,0,341,800,1,7,10);auto saved=stop;
 stop.capture(2,999,2,0,0,0,0,0,0,0,0,0);assert(memcmp(&stop,&saved,sizeof(stop))==0);
 od_capture cap={};od_begin(&cap,2026111406);
 for(unsigned i=1;i<=5000;++i){od_sample r={};r.steps=i;r.nis=i==600?37.f:0;r.flux_alpha=.235f;
 r.reasons=od_reasons(1,1,i,0,.235f,.25f,r.nis);r.published=1;od_push(&cap,&r);}
 assert(cap.blob.header.first_loss_step==600);od_freeze(&cap,0);
 assert(cap.blob.header.schema==2&&cap.blob.header.count==12&&sizeof(od_blob)==1832);
 cap.blob.header.crc=uv3_crc32c((uint8_t*)&cap.blob,OD_BYTES);od_receiver rx={};uint8_t f[43];
 for(unsigned n=0;n<OD_PAGES;++n){memset(f,0,43);f[0]=0x55;f[1]=0xaa;f[2]=OD_WIRE;f[3]=2;f[4]=1;
 f[5]=n;f[6]=OD_PAGES;f[7]=n==OD_PAGES-1?2:30;f[38]=1;memcpy(f+8,((uint8_t*)&cap.blob)+n*30,f[7]);uv3_seal(f);
 assert(odw_receive(&rx,f,2026111406,2026111406,true));}
 assert(rx.complete);f[3]=1;uv3_seal(f);assert(!odw_receive(&rx,f,2026111406,2026111406,true));
 puts("active voltage, immutable stop evidence, schema2 recorder/transport passed");
}
