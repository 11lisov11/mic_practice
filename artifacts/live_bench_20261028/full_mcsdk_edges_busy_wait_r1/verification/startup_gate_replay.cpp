#include <initializer_list>

#include "nucleo_encoder.c"
#include <cassert>
#include <cstdio>
static uint32_t us;
static void step(){us+=10;test_tick=us/1000;test_dwt.CYCCNT=us*170;mic_encoder_poll();}
int main(){
 test_rcc.CR=RCC_CR_HSIRDY;test_gpio.IDR=0x1d0;test_i2c.ISR.value=1;
 test_gpio.MODER=0xa5a0000a;mock_external_sda=true;mock_release_on=4;
 mic_encoder_init();assert(enc.configured);
 while(us<300000)step();
 #if FIXED_WAIT
 assert(enc.errors==1&&enc.primary_busy==1);
 #else
 assert(enc.errors==15&&enc.primary_busy==15);
 #endif
 assert(enc.reads==0&&!enc.bus_ok&&!enc.angle_ok&&!enc.speed_ok&&enc.cause==EC_BUSY);
 assert(!bus_clear.attempted&&!mock_gpio_writes&&!(I2C1->CR1&1)&&!I2C1->CR2);
 assert(fault_ready==1&&release_probe[0].complete);
 const unsigned before=enc.errors;uint32_t frozen[40];memcpy(frozen,fault_record[0],sizeof(frozen));sr_probe probe=release_probe[0];
 mic_encoder_allow_bus_clear(true);
 while(!bus_clear.result && us<310000)step();
 assert(bus_clear.result==BC_CLEARED&&bus_clear.pulses==9&&!bus_clear.active);
 assert(enc.errors==before&&!memcmp(frozen,fault_record[0],sizeof(frozen))&&!memcmp(&probe,&release_probe[0],sizeof(probe)));
 while(enc.state!=1&&us<350000)step();
 assert(enc.state==1);
 I2C1->CR2&=~I2C_CR2_START;I2C1->ISR.value=EC_TXIS|EC_BUSYF;step();assert(enc.state==2);
 I2C1->ISR.value=EC_TC|EC_BUSYF;step();assert(enc.state==3);I2C1->CR2&=~I2C_CR2_START;
 for(unsigned b: {0x20U,7U,99U}){I2C1->RXDR=b;I2C1->ISR.value=EC_RXNE|EC_BUSYF;step();}
 I2C1->ISR.value=EC_STOPF;step();assert(enc.reads==1&&enc.bus_ok&&enc.angle_ok&&enc.raw==1891);
 assert(enc.errors==before&&!memcmp(frozen,fault_record[0],sizeof(frozen)));
 printf("{\"passed\":true,\"fixed_wait\":%u,\"BUSY_before_gate\":%u,\"recovery_pulses\":9,\"first_snapshot_preserved\":true,\"healthy_read_after\":true,\"hardware_calls\":0}\n",FIXED_WAIT,before);
}
