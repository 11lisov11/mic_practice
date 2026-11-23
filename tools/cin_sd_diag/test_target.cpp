#include <cassert>
#include <cstdio>
#include <cstring>
#include "stub_adc.h"
#include "native.inc"
static void setup(){
 memset(&cin_diag,0,sizeof(cin_diag));adc2={};gpioa={};tick=0;dwt={};
 adc2.CR=ADC_CR_ADEN;starts=stops=0;cin_diag_init();
 assert(gpio_init_pin==GPIO_PIN_11&&gpio_init_mode==GPIO_MODE_ANALOG&&gpio_init_pull==GPIO_NOPULL);
}
static void begin(uint32_t now=5000){cin_diag_service(now,true,true);assert(cin_diag.pending);}
static void eoc(uint16_t raw,uint32_t now,uint32_t cycles=100){
 adc2.CR&=~2U;adc2.DR=(uint32_t)raw<<4;adc2.ISR|=1U;dwt.CYCCNT+=cycles;cin_diag_service(now,true,true);
}
int main(){
 setup();cin_diag_service(4999,true,true);assert(!starts);
 cin_diag_service(5000,false,true);cin_diag_service(5000,true,false);assert(!starts);
 gpioa.IDR=GPIO_PIN_6;begin();assert(starts==1);cin_diag_service(5000,true,true);assert(starts==1);
 eoc(0x123,5000);assert(cin_diag.last.raw==0x123&&cin_diag.last.reason==CD_OK&&cin_diag.last.flags==7);
 uint8_t p[UV3_FRAME];cd_packet(p,&cin_diag.last,2026103102U);assert(cd_decode(p,2026103102U));
 cd_receiver receiver={};assert(cd_receive(&receiver,p,2026103102U,true,10));
 assert(cd_fresh(&receiver,2026103102U,true,509));assert(!cd_fresh(&receiver,2026103102U,true,510));
 assert(!cd_receive(&receiver,p,2026103102U,true,11)); // replay
 assert(!cd_fresh(&receiver,2026103102U,false,12));
 for(unsigned byte=0;byte<UV3_FRAME;++byte)for(unsigned bit=0;bit<8;++bit){
  uint8_t bad[UV3_FRAME];memcpy(bad,p,sizeof(bad));bad[byte]^=(uint8_t)(1U<<bit);
  assert(!cd_decode(bad,2026103102U));
 }
 assert(!cd_decode(p,2026103014U));assert(!cd_receive(&receiver,p,2026103102U,false,12));
 cd_record wrong=cin_diag.last;wrong.flags=8;cd_packet(p,&wrong,2026103102U);assert(!cd_decode(p,2026103102U));
 wrong=cin_diag.last;wrong.raw=4096;cd_packet(p,&wrong,2026103102U);assert(!cd_decode(p,2026103102U));
 wrong=cin_diag.last;wrong.vref_mv=3300;cd_packet(p,&wrong,2026103102U);assert(!cd_decode(p,2026103102U));
 wrong=cin_diag.last;wrong.end_ms=wrong.start_ms+2;cd_packet(p,&wrong,2026103102U);assert(!cd_decode(p,2026103102U));
 setup();begin();gpioa.IDR=GPIO_PIN_6;eoc(635,5001);assert(cin_diag.last.flags==(CD_VALID|CD_SD_AFTER));
 cin_diag_service(5100,true,true);assert(starts==1);begin(5101);assert(starts==2);eoc(0,5101);
 setup();begin();adc2.ISR|=1U;adc2.DR=0x7fff;cin_diag_service(5002,true,true);
 assert(cin_diag.last.reason==CD_TIMEOUT&&cin_diag.last.timeouts==1&&!(cin_diag.last.flags&CD_VALID)&&stops==1);
 // Severe main-loop latency remains visible as an invalid record, not a false fresh sample.
 setup();begin();cin_diag_service(6000,true,true);cd_packet(p,&cin_diag.last,2026103102U);
 assert(cin_diag.last.reason==CD_TIMEOUT&&cd_decode(p,2026103102U));
 setup();begin();adc2.ISR|=4U;cin_diag_service(5000,true,true);assert(cin_diag.last.reason==CD_OVERRUN);
 setup();begin();cin_diag_service(5000,false,true);assert(cin_diag.last.reason==CD_UNSAFE&&stops==1);
 setup();adc2.CR|=2U;cin_diag_service(5000,true,true);assert(!starts&&!stops&&cin_diag.last.reason==CD_BUSY);
 setup();adc2.CFGR|=ADC_CFGR_DMAEN;cin_diag_service(5000,true,true);assert(!starts&&cin_diag.last.reason==CD_CONFIG);
 setup();adc2.CR=0;cin_diag_service(5000,true,true);assert(!starts&&cin_diag.last.reason==CD_CONFIG);
 setup();adc2.SQR1=13U<<ADC_SQR1_SQ1_Pos;cin_diag_service(5000,true,true);assert(!starts&&cin_diag.last.reason==CD_CONFIG);
 setup();tick=0xfffffff0U;cin_diag_init();cin_diag_service(4983,true,true);assert(!starts);
 begin(4984);eoc(4095,4984);assert(cin_diag.last.raw==4095);
 // Sender refuses RUN, stale OFF publication, occupied queues and hard TX faults.
 setup();begin();eoc(12,5000);uint32_t seq=cin_diag.last.sequence;
 tim_moe=true;mic_send_cin_page(5000);assert(!submits);tim_moe=false;
 mic_last_control_reply_safe_off=false;mic_send_cin_page(5000);assert(!submits);
 mic_last_control_reply_safe_off=true;mic_uart_tx.head=2;mic_send_cin_page(5000);assert(!submits);
 mic_uart_tx.head=0;mic_uart_tx.hard_error=1;mic_send_cin_page(5000);assert(!submits);
 mic_uart_tx.hard_error=0;mic_send_cin_page(5000);assert(submits==1&&last_seq==seq);
 mic_send_cin_page(5000);assert(submits==1);
 printf("PASS: actual OFF acquisition, 344 bit corruptions, stale/timeout/OVR/busy/guard and sender cases\n");
}
