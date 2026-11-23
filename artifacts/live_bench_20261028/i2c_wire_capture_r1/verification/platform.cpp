#include "nucleo_encoder.c"
#include "nucleo_i2c_wire.c"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>
static uint32_t us;
static void step(uint32_t gap=10){us+=gap;test_tick=us/1000;test_dwt.CYCCNT=us*170;mic_encoder_poll();}
static void begin(){
 for(unsigned n=0;enc.state!=1&&n<4000;n++){step();assert(enc.configured);}
 assert(enc.state==1&&enc.pe_on&&(I2C1->CR1&1));I2C1->CR2&=~I2C_CR2_START;
}
static void send_pointer(){I2C1->ISR.value=EC_TXIS|EC_BUSYF;step();assert(enc.state==2&&I2C1->TXDR==0x0b);}
static void normal(){
 begin();send_pointer();I2C1->ISR.value=EC_TC|EC_BUSYF;step();assert(enc.state==3);I2C1->CR2&=~I2C_CR2_START;
 for(unsigned x:{0x20U,7U,99U}){I2C1->RXDR=x;I2C1->ISR.value=EC_RXNE|EC_BUSYF;step();}
 I2C1->ISR.value=EC_STOPF;step();
 assert(enc.bus_ok&&enc.angle_ok&&enc.raw==1891&&enc.pe_on&&config_ok());
 assert(I2C1->CR1==0x201&&I2C1->CR2==0&&I2C1->TIMINGR==MIC_ENC_TIMING);
 step();assert(enc.configured&&config_ok()); // Includes healthy idle, not just active state.
}
int main(int argc,char**argv){
 const char*mode=argc>1?argv[1]:"normal";
 test_rcc.CR=RCC_CR_HSIRDY;test_gpio.IDR=0x300;test_i2c.ISR.value=1;
 mic_i2c_wire_init();DMA2->ISR=0x2000;DMA2_Channel4->CNDTR=4090;
 mic_encoder_init();assert(enc.configured&&!enc.pe_on&&config_ok());
 unsigned disabled_at_init=mock_pe_disables;
 if(!strcmp(mode,"missing_hook")){
  io.completed=nullptr;step(5000);assert(!enc.configured&&enc.cause==EC_SETUP&&!enc.reads&&!mock_pe_enables);
  puts("{\"passed\":true,\"mode\":\"missing_hook\"}");return 0;
 }
 normal();
 if(!strcmp(mode,"lost_pe")){
  I2C1->CR1&=~1U;step();assert(!enc.configured&&enc.cause==EC_SETUP&&!enc.pe_on&&enc.errors==1);
  assert(fault_ready==1&&((fault_record[0][4]&255U)==EC_SETUP));
  puts("{\"passed\":true,\"mode\":\"lost_pe\"}");return 0;
 }
 for(unsigned n=1;n<200;n++){TIM1->BDTR=n&1?TIM_BDTR_MOE:0;normal();}
 assert(enc.reads==200&&enc.errors==0&&enc.resets==0&&!fault_ready);
 assert(mock_pe_enables==1&&mock_pe_disables==disabled_at_init&&!mock_gpio_writes);
 uint8_t measurement[43];mic_encoder_packet(measurement,EW_PEER);ew_receiver rx{};
 assert(measurement[37]==1&&ew_receive(&rx,measurement,EW_PEER,true,HAL_GetTick()));
 assert((measurement[3]&11U)==11U); // PE1 while idle must not hide a fresh valid angle.
 for(unsigned n=0;n<43;n++){
  uint8_t bad[43];memcpy(bad,measurement,43);bad[n]^=1;ew_receiver corrupt{};
  assert(!ew_receive(&corrupt,bad,EW_PEER,true,HAL_GetTick()));
 }
 // A real failure after healthy retained-PE reads still freezes the PE1 state
 // and parks the peripheral. No NACK is promoted to a valid measurement.
 begin();send_pointer();I2C1->ISR.value=EC_NACKF|EC_STOPF;step();
 assert(enc.errors==1&&!enc.bus_ok&&!enc.angle_ok&&!enc.speed_ok&&!enc.pe_on);
 assert(!(I2C1->CR1&1)&&config_ok()&&mock_pe_disables==disabled_at_init+1);
 mic_encoder_packet(measurement,EW_PEER);assert(!(measurement[3]&7U)&&measurement[37]==0);
 assert(wire.state==WC_FROZEN&&wire.parent==fault_record[1]);
 assert(fault_ready==3&&fault_record[0][36]==0x201&&fault_record[0][35]==EC_STOPF);
 step(10);step(10);assert(release_probe[0].complete);
 uint32_t frozen[40];memcpy(frozen,fault_record[0],sizeof(frozen));sr_probe probe=release_probe[0];
 normal();assert(enc.reads==201&&enc.errors==1&&mock_pe_enables==2);
 assert(!memcmp(frozen,fault_record[0],sizeof(frozen))&&!memcmp(&probe,&release_probe[0],sizeof(probe)));
 // Missing STOP: bounded request, then forced PE reset, preserving first capture.
 begin();send_pointer();I2C1->ISR.value=EC_NACKF|EC_BUSYF;step();assert(enc.recovering&&enc.pe_on);
 step(100);assert(I2C1->CR2&I2C_CR2_STOP);step(410);
 assert(!enc.recovering&&!enc.pe_on&&!(I2C1->CR1&1)&&enc.resets==1&&config_ok());
 assert(enc.errors==2&&enc.reads==201&&!memcmp(frozen,fault_record[0],sizeof(frozen)));
 assert(!memcmp(&probe,&release_probe[0],sizeof(probe))&&!mock_gpio_writes);
 TIM1->BDTR=0;mic_i2c_wire_service(false);assert(wire.state==WC_READY);
 assert(wire.header[4]==uv3_crc32c((const uint8_t*)fault_record[1],160));
 printf("{\"passed\":true,\"mode\":\"normal\",\"healthy_reads_before_fault\":200,\"healthy_pe_enables\":1,\"healthy_pe_disables\":0,\"clean_and_forced_cleanup_verified\":true,\"first_records_frozen\":true}\n");
}
