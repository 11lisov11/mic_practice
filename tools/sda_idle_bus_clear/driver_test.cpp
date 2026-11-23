#include "nucleo_encoder.c"
#include "bus_clear_wire.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>
static unsigned us;
static void step(unsigned dt=10){us+=dt;test_tick=us/1000;test_dwt.CYCCNT=us*170;mic_encoder_poll();}
static void emit(const uint8_t*p,unsigned n){for(unsigned j=0;j<n;j++)printf("%02x",p[j]);}
int main(int argc,char**argv){
 unsigned mode=argc>1?(unsigned)argv[1][0]-'0':0;
 test_rcc.CR=RCC_CR_HSIRDY;test_gpio.IDR=0x1d0;test_i2c.ISR.value=1;
 test_gpio.MODER=0xa5a0000a;test_gpio.ODR=0x55;mock_external_sda=true;mock_release_on=mode==1?99:4;
 mic_encoder_init();assert(enc.configured);
 for(unsigned n=0;n<900;n++)step();
 assert(enc.errors==1&&enc.primary_busy==1&&enc.reads==0&&fault_ready==1);
 assert(release_probe[0].complete&&release_probe[0].after[0].gpio==0x1d0);
 uint32_t parent[40];memcpy(parent,fault_record[0],sizeof(parent));sr_probe probe=release_probe[0];
 uint32_t mode_before=GPIOB->MODER,odr_before=GPIOB->ODR;
 // No recovery without an explicit main-loop OFF gate.
 assert(!bus_clear.attempted&&!mock_gpio_writes);
 mic_encoder_allow_bus_clear(true);
 if(mode==2)TIM1->BDTR=TIM_BDTR_MOE;
 for(unsigned n=0;n<300;n++)step();
 if(mode==2){assert(!bus_clear.attempted&&!mock_gpio_writes);puts("{\"passed\":true,\"mode\":2}");return 0;}
 assert(bus_clear.attempted&&!bus_clear.active&&bus_clear.result==(mode==1?BC_SDA_LOW:BC_CLEARED));
 assert(bus_clear.pulses==9);
 assert(GPIOB->MODER==mode_before&&GPIOB->ODR==odr_before);
 assert(!memcmp(parent,fault_record[0],sizeof(parent))&&!memcmp(&probe,&release_probe[0],sizeof(probe)));
 assert(!(I2C1->CR1&1)&&!I2C1->CR2); // No new START in the error backoff.
 uint8_t packet[43];assert(mic_encoder_bus_clear_packet(packet));assert(bc_packet_valid(packet,EW_PEER,true));
 for(unsigned i=0;i<43;i++){uint8_t bad[43];memcpy(bad,packet,43);bad[i]^=1;assert(!bc_packet_valid(bad,EW_PEER,true));}
 assert(!bc_packet_valid(packet,EW_PEER,false)&&!bc_packet_valid(packet,EW_PEER-2,true));
 if(!mode){
  // Once the bus clears, the unchanged production state machine reads the sensor.
  for(unsigned n=0;enc.state!=1&&n<2000;n++)step();
  assert(enc.state==1);
  I2C1->CR2&=~I2C_CR2_START;I2C1->ISR.value=EC_TXIS|EC_BUSYF;step();assert(enc.state==2&&I2C1->TXDR==0x0b);
  I2C1->ISR.value=EC_TC|EC_BUSYF;step();assert(enc.state==3);I2C1->CR2&=~I2C_CR2_START;
  for(unsigned b:{0x20U,7U,99U}){I2C1->RXDR=b;I2C1->ISR.value=EC_RXNE|EC_BUSYF;step();}
  I2C1->ISR.value=EC_STOPF;step();assert(enc.reads==1&&enc.bus_ok&&enc.angle_ok&&enc.raw==1891);
 }
 assert(!memcmp(parent,fault_record[0],sizeof(parent)));
 printf("{\"passed\":true,\"mode\":%u,\"record\":\"",mode);emit(packet,43);printf("\",\"parent\":\"");emit((uint8_t*)parent,160);puts("\"}");
}
