
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <cstdint>
#include "boot_wire.h"
#include "repeat_state.h"
static const uint32_t MIC_NUCLEO_FW_BUILD_ID=2026111810U;
enum {HAL_OK=0,UNO_TX_TAG_DIAG=0};
struct{uint32_t head,tail,hard_error;}mic_uart_tx;
struct{bool command_enabled;}uno_link;
static bool MOE,mic_last_control_reply_safe_off,records;static void*TIM1;
static bool LL_TIM_IsEnabledAllOutputs(void*){return MOE;}
static rp_state mic_repeat_state;
static struct{uint32_t magic;}mic_after_clear_break;
enum{MIC_BREAK_MAGIC=0x1234};static bool mic_repeat_wave_ready;
static mb_record boot;static mb_receiver received;static uint32_t now,origin;
static uint8_t last_repeat[43],queue[4][43];static uint32_t repeat_seen;
static double us,done_at,boot_last=-1,repeat_last=-1,max_boot,max_repeat;
static unsigned full_errors,boot_count,repeat_count,control_count,max_pending;
static void mic_boot_packet(uint8_t*p,uint32_t tick){mb_packet(p,&boot,tick);}
static int uno_tx_submit(const uint8_t*p,uint8_t){
 unsigned pending=mic_uart_tx.head-mic_uart_tx.tail;
 if(pending>=4){++full_errors;return 1;}
 memcpy(queue[mic_uart_tx.head&3],p,43);++mic_uart_tx.head;
 if(++pending>max_pending)max_pending=pending;
 if(pending==1)done_at=us+430e6/921600.;return 0;
}
static void drain(){while(mic_uart_tx.tail!=mic_uart_tx.head&&done_at<=us){
 auto*p=queue[mic_uart_tx.tail&3];uint32_t tick=origin+(uint32_t)(done_at/1000);
 if(p[2]==MB_WIRE){assert(mb_receive(&received,p,MIC_NUCLEO_FW_BUILD_ID,true,tick));
  if(boot_last>=0&&done_at-boot_last>max_boot)max_boot=done_at-boot_last;boot_last=done_at;++boot_count;}
 if(p[2]==RPM_VERSION){assert(rpm_valid(p,MIC_NUCLEO_FW_BUILD_ID,true));memcpy(last_repeat,p,43);repeat_seen=tick;
  if(repeat_last>=0&&done_at-repeat_last>max_repeat)max_repeat=done_at-repeat_last;repeat_last=done_at;++repeat_count;}
 if(p[2]==0x80){mic_last_control_reply_safe_off=true;++control_count;}
 ++mic_uart_tx.tail;done_at+=430e6/921600.;}}
static void generic(uint32_t tick,unsigned type,uint32_t period,unsigned index,bool enabled=true,unsigned count=1){
 static uint32_t last[9];if(!enabled||MOE||mic_uart_tx.hard_error||(uint32_t)(tick-last[index])<period||mic_uart_tx.head-mic_uart_tx.tail>1)return;
 uint8_t p[43]={};p[2]=(uint8_t)type;for(unsigned i=0;i<count;++i)assert(uno_tx_submit(p,0)==HAL_OK);last[index]=tick;
}
static void mic_send_current_page(uint32_t n){generic(n,0xd2,200,0);}
static void mic_send_research_page(uint32_t n){generic(n,0xe4,100,1,true,2);}
static void mic_send_observer_page(uint32_t n){generic(n,0xea,20,2,records);}
static void mic_send_break_page(uint32_t n){generic(n,0xd1,200,3);}
static void mic_send_peak_page(uint32_t n){generic(n,0xd8,100,4,records);}
static void mic_send_noise_page(uint32_t n){generic(n,0xe7,20,5,records);}
static void mic_send_identification(uint32_t n){generic(n,0xe5,records?20:250,6);}
static void mic_send_clear_page(uint32_t n){generic(n,0xee,500,7,records);}

