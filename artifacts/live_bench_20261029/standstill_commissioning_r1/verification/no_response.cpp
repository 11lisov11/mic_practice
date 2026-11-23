
#include "identify_core.h"
#include <cassert>
int main(){
 ma_geometry g={5312,5184,771,112,240,229};ma_output output;
 for(unsigned kind=MI_DC;kind<=MI_AC;kind++){
  mi_state state={};mi_config cfg={88,kind,kind==MI_AC?1.f:0.f,0,.1f,12.23f,8000,1,{0,0,0},.025f,{0,0},0};
  cfg.calibration_crc=mi_cal_crc(&cfg);assert(mi_begin(&state,&cfg,0));
  int result=MI_OK;unsigned n=0;
  for(;n<70000&&result==MI_OK;n++){
   mi_sample sample={};sample.valid=1;sample.bus=320;sample.arr=5312;sample.epoch=n;
   sample.cycles=n*10624;for(unsigned i=0;i<3;i++)sample.ccr[i]=2656;
   result=mi_step(&state,&g,&sample,sample.cycles,170000000,&output);
  }
  assert(result==MI_NO_RESPONSE&&!state.active&&!output.valid);
  assert(n<(kind==MI_DC?22000U:50000U));
 }
}
