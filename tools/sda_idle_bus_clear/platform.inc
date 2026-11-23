#include "bus_clear.h"
static bc_state bus_clear;
static bool bus_clear_allowed;
static uint32_t bus_clear_saved_mode,bus_clear_saved_odr;
static void bc_gpio_enter(void*x){
  (void)x;
  bus_clear_saved_mode=GPIOB->MODER&(15U<<16);
  bus_clear_saved_odr=GPIOB->ODR&(3U<<8);
  /* Latch both released BEFORE changing AF to output; OTYPER is already OD. */
  GPIOB->BSRR=3U<<8;__DSB();
  MODIFY_REG(GPIOB->MODER,15U<<16,5U<<16);__DSB();
}
static void bc_gpio_scl(void*x,bool low){(void)x;GPIOB->BSRR=1U<<(low?24:8);__DSB();}
static void bc_gpio_sda(void*x,bool low){(void)x;GPIOB->BSRR=1U<<(low?25:9);__DSB();}
static void bc_gpio_leave(void*x){
  (void)x;GPIOB->BSRR=3U<<8;__DSB();
  MODIFY_REG(GPIOB->MODER,15U<<16,bus_clear_saved_mode);__DSB();
  GPIOB->BSRR=bus_clear_saved_odr|(((3U<<8)&~bus_clear_saved_odr)<<16);
}
static bc_io bus_clear_io={0,lines,bc_gpio_enter,bc_gpio_scl,bc_gpio_sda,bc_gpio_leave};
void mic_encoder_allow_bus_clear(bool allowed){bus_clear_allowed=allowed;}
static bool bus_clear_service(void){
  const bool allowed=bus_clear_allowed && !(TIM1->BDTR&TIM_BDTR_MOE) &&
    !(I2C1->CR1&I2C_CR1_PE) && enc.configured && !enc.state && !enc.prepare && !enc.recovering;
  if(bus_clear.active){bc_poll(&bus_clear,&bus_clear_io,DWT->CYCCNT,SystemCoreClock,allowed);return true;}
  /* Freeze the original first fault AND its PE0 observations before recovery.
     One attempt per boot; no new GPIO recovery while PWM or START is pending. */
  if(allowed && !bus_clear.attempted && enc.primary_busy && (fault_ready&1U) &&
     release_probe[0].complete && lines(0)==1U){
    bc_begin(&bus_clear,&bus_clear_io,DWT->CYCCNT);return true;
  }
  return false;
}
bool mic_encoder_bus_clear_packet(uint8_t*p){
  if(!bus_clear.attempted||bus_clear.active||!bus_clear.result)return false;
  memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=0xde;p[3]=1;
  p[4]=bus_clear.result;p[5]=bus_clear.pulses;ew_p32(p+6,EW_PEER);
  p[10]=bus_clear.before;p[11]=bus_clear.released;p[12]=bus_clear.after;
  ew_p32(p+14,bus_clear.duration_us);ew_p32(p+18,bus_clear.begin);
  ew_p32(p+22,uv3_crc32c((const uint8_t*)fault_record[0],FC_BYTES));
  uv3_seal(p);return true;
}
