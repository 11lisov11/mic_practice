#include "nucleo_i2c_wire.c"
#include "peer_epoch.h"
#include "pulse_core.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>
static bool parent_ready;
bool mic_encoder_pwm_fault_ready(void){return parent_ready;}
static unsigned checks;
#define CHECK(x) do {assert(x);++checks;} while(0)
static void frame(const uint8_t*raw,unsigned page,uint8_t*p){
  wc_frame(p,page,uv3_crc32c(raw,WC_BYTES));
  unsigned n=WC_BYTES-page*24U;if(n>24)n=24;memcpy(p+14,raw+page*24,n);uv3_seal(p);
}
static void receive_all(wc_receiver*r,const uint8_t*raw){
  uint8_t p[43];for(unsigned page=0;page<WC_PAGES;page++){frame(raw,page,p);CHECK(wc_receive(r,p,WC_PEER,true));}
}
int main(int argc,char**argv){
  (void)SystemCoreClock;(void)test_debug;(void)test_rcc;
  const char*mode=argc>1?argv[1]:"normal";
  if(!strcmp(mode,"clock")){mock_wire_hz=160000000U;mic_i2c_wire_init();CHECK(wire.state==WC_ERROR);CHECK(!(DMA2_Channel4->CCR&1));}
  else if(!strcmp(mode,"conflict")){DMA2_Channel4->CCR=1;mic_i2c_wire_init();CHECK(wire.state==WC_ERROR);CHECK(DMA2_Channel4->CCR==1);}
  else if(!strcmp(mode,"dma_fail")){mock_dma_fail=true;mic_i2c_wire_init();CHECK(wire.state==WC_ERROR);CHECK(!(TIM4->CR1&1));}
  else {
    mic_i2c_wire_init();CHECK(wire.state==WC_ARMED);CHECK(TIM4->ARR==19);CHECK(TIM4->DIER==256);
    CHECK(mock_dma_init.Init.Request==71);CHECK(mock_dma_init.Init.PeriphDataAlignment==512);
    CHECK(mock_dma_init.Init.MemDataAlignment==1024);CHECK(!(DMA2_Channel4->CCR&14));
    for(unsigned i=0;i<WC_SAMPLES;i++)wire_ring[i]=(uint16_t)((i%4)<<8|0xfcff);
    uint32_t parent[40]={0};parent[0]=0x31434649U;parent[1]=WC_PEER;
    parent[3]=10000;parent[4]=2;parent[16]=32768;parent[32]=170000000U;
    mic_i2c_wire_freeze(parent,10000);CHECK(wire.state==WC_ARMED); // No PWM.
    mic_i2c_wire_request=0x57495245;mic_i2c_wire_service(false);CHECK(wire.state==WC_ARMED);
    if(!strcmp(mode,"early")){
      DMA2_Channel4->CNDTR=WC_SAMPLES-13;DWT->CYCCNT=11000;
      mic_i2c_wire_request=0x57495245;mic_i2c_wire_service(true);
      CHECK(wire.state==WC_READY);CHECK(wire.header[7]==13);CHECK(wire.header[11]==WC_MANUAL);
      CHECK(wire_byte(48)==0xe4);CHECK(wire_byte(51)==0); // sample12=0, then padding.
      for(unsigned i=52;i<WC_BYTES;i++)CHECK(wire_byte(i)==0);
      mic_i2c_wire_request=0x41524d57;mic_i2c_wire_service(true);CHECK(wire.state==WC_READY);
    }else{
      TIM1->BDTR=32768;DMA2->ISR=0x2000;DMA2_Channel4->CNDTR=WC_SAMPLES-7;DWT->CYCCNT=11000;
      mic_i2c_wire_freeze(parent,10000);CHECK(wire.state==WC_FROZEN);CHECK(wire.end==7);
      CHECK(wire.header[7]==WC_SAMPLES);CHECK(wire.header[11]==(WC_FULL|WC_MOE));
      CHECK(!(TIM4->CR1&1));CHECK(!(TIM4->DIER&256));CHECK(!(DMA2_Channel4->CCR&1));
      CHECK(wire_byte(48)==0x93); // samples7,8,9,10 =3,0,1,2.
      mic_i2c_wire_service(false);CHECK(wire.state==WC_FROZEN);
      parent[39]=12345;TIM1->BDTR=0;mic_i2c_wire_service(false);CHECK(wire.state==WC_FROZEN);
      parent_ready=true;mic_i2c_wire_service(false);CHECK(wire.state==WC_READY);
      CHECK(wire.header[4]==uv3_crc32c((uint8_t*)parent,160));
      uint8_t raw[WC_BYTES],p[43];for(unsigned i=0;i<WC_BYTES;i++)raw[i]=wire_byte(i);
      CHECK(uv3_crc32c(raw,WC_BYTES)==wire.crc);
      wc_receiver r={};receive_all(&r,raw);CHECK(r.valid);CHECK(!memcmp(r.bytes,raw,WC_BYTES));
      // Every fragment independently rejects every one-byte corruption.
      for(unsigned page=0;page<WC_PAGES;page++){
        frame(raw,page,p);
        for(unsigned n=0;n<43;n++){uint8_t bad[43];memcpy(bad,p,43);bad[n]^=1;wc_receiver fresh={};CHECK(!wc_receive(&fresh,bad,WC_PEER,true));}
        wc_receiver fresh={};CHECK(!wc_receive(&fresh,p,WC_PEER,false));CHECK(!wc_receive(&fresh,p,WC_PEER-1,true));
      }
      // Record CRC catches transport-valid altered data; published data cannot change.
      frame(raw,0,p);p[14]^=1;uv3_seal(p);CHECK(!wc_receive(&r,p,WC_PEER,true));CHECK(!memcmp(r.bytes,raw,WC_BYTES));
      wc_receiver broken={};for(unsigned page=0;page<WC_PAGES;page++){
        frame(raw,page,p);if(page==0){p[14]^=1;uv3_seal(p);}
        bool ok=wc_receive(&broken,p,WC_PEER,true);if(page==44)CHECK(!ok);
      }CHECK(!broken.valid);
      // Last-page padding, wrong peer, format, and malformed header re-sealed CRC.
      frame(raw,44,p);p[30]=1;uv3_seal(p);wc_receiver fresh={};CHECK(!wc_receive(&fresh,p,WC_PEER,true));
      for(unsigned n=0;n<48;n++){uint8_t bad[WC_BYTES];memcpy(bad,raw,WC_BYTES);bad[n]^=0x80;
        if(n<16||(n>=20&&n<32)||n==44)CHECK(!wc_header_valid(bad));}
      mic_i2c_wire_request=0x41524d57;mic_i2c_wire_service(true);CHECK(wire.state==WC_READY);
      mic_i2c_wire_request=0x57495245;mic_i2c_wire_service(true);CHECK(wire.state==WC_READY);
      mic_i2c_wire_freeze(parent,999);CHECK(wire.header[9]==10000);
      // Epoch rollover archives complete raw records, invalidates current slots,
      // and never overwrites retained records with an empty generation.
      pe_records records={};pe_history h={};records.wire=r;records.fault.slot[0].valid=true;
      records.fault.slot[0].bytes[0]=42;pe_reset(&h,&records);
      CHECK(h.previous_valid&&h.epoch==1&&h.previous_epoch==0);CHECK(h.previous.fault.slot[0].bytes[0]==42);
      CHECK(!pe_nonempty(&records));CHECK(!memcmp(h.previous.wire.bytes,raw,WC_BYTES));
      pe_reset(&h,&records);CHECK(h.epoch==2&&h.previous_epoch==0&&h.previous_valid);
      FILE*f=fopen("wire_fixture.bin","wb");CHECK(f);CHECK(fwrite(raw,1,sizeof(raw),f)==sizeof(raw));fclose(f);
      FILE*g=fopen("wire_parent.bin","wb");CHECK(g);CHECK(fwrite(parent,1,sizeof(parent),g)==sizeof(parent));fclose(g);
    }
    // Exhaustive proof of the SD storage-only change for every GPIO IDR word.
    for(unsigned word=0;word<65536;word++)CHECK(bp_state(word)==bp_state(word&255U));
  }
  printf("{\"passed\":true,\"mode\":\"%s\",\"checks\":%u}\n",mode,checks);
}
