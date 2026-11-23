
#include <cassert>
#include <cstdio>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include "uart_v3_transport.h"
#include "current_wire.h"
#define __DMB() ((void)0)
#include "current_snapshot.h"
using std::isfinite;
#define ADC_REFERENCE_VOLTAGE 3.3
#define RSHUNT .04
#define AMPLIFICATION_GAIN 2.1
enum{HAL_OK=0,UNO_TX_TAG_DIAG=0};
static const unsigned MIC_NUCLEO_FW_BUILD_ID=2026111604;
static cm_core state;static volatile unsigned state_sequence;static unsigned packets;
static double now_us,next_done;static uint32_t origin_ms;
static uint32_t HAL_GetTick(){return origin_ms+(uint32_t)(now_us/1000);}
static struct{uint32_t head,tail,hard_error;} mic_uart_tx;
static struct{bool command_enabled;} uno_link;
static bool MOE,mic_last_control_reply_safe_off=false,records;
static void*TIM1;static bool LL_TIM_IsEnabledAllOutputs(void*){return MOE;}
static uint8_t queue[4][43];static double queued_at[4];
static ct_receiver receiver;
static uint32_t full_errors,controls,bulk_count,max_pending;
static double max_control_us,last_control_us=-1e9;
static double last_normal[3]={-1,-1,-1},max_gap[3];
static unsigned mask[2][62],first_complete[2];
static FILE*csv;
static void drain(){while(mic_uart_tx.head!=mic_uart_tx.tail&&next_done<=now_us){
 auto*frame=queue[mic_uart_tx.tail&3];unsigned type=frame[2];
 if(type==0x80){++controls;double age=now_us-queued_at[mic_uart_tx.tail&3];if(age>max_control_us)max_control_us=age;last_control_us=now_us;mic_last_control_reply_safe_off=true;}
 if(type==CT_SUMMARY||type==CT_DETAIL||type==CT_QUALITY){
  assert(ct_receive(&receiver,frame,MIC_NUCLEO_FW_BUILD_ID,now_us-last_control_us<300000,HAL_GetTick()));
  unsigned slot=type==CT_SUMMARY?0:type==CT_DETAIL?1:2;
  if(last_normal[slot]>=0){double gap=now_us-last_normal[slot];if(gap>max_gap[slot])max_gap[slot]=gap;}
  last_normal[slot]=now_us;
 }
 if(type==0xea||type==0xd8){unsigned row=type==0xea?0:1;mask[row][frame[5]]=1;unsigned n=0;
  for(unsigned i=0;i<(row?35U:62U);++i)n+=mask[row][i];
  if(n==(row?35U:62U)&&!first_complete[row])first_complete[row]=(unsigned)now_us;}
 ++mic_uart_tx.tail;next_done+=430000000.0/115200;
}}
static int uno_tx_submit(const uint8_t*frame,uint8_t){
 unsigned pending=mic_uart_tx.head-mic_uart_tx.tail;
 if(pending>=4){++full_errors;return 1;}
 bool empty=pending==0;memcpy(queue[mic_uart_tx.head&3],frame,43);queued_at[mic_uart_tx.head&3]=now_us;
 ++mic_uart_tx.head;if(++pending>max_pending)max_pending=pending;
 if(empty)next_done=now_us+430000000.0/115200;
 return 0;}
static void mark(uint8_t*p,unsigned kind){memset(p,0,43);p[0]=0x55;p[1]=0xaa;p[2]=(uint8_t)kind;p[38]=1;uv3_seal(p);}
static void ma_native_service(){}
static void ma_native_diag(uint8_t*p,unsigned){mark(p,0xe4);}
static void ma_timing_diag(uint8_t*p,unsigned,unsigned){mark(p,0xe8);}
static int mic_zero_packet(uint8_t*p,unsigned){mark(p,0xd9);return 1;}
static int ma_observer_trace_packet(uint8_t*p,unsigned,unsigned page){mark(p,0xea);p[5]=page;return records;}
static int mic_current_peak_packet(uint8_t*p,unsigned page,unsigned){mark(p,0xd8);p[5]=page;return records;}
static int mic_current_noise_packet(uint8_t*p,unsigned page,unsigned){mark(p,0xdb);p[5]=page;return 1;}
static void ma_id_status(uint8_t*p,unsigned){mark(p,0xe5);}
static int ma_id_page(uint8_t*p,unsigned,unsigned page){mark(p,0xe6);p[5]=page;return records;}
static unsigned other_last[3];
static void other(unsigned index,unsigned now,unsigned period,unsigned type,bool loose=false){
 if(MOE||uno_link.command_enabled||!mic_last_control_reply_safe_off||mic_uart_tx.hard_error||
  (uint32_t)(now-other_last[index])<period||(!loose&&mic_uart_tx.head-mic_uart_tx.tail>1))return;
 uint8_t f[43];mark(f,type);if(!uno_tx_submit(f,0)){other_last[index]=now;++bulk_count;}}
