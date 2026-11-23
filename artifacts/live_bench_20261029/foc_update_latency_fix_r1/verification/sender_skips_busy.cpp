
#include <cassert>
#include <cstdint>
enum{UV3_FRAME=43,HAL_OK=0,UNO_TX_TAG_DIAG=1,MIC_NUCLEO_FW_BUILD_ID=2026103004};
static struct{unsigned head,tail,hard_error;}mic_uart_tx;
static int success,calls,tx;
static int mic_zero_packet(uint8_t*,unsigned){return 0;}
static int mic_current_packet(uint8_t*,uint8_t,unsigned){++calls;return success;}
static int uno_tx_submit(uint8_t*,unsigned){++tx;return 0;}
static void mic_send_current_page(uint32_t now_ms) {
  static uint32_t last_ms;
  static uint8_t slot;
  if((uint32_t)(now_ms-last_ms)<200U ||
      (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U || mic_uart_tx.hard_error) return;
  uint8_t packet[UV3_FRAME];
  if(slot!=4U || !mic_zero_packet(packet,MIC_NUCLEO_FW_BUILD_ID)) {
    if(!mic_current_packet(packet,(uint8_t)(slot==0U?1U:slot==2U?2U:0U),MIC_NUCLEO_FW_BUILD_ID))return;
  }
  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK) {
    last_ms=now_ms;slot=(uint8_t)((slot+1U)%5U);
  }
}
int main(){mic_send_current_page(201);assert(calls==1&&tx==0);
success=1;mic_send_current_page(202);assert(calls==2&&tx==1);
mic_send_current_page(203);assert(calls==2&&tx==1);}
