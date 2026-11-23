
#include <cassert>
#include <cstdio>
#include "foc_experiment.h"
#include "observer_start_history.h"
namespace peer {
#include "observer_start_history_wire.h"
}
static nh_capture c;static peer::nh_receiver r;
static void run(bool loss){
 memset(&c,0,sizeof(c));memset(&r,0,sizeof(r));ma_observer o={};ma_motor m=FE_ESTIMATED_MOTOR;
 ma_controller ctrl;ma_reset(&o,&ctrl);nh_begin(&c,&o,&m,2026111804U,123,0);
 float in[5]={0,0,0,0,.001f};uint8_t packet[UV3_FRAME];
 for(unsigned i=0;i<NH_CAPACITY;++i){
  o.steps=i+1;nh_step(&c,&o,in,nh_pair_counts(i%153U),0,0,i*170000U,i*170000U+80000U);
  assert(nh_packet(&c,packet,0));
  if(!(loss&&i==32))(void)peer::nhr_receive(&r,packet,2026111804U,2026111804U);
  nh_sent(&c);
 }
 nh_freeze(&c,&o,NH_STOP);
 for(unsigned i=0;i<NH_META_PAGES;++i){assert(nh_packet(&c,packet,1));
  assert(peer::nhr_receive(&r,packet,2026111804U,2026111804U));nh_sent(&c);}
 assert(r.complete);assert(peer::nhr_exact(&r)==!loss);
 if(!loss){assert(r.count==NH_CAPACITY);assert(!memcmp(r.rows[NH_CAPACITY-1],in,20));}
 else assert(r.gap&&r.bad>0);
}
int main(){run(false);run(true);puts("{\"passed\":true,\"capacity\":5120,\"full_transfer\":true,\"missing_row_cannot_be_exact\":true,\"synthetic_transport_only\":true}");}
