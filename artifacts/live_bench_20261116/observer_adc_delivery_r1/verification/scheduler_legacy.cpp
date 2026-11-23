
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>
enum{UV3_FRAME=43,UNO_TX_TAG_DIAG=0,HAL_OK=0};
static const unsigned MIC_NUCLEO_FW_BUILD_ID=2026111602;
static struct {unsigned head,tail,hard_error;} mic_uart_tx;
static struct {bool command_enabled;} uno_link;
static bool mic_last_control_reply_safe_off=true,MOE;
static void* TIM1;
static bool LL_TIM_IsEnabledAllOutputs(void*){return MOE;}
static double now_us,next_done;
static unsigned delivered[10],page_mask[2][64],first_complete[2],full_errors;
static uint8_t queue[4][43];
static void drain(){while(mic_uart_tx.head!=mic_uart_tx.tail&&next_done<=now_us){
 auto*p=queue[mic_uart_tx.tail&3];unsigned type=p[2];++delivered[type];
 if(type==2||type==4){unsigned row=type==2?0:1;page_mask[row][p[5]]=1;
  unsigned n=0;for(unsigned i=0;i<(row?35:62);++i)n+=page_mask[row][i];
  if(n==(row?35U:62U)&&!first_complete[row])first_complete[row]=(unsigned)now_us;}
 ++mic_uart_tx.tail;next_done+=430000000.0/115200;}}
static int uno_tx_submit(const uint8_t*p,unsigned){
 if(mic_uart_tx.head-mic_uart_tx.tail>=4){++full_errors;return 1;}
 bool empty=mic_uart_tx.head==mic_uart_tx.tail;
 memcpy(queue[mic_uart_tx.head&3],p,43);++mic_uart_tx.head;
 if(empty)next_done=now_us+430000000.0/115200;
 return 0;}
static int ma_observer_trace_packet(uint8_t*p,unsigned,unsigned page){memset(p,0,43);p[2]=2;p[5]=page;return 1;}
static int mic_current_peak_packet(uint8_t*p,unsigned page,unsigned){memset(p,0,43);p[2]=4;p[5]=page;return 1;}
static unsigned last[10];
static void other(unsigned id,unsigned now,unsigned period,bool loose=false){
 if(MOE||uno_link.command_enabled||mic_uart_tx.hard_error||now-last[id]<period)return;
 if(!loose&&mic_uart_tx.head-mic_uart_tx.tail>1)return;
 uint8_t p[43]={};p[2]=id;if(uno_tx_submit(p,0)==HAL_OK)last[id]=now;}
static void mic_send_repeat_meta(unsigned now){other(0,now,500);}
static void mic_send_boot_page(unsigned now){other(1,now,500);}
static void mic_send_break_page(unsigned now){other(3,now,200,true);}
static void mic_send_noise_page(unsigned now){other(5,now,20);}
static void mic_send_identification(unsigned now){other(6,now,250);}
static void control(unsigned now){
 uint8_t p[43]={};p[2]=7;assert(!uno_tx_submit(p,0));
 if(now-last[8]>=100&&mic_uart_tx.head-mic_uart_tx.tail<=1){
  p[2]=8;assert(!uno_tx_submit(p,0));assert(!uno_tx_submit(p,0));last[8]=now;}
 if(now-last[9]>=200&&mic_uart_tx.head-mic_uart_tx.tail<=1){p[2]=9;assert(!uno_tx_submit(p,0));last[9]=now;}
}
static void mic_send_observer_page(uint32_t now_ms){
  static uint32_t last_ms;static unsigned page;
  if(LL_TIM_IsEnabledAllOutputs(TIM1)||uno_link.command_enabled||!mic_last_control_reply_safe_off||
      (uint32_t)(now_ms-last_ms)<20U||(uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME];
  if(ma_observer_trace_packet(packet,MIC_NUCLEO_FW_BUILD_ID,page)&&uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK){
    page=(page+1U)%62U;last_ms=now_ms;
  }
}
static void mic_send_peak_page(uint32_t now_ms) {
  static uint32_t last_ms;static uint8_t page;
  if(LL_TIM_IsEnabledAllOutputs(TIM1) || (uint32_t)(now_ms-last_ms)<100U ||
      (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U || mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME];
  if(mic_current_peak_packet(packet,page,MIC_NUCLEO_FW_BUILD_ID) &&
      uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK){last_ms=now_ms;page=(uint8_t)((page+1U)%35U);}
}
int main(int argc,char**argv){
 unsigned cadence=argc>1?(unsigned)atoi(argv[1]):50000,phase=argc>2?(unsigned)atoi(argv[2]):0;
 for(unsigned us=0;us<8000000;us+=100){now_us=us;drain();unsigned ms=us/1000;
  if((us+phase)%cadence==0){control(ms);mic_send_repeat_meta(ms);mic_send_boot_page(ms);mic_send_observer_page(ms);mic_send_break_page(ms);mic_send_peak_page(ms);mic_send_noise_page(ms);mic_send_identification(ms);}
  
 }
 printf("{\"observer_pages_delivered\":%u,\"ADC_pages_delivered\":%u,\"observer_complete_us\":%u,\"ADC_complete_us\":%u,\"control_replies\":%u,\"queue_full\":%u}\n",delivered[2],delivered[4],first_complete[0],first_complete[1],delivered[7],full_errors);
 assert(delivered[2]>0&&delivered[4]==0);
 // Gate independent of the records' readiness.
 MOE=true;auto h=mic_uart_tx.head;mic_send_observer_page(100000);mic_send_peak_page(100000); assert(mic_uart_tx.head==h);
}