static void mic_send_repeat_meta(unsigned now){other(0,now,500,0xec);}
static void mic_send_boot_page(unsigned now){other(1,now,500,0xe9);}
static void mic_send_break_page(unsigned now){other(2,now,200,0xd1,true);}
static void hex(FILE*f,const uint8_t*p){for(unsigned i=0;i<43;++i)fprintf(f,"%02x",p[i]);}
static void export_row(){
 if(!csv||now_us<2000000)return;
 unsigned now=HAL_GetTick();
 fprintf(csv,"{\"t_us\":%u,\"ages\":[%u,%u,%u],\"packets\":[\"",(unsigned)now_us,
  receiver.has_summary?(uint32_t)(now-receiver.summary_ms):999999,
  receiver.has_detail?(uint32_t)(now-receiver.detail_ms):999999,
  receiver.has_quality?(uint32_t)(now-receiver.quality_ms):999999);
 hex(csv,receiver.summary);fputs("\",\"",csv);hex(csv,receiver.detail);fputs("\",\"",csv);hex(csv,receiver.quality);fputs("\"]}\n",csv);
}
static uint16_t ma_u(float x,uint8_t *flags) {
  if(!isfinite(x)||x<0.0f||x>65534.0f){*flags|=CM_CLIP;return 65535;}
  return (uint16_t)(x+0.5f);
}
static void put16(uint8_t *p,uint16_t x){p[0]=(uint8_t)x;p[1]=(uint8_t)(x>>8);}
static void put32(uint8_t *p,uint32_t x){for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(x>>(8*i));}
uint8_t mic_current_packet(uint8_t *packet,uint8_t detail,uint32_t build) {
  cm_core copy;
  if(!cm_snapshot_read(&copy,&state,&state_sequence))return 0;
  memset(packet,0,UV3_FRAME);packet[0]=0x55;packet[1]=0xaa;packet[2]=detail==2?0xD7:detail?0xD6:0xD5;
  uint8_t flags=(copy.zero_ready?CM_ZERO:0)|(copy.zero_bad?CM_ZERO_BAD:0);
  if(copy.was_active)flags|=CM_ACTIVE;
  cm_window *w=&copy.published;
  if(w->flags&CM_FROZEN)flags|=CM_FROZEN;
  flags|=w->flags&(CM_CLIP|CM_TIMING);
  if(copy.zero_ready && cm_window_valid(w))flags|=CM_VALID;
  packet[4]=(uint8_t)++packets;
  put32(packet+6,build);
  put32(packet+10,detail?HAL_GetTick():w->end_ms);
  if(detail==2) {
    for(unsigned i=0;i<4;++i){put16(packet+14+2*i,copy.zero_low[i]);put16(packet+22+2*i,copy.zero_high[i]);}
    packet[5]=copy.zero_attempts;packet[30]=copy.zero_stable;packet[31]=copy.zero_last_bad;
    packet[32]=CM_ZERO_BLOCKS;packet[33]=CM_ZERO_MAX_BLOCKS;packet[34]=0;packet[35]=CM_ZERO_DRIFT;packet[36]=3;packet[37]=2;
  } else if(detail) {
    for(unsigned i=0;i<4;++i){put16(packet+14+2*i,copy.raw[i]);put16(packet+22+2*i,copy.offset[i]);put16(packet+30+2*i,copy.count[i]);}
    packet[5]=4;
  } else {
    const float scale=1000.0f*ADC_REFERENCE_VOLTAGE/(4095.0f*RSHUNT*AMPLIFICATION_GAIN);
    for(unsigned i=0;i<3;++i) {
      put16(packet+14+2*i,ma_u(w->n?sqrtf((float)w->square[i]/w->n)*scale:0,&flags));
      put16(packet+20+2*i,ma_u(w->peak[i]*scale,&flags));
      float instant=w->last[i]*scale;
      if(instant>32767||instant< -32767){flags|=CM_CLIP;instant=0;}
      put16(packet+26+2*i,(uint16_t)(int16_t)instant);
    }
    if(flags&CM_CLIP)flags&=(uint8_t)~CM_VALID;
    packet[5]=(uint8_t)((w->n+w->bad)?100U*w->n/(w->n+w->bad):0);
    packet[32]=w->reconstructed;
    put16(packet+34,(uint16_t)(w->end_ms-w->start_ms));
    put16(packet+36,(uint16_t)(w->bad>65535?65535:w->bad));
  }
  packet[3]=flags;packet[38]=1;uv3_seal(packet);return 1;
}
static void mic_send_research_page(uint32_t now_ms) {
  static uint32_t last_ms;
  if((uint32_t)(now_ms-last_ms)<100U ||
      (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U || mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME];ma_native_diag(packet,MIC_NUCLEO_FW_BUILD_ID);
  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK){
    last_ms=now_ms;static unsigned timing_page;
    ma_native_service();
    if(!LL_TIM_IsEnabledAllOutputs(TIM1)){
    ma_timing_diag(packet,MIC_NUCLEO_FW_BUILD_ID,timing_page);
    if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK)timing_page=(timing_page+1U)%9U;
      }
  }
}
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
static void mic_send_noise_page(uint32_t now_ms){
 static uint32_t last_ms;static uint8_t page;
 if(LL_TIM_IsEnabledAllOutputs(TIM1)||(uint32_t)(now_ms-last_ms)<20U||
  (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||mic_uart_tx.hard_error)return;
 uint8_t packet[UV3_FRAME];
 if(mic_current_noise_packet(packet,page,MIC_NUCLEO_FW_BUILD_ID)&&
  uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK){last_ms=now_ms;page=(uint8_t)((page+1U)%91U);}
}
static void mic_send_identification(uint32_t now_ms){
 static uint32_t status_ms,page_ms;static unsigned page;
 if((uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||mic_uart_tx.hard_error)return;
 uint8_t packet[UV3_FRAME];
 if((uint32_t)(now_ms-status_ms)>=250U){
  ma_id_status(packet,MIC_NUCLEO_FW_BUILD_ID);
  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK)status_ms=now_ms;
 }else if((uint32_t)(now_ms-page_ms)>=20U&&ma_id_page(packet,MIC_NUCLEO_FW_BUILD_ID,page)){
  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK){page=(page+1U)%70U;page_ms=now_ms;}
 }
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
 for(unsigned attempt=0;attempt<7U;++attempt){
  unsigned slot=(next+attempt)%7U;uint32_t before=mic_uart_tx.head;
  switch(slot){
   case 0:mic_send_repeat_meta(now_ms);break;
   case 1:mic_send_boot_page(now_ms);break;
   case 2:mic_send_observer_page(now_ms);break;
   case 3:mic_send_break_page(now_ms);break;
   case 4:mic_send_peak_page(now_ms);break;
   case 5:mic_send_noise_page(now_ms);break;
   default:mic_send_identification(now_ms);break;
  }
  if(mic_uart_tx.head!=before){next=(uint8_t)((slot+1U)%7U);last_bulk_ms=now_ms;return;}
 }
}
static void control(unsigned now){uint8_t frame[43];mark(frame,0x80);assert(!uno_tx_submit(frame,0));
 ma_native_service();mic_send_research_page(now);ma_native_service();mic_send_current_page(now);ma_native_service();}
