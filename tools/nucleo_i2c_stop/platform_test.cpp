// Compile entire production C driver with MMIO register semantics, including W1C.
#include "nucleo_encoder.c"
#include <cassert>
#include <cstdio>
static void step(unsigned us){test_dwt.CYCCNT=us*170;mic_encoder_poll();}
static void start(unsigned base){step(base);step(base+5);step(base+10);step(base+15);assert(enc.state==1&&config_ok());}
int main(){
 test_rcc.CR=RCC_CR_HSIRDY;test_gpio.IDR=0x300;test_i2c.ISR.value=1;
 mic_encoder_init();assert(enc.configured&&config_ok()&&I2C1->CR1==0x200);
 test_tick=5;start(0);assert(I2C1->CR2==0x1206c);
 TIM1->BDTR=32768;
 I2C1->ISR.value=0x8011;step(30);
 assert(enc.recovering&&I2C1->CR1==0x201&&I2C1->ICR.last==16&&I2C1->ISR.value==0x8001);
 assert(fault_pending==3&&fault_ready==0&&enc.resets==0);
 // Capture must not be transmitted incomplete.
 uint8_t p[UV3_FRAME];assert(!mic_encoder_fault_packet(p,1,0));
 I2C1->CR2&=~I2C_CR2_START;I2C1->ISR.value=EC_STOPF|1;step(40);
 assert(!enc.recovering&&I2C1->CR1==0x200&&I2C1->CR2==0&&enc.resets==0&&enc.clean_stops==1);
 assert(fault_ready==3&&!fault_pending);
 for(unsigned slot=0;slot<2;slot++){
  assert(fault_record[slot][5]==0x8011&&fault_record[slot][35]==(EC_STOPF|1)&&fault_record[slot][36]==0x201);
  assert((fault_record[slot][4]>>26)==EC_CL_STOP);
 }
 uint32_t frozen[40];memcpy(frozen,fault_record[1],sizeof(frozen));
 assert(mic_encoder_fault_packet(p,1,0)&&p[38]==2&&uv3_crc_ok(p));
 // Follow-up normal frame and actual producer, with PE parked in the wire sample.
 test_tick=25;TIM1->BDTR=0;start(20000);
 I2C1->CR2&=~I2C_CR2_START;I2C1->ISR.value=EC_BUSYF|EC_TXIS;step(20020);assert(I2C1->TXDR==0x0b);
 I2C1->ISR.value=EC_BUSYF|EC_TC;step(20025);assert(I2C1->CR2==(0x6c|(3U<<16)|(1U<<25)|(1U<<13)|(1U<<10)));
 I2C1->CR2&=~I2C_CR2_START;
 for(unsigned n=0;n<3;n++){I2C1->ISR.value=EC_RXNE|EC_BUSYF;I2C1->RXDR=n==0?0x20:n==1?8:0;step(20030+5*n);}
 I2C1->ISR.value=EC_STOPF|1;step(20045);assert(enc.reads==1&&enc.bus_ok&&enc.raw==2048&&config_ok());
 mic_encoder_packet(p,EW_PEER);ew_receiver rx{};assert(ew_receive(&rx,p,EW_PEER,true,25)&&p[37]==0);
 // Active configuration mismatch cannot strand recovery or publish old data.
 test_tick=30;start(25000);I2C1->ISR.value=EC_BUSYF|1;I2C1->TIMINGR^=1;step(25020);
 assert(!enc.configured&&enc.recovering&&!enc.bus_ok&&!enc.angle_ok);
 I2C1->CR2&=~I2C_CR2_START;step(25030);assert(I2C1->CR2&I2C_CR2_STOP);
 I2C1->ISR.value=EC_STOPF|1;step(25040);assert(!enc.recovering&&!(I2C1->CR1&1));
 assert(!memcmp(frozen,fault_record[1],sizeof(frozen)));
 uint32_t health[14];mic_encoder_health_snapshot(health);assert(health[0]==1&&health[6]==1&&health[8]==2&&health[9]==0&&health[10]==1);
 // RXNE+NACK+STOP is invalidated; NACK clear must not clear STOP before terminal.
 mic_encoder_init();test_tick=5;start(30000);I2C1->ISR.value=EC_NACKF|EC_STOPF|EC_RXNE;step(30030);
 assert(enc.errors==1&&enc.reads==0&&!enc.bus_ok&&!enc.recovering&&enc.clean_stops==1);
 std::puts("{\"passed\":true,\"full_production_driver\":true,\"w1c_mmio\":true,\"terminal_captured_before_park\":true,\"frozen_record_preserved\":true}");
}
