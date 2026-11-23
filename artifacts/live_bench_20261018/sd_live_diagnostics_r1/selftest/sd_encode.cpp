
#include <cstdio>
#include <cstring>
#include <cassert>
#include "sd_live_status.h"
struct Gpio { unsigned MODER,OTYPER,PUPDR,AFR[2],IDR; } gpio;
struct Timer { unsigned AF1,BDTR,DIER; } tim;
#define GPIOA (&gpio)
#define TIM1 (&tim)
enum {GPIO_PIN_6=64,TIM1_AF1_BKINE=1,TIM1_AF1_BKINP=512,
 TIM_BDTR_BKE=4096,TIM_BDTR_BKP=8192,TIM_BDTR_BKBID=268435456,
 TIM_DIER_BIE=128,MIC_BKIN_RUNNING=1};
unsigned mic_bkin_capture_state,mic_bkin_record_ready;
unsigned char encode() {unsigned char reply[43]={};
  const bool sd_config_ok =
      ((GPIOA->MODER >> 12U) & 3U) == 2U &&
      (GPIOA->OTYPER & GPIO_PIN_6) != 0U &&
      ((GPIOA->PUPDR >> 12U) & 3U) == 1U &&
      ((GPIOA->AFR[0] >> 24U) & 15U) == 6U &&
      (TIM1->AF1 & (TIM1_AF1_BKINE | TIM1_AF1_BKINP)) ==
          (TIM1_AF1_BKINE | TIM1_AF1_BKINP) &&
      (TIM1->BDTR & (TIM_BDTR_BKE | TIM_BDTR_BKP | TIM_BDTR_BKBID)) ==
          (TIM_BDTR_BKE | TIM_BDTR_BKP);
  reply[21] |= sd_live_encode((GPIOA->IDR & GPIO_PIN_6) != 0U,
      (TIM1->DIER & TIM_DIER_BIE) != 0U,
      mic_bkin_capture_state == MIC_BKIN_RUNNING,
      mic_bkin_record_ready != 0U, sd_config_ok);
return reply[21];}
int main(){
 gpio={2u<<12,64,1u<<12,{6u<<24,0},0};tim={513,12288,0};
 for(unsigned mask=0;mask<16;++mask){
   gpio.IDR=(mask&1)?64:0;tim.DIER=(mask&2)?128:0;
   mic_bkin_capture_state=(mask&4)?1:2;mic_bkin_record_ready=!!(mask&8);
   Gpio beforeG=gpio;Timer beforeT=tim;
   unsigned result=encode();
   assert(!memcmp(&beforeG,&gpio,sizeof(gpio))&&!memcmp(&beforeT,&tim,sizeof(tim)));
   assert((result&3)==0);
   printf("%u\n",result);
 }
 // Wrong mode, output type, pull, AF, polarity, enable, bidirectional mode.
 unsigned *fields[]={&gpio.MODER,&gpio.OTYPER,&gpio.PUPDR,&gpio.AFR[0],&tim.AF1,&tim.AF1,&tim.BDTR,&tim.BDTR,&tim.BDTR};
 unsigned changes[]={1u<<12,64,1u<<12,1u<<24,1,512,4096,8192,268435456};
 for(unsigned i=0;i<9;++i){unsigned old=*fields[i];*fields[i]^=changes[i];assert(!(encode()&128));*fields[i]=old;}
 assert(encode()&128);
}