int main(int argc,char**argv){
 assert(argc==7);unsigned cadence=atoi(argv[1]),phase=atoi(argv[2]),stride=atoi(argv[3]);records=atoi(argv[4]);origin_ms=strtoul(argv[5],nullptr,0);
 csv=fopen(argv[6],"wb");assert(csv);cm_init(&state);state.zero_ready=1;state.zero_stable=3;state.zero_attempts=3;
 for(unsigned i=0;i<4;++i){state.offset[i]=state.raw[i]=2065+i;state.zero_low[i]=2050+i;state.zero_high[i]=2080+i;state.count[i]=256;}
 state.published.n=3200;state.published.start_ms=0;state.published.end_ms=200;state.published.flags=CM_FROZEN;
 for(unsigned i=0;i<3;++i){state.published.square[i]=(uint64_t)3200*(80+i)*(80+i);state.published.peak[i]=85+i;}
 unsigned next_control=phase,next_export=0;
 for(unsigned us=0;us<70000000;us+=stride){now_us=us;drain();unsigned now=HAL_GetTick();
  if(us>=next_control){control(now);next_control+=cadence;}
  mic_send_bulk_page(now);
  if(us>=next_export){export_row();next_export+=20000;}
 }
 fclose(csv);
 unsigned gap[3];for(unsigned i=0;i<3;++i)gap[i]=(unsigned)max_gap[i];
 printf("{\"summary_gap_us\":%u,\"detail_gap_us\":%u,\"quality_gap_us\":%u,\"receiver_good\":%u,\"receiver_bad\":%u,\"control_replies\":%u,\"max_control_latency_us\":%.1f,\"queue_full\":%u,\"max_pending\":%u,\"observer_complete_us\":%u,\"ADC_complete_us\":%u}\n",
  gap[0],gap[1],gap[2],receiver.good,receiver.bad,controls,max_control_us,full_errors,max_pending,first_complete[0],first_complete[1]);
 assert(gap[0]<750000&&gap[1]<1500000&&gap[2]<1500000);
 assert(!full_errors&&!receiver.bad&&max_control_us<50000);
 if(records)assert(first_complete[0]&&first_complete[1]&&first_complete[0]<20000000&&first_complete[1]<20000000);
 // An OFF scheduler must not start sending anything during RUN or on an
 // unacknowledged/offline link; no bypass through the new normal priority.
 for(unsigned gate=0;gate<4;++gate){MOE=gate==0;uno_link.command_enabled=gate==1;
  mic_last_control_reply_safe_off=gate!=2;mic_uart_tx.hard_error=gate==3;
  unsigned before=mic_uart_tx.head;mic_send_bulk_page(HAL_GetTick()+10000);assert(mic_uart_tx.head==before);}
}
