
#include <cassert>
#include "observer_trace_core.h"
#include "observer_trace_wire.h"
#include "foc_experiment.h"
static od_sample row(const ma_observer*o,const float*v){
 od_sample r={};r.steps=o->steps;r.reasons=OD_NIS;r.nis=o->nis;
 r.ia=v[0];r.ib=v[1];r.va=v[2];r.vb=v[3];r.dt=v[4];
 r.cycles=310000;r.control_adc_cycles=r.observer_adc_cycles=r.bin_cycles=300000;
 r.observation_cycles=220320;r.window_first_cycles=140640;r.window_count=16;r.forecast_dt=79680.f/170000000.f;
 return r;
}
extern "C" __declspec(dllexport) int capture(const ma_observer*prior,const ma_observer*post,
 const ma_motor*m,const float*v,int rc,uint8_t*blob){
 od_capture c={};od_begin(&c,2026111714U);
 int staged=od_replay_stage(&c,prior,m,v[0],v[1],v[2],v[3],v[4]);
 od_replay_commit(&c,post,rc,staged);od_sample r=row(post,v);od_push(&c,&r);od_freeze(&c,rc);
 c.blob.header.crc=odw_crc((const uint8_t*)&c.blob);memcpy(blob,&c.blob,OD_BYTES);
 return c.replay_latched;
}
extern "C" __declspec(dllexport) unsigned checks(){
 unsigned n=0;ma_motor m=FE_ESTIMATED_MOTOR;ma_observer prior={};
 for(unsigned i=0;i<6;++i){prior.x[i]=.01f*(i+1);for(unsigned j=0;j<6;++j)prior.p[i][j]=.001f*(i*6+j+1);}
 prior.steps=499;prior.rejected=3;
 float v[5]={.9f,-.5f,8.f,4.f,.001f};od_capture c={};od_begin(&c,2026111714U);
 int staged=od_replay_stage(&c,&prior,&m,v[0],v[1],v[2],v[3],v[4]);assert(staged);++n;
 ma_observer post=prior;post.steps=500;post.nis=25.f;post.x[0]+=.1f;post.p[0][5]+=.2f;
 od_replay_commit(&c,&post,0,staged);assert(c.replay_latched&&!c.seen_valid);++n;
 assert(!memcmp(c.blob.replay.prior_x,prior.x,sizeof(prior.x)));++n;
 assert(!memcmp(c.blob.replay.prior_p,prior.p,sizeof(prior.p)));++n;
 assert(!memcmp(c.blob.replay.post_x,post.x,sizeof(post.x)));++n;
 assert(!memcmp(c.blob.replay.post_p,post.p,sizeof(post.p)));++n;
 assert(!memcmp(&c.blob.replay.motor,&m,sizeof(m)));++n;
 assert(!memcmp(c.blob.replay.input,v,sizeof(v)));++n;
 auto first=c.blob.replay;od_begin(&c,123);assert(!memcmp(&first,&c.blob.replay,sizeof(first)));++n;
 assert(!od_replay_stage(&c,&post,&m,0,0,0,0,.001f));++n;
 post.nis=100;od_replay_commit(&c,&post,5,1);assert(!memcmp(&first,&c.blob.replay,sizeof(first)));++n;
 od_sample r=row(&post,v);od_push(&c,&r);od_freeze(&c,5);assert(c.blob.header.schema==4&&(c.blob.header.flags&4));++n;
 auto frozen=c;od_begin(&c,999);od_push(&c,&r);od_freeze(&c,0);
 assert(!memcmp(&frozen,&c,sizeof(c)));++n;
 od_capture no_loss={};od_begin(&no_loss,2026111714U);post.nis=24.999f;
 staged=od_replay_stage(&no_loss,&prior,&m,1,2,3,4,.001f);od_replay_commit(&no_loss,&post,0,staged);
 assert(!no_loss.replay_latched);++n;
 od_push(&no_loss,&r);od_freeze(&no_loss,0);od_replay zero={};
 assert(!(no_loss.blob.header.flags&4)&&!memcmp(&zero,&no_loss.blob.replay,sizeof(zero)));++n;
 prior.steps=498;od_capture warm={};assert(!od_replay_stage(&warm,&prior,&m,1,2,3,4,.001f));++n;
 assert(sizeof(od_blob)==1888&&sizeof(od_replay)==456&&sizeof(od_capture)==2052);++n;
 // Receive all63 pages in reverse order, reject transmission while ON,
 // detect conflicting duplicates and corrupted bytes with correct packet CRC.
 c.blob.header.crc=odw_crc((const uint8_t*)&c.blob);od_receiver rx={};
 for(int page=OD_PAGES-1;page>=0;--page){
  uint8_t packet[43]={};packet[0]=0x55;packet[1]=0xaa;packet[2]=OD_WIRE;packet[3]=4;packet[4]=1;
  packet[5]=(uint8_t)page;packet[6]=OD_PAGES;packet[7]=page==62?28:30;packet[38]=1;
  memcpy(packet+8,(const uint8_t*)&c.blob+page*30,packet[7]);uv3_seal(packet);
  assert(!odw_receive(&rx,packet,2026111714U,2026111714U,false));++n;
  assert(odw_receive(&rx,packet,2026111714U,2026111714U,true));++n;
 }
 assert(rx.complete&&!memcmp(rx.data,&c.blob,1888));++n;
 uint8_t bad[43]={};bad[0]=0x55;bad[1]=0xaa;bad[2]=OD_WIRE;bad[3]=4;bad[4]=1;
 bad[5]=0;bad[6]=OD_PAGES;bad[7]=30;bad[38]=1;memcpy(bad+8,&c.blob,30);bad[8]^=1;uv3_seal(bad);
 assert(!odw_receive(&rx,bad,2026111714U,2026111714U,true));++n;
 bad[8]^=1;bad[3]=3;uv3_seal(bad);assert(!odw_receive(&rx,bad,2026111714U,2026111714U,true));++n;
 bad[3]=4;uv3_seal(bad);assert(!odw_receive(&rx,bad,2026111712U,2026111714U,true));++n;
 return n;
}
