
#include "identify_core.h"
#include <cassert>
#include <random>
int main(){
 ma_geometry g={5312,5184,771,112,240,229};std::mt19937 rng(26);
 std::uniform_real_distribution<float> voltage(-60,60),bus(250,350);
 unsigned accepted=0;
 for(unsigned n=0;n<50000;n++){
  float va=voltage(rng),vb=voltage(rng),dc=bus(rng);ma_output out={};
  int rc=mi_modulate(&g,va,vb,dc,&out);
  if(rc==MA_OK){
   accepted++;assert(mic_current_window_safe(out.pair,out.ccr[0],out.ccr[1],out.ccr[2],out.trigger,g.settle,g.acquire));
   for(unsigned k=0;k<3;k++)assert(out.ccr[k]>=g.min_pulse&&out.ccr[k]<=g.arr-g.min_pulse);
   assert(hypotf(va-out.va,vb-out.vb)<.14f);
  }else assert(rc==MA_WINDOW);
 }
 assert(accepted>45000);
 ma_output out={};assert(mi_modulate(&g,NAN,0,320,&out)==MA_BUS);
 assert(mi_modulate(&g,0,INFINITY,320,&out)==MA_BUS);
 assert(mi_modulate(&g,1.e30f,1.e30f,320,&out)!=MA_OK);
 assert(mi_modulate(&g,1,0,20,&out)==MA_BUS);
}