static void mic_send_repeat_meta(uint32_t now_ms) {
  static uint32_t last;
  if(LL_TIM_IsEnabledAllOutputs(TIM1)||uno_link.command_enabled||
     !mic_last_control_reply_safe_off||(uint32_t)(now_ms-last)<500U||
     (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME],boot[UV3_FRAME];mic_boot_packet(boot,now_ms);
  const uint8_t flags=(mic_after_clear_break.magic==MIC_BREAK_MAGIC?1U:0U)|
    (mic_repeat_wave_ready?2U:0U);
  rpm_packet(packet,&mic_repeat_state,flags,rpm_u32(boot+30));
  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK)last=now_ms;
}
static void mic_send_boot_page(uint32_t now_ms){
  static uint32_t last_ms;
  if(LL_TIM_IsEnabledAllOutputs(TIM1)||uno_link.command_enabled||
     !mic_last_control_reply_safe_off||(uint32_t)(now_ms-last_ms)<500U||
     (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME];mic_boot_packet(packet,now_ms);
  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK)last_ms=now_ms;
}
static void mic_send_bulk_page(uint32_t now_ms){
 static uint8_t next;static uint32_t last_bulk_ms;
 if(LL_TIM_IsEnabledAllOutputs(TIM1)||uno_link.command_enabled||
    !mic_last_control_reply_safe_off||mic_uart_tx.hard_error)return;
 /* Ordinary telemetry has deadlines too. Retry from foreground as soon as
  * TX has room, not only immediately after the50ms control reply (which may
  * find the queue occupied). Keep the original200ms slot schedule/sequence,
  *100ms research schedule and all receiver freshness/CRC/zero guards. */
 mic_send_current_page(now_ms);
 mic_send_research_page(now_ms);
 /* OFF bulk remains secondary, one frame per invocation and <=100fps.
  * Two slots stay reserved for control. Timers wrap with unsigned arithmetic. */
 if((uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||
    (uint32_t)(now_ms-last_bulk_ms)<10U)return;
 for(unsigned attempt=0;attempt<8U;++attempt){
  unsigned slot=(next+attempt)%8U;uint32_t before=mic_uart_tx.head;
  switch(slot){
   case 0:mic_send_repeat_meta(now_ms);break;
   case 1:mic_send_boot_page(now_ms);break;
   case 2:mic_send_observer_page(now_ms);break;
   case 3:mic_send_break_page(now_ms);break;
   case 4:mic_send_peak_page(now_ms);break;
   case 5:mic_send_noise_page(now_ms);break;
   case 6:mic_send_identification(now_ms);break;
   case 7:mic_send_clear_page(now_ms);break;
  }
  if(mic_uart_tx.head!=before){next=(uint8_t)((slot+1U)%8U);last_bulk_ms=now_ms;return;}
 }
}
int main(int argc,char**argv){
 assert(argc==4);records=atoi(argv[1])!=0;origin=(uint32_t)strtoul(argv[2],0,0);unsigned delay=atoi(argv[3]);
 boot={MB_MAGIC,MIC_NUCLEO_FW_BUILD_ID,1,0x14000000,0,MB_CURRENT_CLEARED,0,0};boot.crc=mb_crc(&boot);
 // Exact symptom: valid first page then an ADC-stack overwrite. TTL is NOT relaxed.
 uint8_t packet[43];mb_packet(packet,&boot,520);mb_receiver bad={};assert(mb_receive(&bad,packet,MIC_NUCLEO_FW_BUILD_ID,true,520));
 mb_record corrupted=boot;corrupted.magic=0x432e;mb_packet(packet,&corrupted,1020);
 assert(!mb_receive(&bad,packet,MIC_NUCLEO_FW_BUILD_ID,true,1020));assert(!mb_fresh(&bad,MIC_NUCLEO_FW_BUILD_ID,true,2500));
 uint32_t command_ms=origin;
 for(us=0;us<30e6;us+=delay){
  now=origin+(uint32_t)(us/1000);drain();
  if((uint32_t)(now-command_ms)>=50){uint8_t p[43]={};p[2]=0x80;assert(uno_tx_submit(p,2)==HAL_OK);command_ms=now;}
  mic_send_bulk_page(now);
  if(us>3e6){assert(mb_fresh(&received,MIC_NUCLEO_FW_BUILD_ID,true,now));assert((uint32_t)(now-repeat_seen)<1500);
   assert(rpm_u32(last_repeat+34)==mb_u32(received.packet+30));}
 }
 assert(boot_count>30&&repeat_count>30&&control_count>500&&!full_errors&&max_pending<=4);
 assert(max_boot<1500000&&max_repeat<1500000);
 unsigned b=boot_count,r=repeat_count;MOE=true;for(unsigned i=0;i<2000;++i){us+=1000;now=origin+(uint32_t)(us/1000);drain();mic_send_bulk_page(now);}
 assert(boot_count<=b+1&&repeat_count<=r+1);assert(!mb_fresh(&received,MIC_NUCLEO_FW_BUILD_ID,true,now));
 printf("{\"passed\":true,\"boot_pages\":%u,\"repeat_pages\":%u,\"max_boot_gap_us\":%.1f,\"max_repeat_gap_us\":%.1f,\"queue_full\":%u,\"TTL_unchanged\":true,\"old_corruption_negative_control\":true}\n",b,r,max_boot,max_repeat,full_errors);
}
