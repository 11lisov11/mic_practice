#ifndef MIC_MULTI_COMMAND_H
#define MIC_MULTI_COMMAND_H
#include <stdint.h>
#include <string.h>
static inline uint8_t ma_wire_mode(unsigned algorithm){
  return algorithm==1?3:algorithm==2?6:algorithm==3?7:algorithm==4?9:0;
}
static inline int ma_config_allowed(int enable,int estop,int clear,int force,int safe){
  return !enable&&!estop&&!clear&&!force&&safe;
}
static inline int ma_config_cancel(int clear_cmd,int force,int pwm,int start,int safe){
  return clear_cmd||force||pwm||start||!safe;
}
static inline void ma_config_encode(uint8_t*p,unsigned op,unsigned index,uint32_t value){
  /* Keep native version and transaction sequence; no enable or service outputs. */
  const uint8_t seq=p[5];memset(p+3,0,36);p[4]=8;p[5]=seq;
  p[6]=(uint8_t)op;p[7]=(uint8_t)index;
  for(unsigned i=0;i<4;i++)p[8+i]=(uint8_t)(value>>(8*i));
  p[12]=1;p[13]=0xA6;
}
#endif
