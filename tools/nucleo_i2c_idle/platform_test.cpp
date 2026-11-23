// Include the complete candidate C driver. Only MCU registers/HAL are mocked.
#include "nucleo_encoder.c"
#include <cassert>
#include <cstdio>
int main(){
 test_rcc.CR=RCC_CR_HSIRDY;test_gpio.IDR=0x300;test_i2c.ISR=1;
 mic_encoder_init();assert(enc.configured&&config_ok()&&!(I2C1->CR1&1));
 test_tick=5;test_dwt.CYCCNT=100000;mic_encoder_poll();assert(enc.prepare==1&&config_ok());
 test_dwt.CYCCNT+=1700;mic_encoder_poll();assert(enc.prepare==2&&config_ok()&&(I2C1->CR1&1));
 test_dwt.CYCCNT+=1700;mic_encoder_poll();test_dwt.CYCCNT+=1700;mic_encoder_poll();
 assert(enc.state==1&&config_ok());
 I2C1->ISR=EC_TXIS;test_dwt.CYCCNT+=1700;mic_encoder_poll();assert(enc.state==2);
 I2C1->ISR=EC_TC;test_dwt.CYCCNT+=1700;mic_encoder_poll();assert(enc.state==3);
 for(unsigned n=0;n<3;++n){I2C1->ISR=EC_RXNE;I2C1->RXDR=n==0?0x20:n==1?8:0;test_dwt.CYCCNT+=1700;mic_encoder_poll();}
 I2C1->ISR=EC_STOPF;test_dwt.CYCCNT+=1700;mic_encoder_poll();
 assert(enc.reads==1&&enc.bus_ok&&enc.angle_ok&&enc.state==0&&config_ok()&&!(I2C1->CR1&1)&&I2C1->CR2==0);
 uint8_t p[UV3_FRAME];mic_encoder_packet(p,EW_PEER);ew_receiver rx{};
 assert(p[37]==0&&p[38]==2&&ew_receive(&rx,p,EW_PEER,true,10));
 // BERR workaround writes only BERRCF; no STOP/RX data access here.
 I2C1->ICR=0;clear_berr(0);assert(I2C1->ICR==I2C_ICR_BERRCF);
 // A real hardware configuration mismatch makes the sample unusable.
 I2C1->TIMINGR^=1;test_tick=6;test_dwt.CYCCNT+=1700;mic_encoder_poll();
 assert(!enc.configured&&!enc.bus_ok&&!enc.angle_ok&&!enc.speed_ok);
 std::puts("{\"passed\":true,\"actual_platform_driver_compiled\":true,\"parked_PE0_packet_validated\":true,\"configuration_mismatch_rejected\":true}");
}
