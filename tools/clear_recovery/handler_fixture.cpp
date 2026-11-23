#include <cassert>
#include <array>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include "clear_recovery_wire.h"
#define __weak
#define __DMB() ((void)0)
#define MC_NULL nullptr
using MCI_State_t=int;
enum {IDLE=0,RUN=6,FAULT_NOW=10,FAULT_OVER=11,MC_NO_FAULTS=0,MCI_ACK_FAULTS=3,
 GPIO_PIN_6=64,GPIO_PIN_SET=1,TIM_DIER_BIE=128,UNO_REPLY_TIMEOUT_MS=5,
 UNO_TX_SLOTS=4,UNO_TX_TAG_DIAG=0,HAL_OK=0,UNO_FLAG_CLEAR_FAULT=8,
 UNO_MODE_OFF=0,UNO_FAULT_OK=0,UNO_FAULT_INTERNAL=5,UNO_FAULT_ESTOP=3,
 UNO_DIAG_NONE=0,UNO_DIAG_TX=7,UNO_DIAG_MCSDK=8,UNO_DIAG_ESTOP=5};
static constexpr uint32_t MIC_NUCLEO_FW_BUILD_ID=2026111606;
static uint32_t tick=100,starts,stops,acks,local_calls,locks;
static bool local_ok=true,mic_local_stop_latched;
static uint32_t HAL_GetTick(){return tick;}
struct MCI_Handle_t{uint16_t CurrentFaults,PastFaults;int DirectCommand,State;} mci;
static int MCI_GetSTMState(MCI_Handle_t*p){return p->State;}
static uint16_t MCI_GetCurrentFaults(MCI_Handle_t*p){return p->CurrentFaults;}
// ACTUAL_MCI_ACK
static int MC_GetSTMStateMotor1(){return mci.State;}
static uint16_t MC_GetCurrentFaultsMotor1(){return mci.CurrentFaults;}
static uint16_t MC_GetOccurredFaultsMotor1(){return mci.PastFaults;}
static bool MC_AcknowledgeFaultMotor1(){++acks;return MCI_FaultAcknowledged(&mci);}
static bool MC_StopMotor1(){++stops;return true;}
static bool mic_local_stop_clear(){++local_calls;return local_ok;}
struct Timer{uint32_t SR,DIER;bool moe,held;} tim;
struct Port{uint32_t IDR;} gpio;
#define TIM1 (&tim)
#define GPIOA (&gpio)
static uint8_t mic_break_start_window;
static bool LL_TIM_IsEnabledAllOutputs(Timer*t){return t->moe;}
static int HAL_GPIO_ReadPin(Port*p,unsigned mask){return (p->IDR&mask)?GPIO_PIN_SET:0;}
static void LL_TIM_ClearFlag_BRK(Timer*t){if(!t->held)t->SR&=~128U;}
static void LL_TIM_ClearFlag_BRK2(Timer*t){if(!t->held)t->SR&=~256U;}
static bool LL_TIM_IsActiveFlag_BRK(Timer*t){return t->SR&128U;}
static bool LL_TIM_IsActiveFlag_BRK2(Timer*t){return t->SR&256U;}
static void LL_TIM_EnableIT_BRK(Timer*t){t->DIER|=128U;}
static uint32_t repeat_arms;
static void mic_repeat_capture_arm(uint32_t){++repeat_arms;}
struct Link{bool command_enabled,coast_hold,fault_latched;uint8_t last_mode,last_seq,fault_code,
 first_reason,first_uart_errors,first_motor_state,first_tx_status,first_sequence,last_bad_reason,
 last_uart_errors,last_tx_status;uint16_t first_current_faults,first_occurred_faults,bad_count;} uno_link;
struct Tx {uint32_t head,tail,active,started_ms,late_reported,hard_error;uint8_t bytes[4][43];} mic_uart_tx;
static bool mic_last_control_reply_safe_off=true;
static void uno_tx_lock(){++locks;}
static void uno_tx_unlock(){assert(locks);--locks;}
static int uno_tx_submit(const uint8_t*,uint8_t){return HAL_OK;}
// ACTUAL_FUNCTIONS
static void apply(const uint8_t *frame){
 // ACTUAL_CLEAR_BRANCH
}
static void reset(){
 tick=100;starts=stops=acks=local_calls=locks=repeat_arms=0;local_ok=true;
 mic_local_stop_latched=false;mic_break_start_window=0;mic_last_control_reply_safe_off=true;
 memset(&mci,0,sizeof mci);mci.State=FAULT_OVER;mci.PastFaults=4;
 memset(&tim,0,sizeof tim);tim.SR=128;gpio.IDR=64;
 memset(&uno_link,0,sizeof uno_link);uno_link.fault_latched=true;uno_link.fault_code=5;
 uno_link.first_reason=8;uno_link.first_current_faults=4;uno_link.first_occurred_faults=4;
 memset(&mic_uart_tx,0,sizeof mic_uart_tx);
#if CANDIDATE
 mic_clear_diag_ready=0;
#endif
}
int main(){
 uint8_t frame[43]={};frame[3]=8;
 reset();mic_uart_tx.head=1;mic_uart_tx.active=1;mic_uart_tx.started_ms=100;
 memset(mic_uart_tx.bytes,0xa5,sizeof mic_uart_tx.bytes);auto saved=mic_uart_tx;
 apply(frame);
 assert(!memcmp(&saved,&mic_uart_tx,sizeof saved));
#if CANDIDATE
 assert(!uno_link.fault_latched && tim.DIER==128 && acks==1 && repeat_arms==1);
 assert(mci.State==FAULT_OVER && mci.PastFaults==0 && mci.DirectCommand==MCI_ACK_FAULTS);
 assert(uno_mcsdk_fault_present()); // asynchronous ACK must still block START
 mci.State=IDLE;assert(!uno_mcsdk_fault_present());
 assert(mic_clear_diag_packet[37]==CC_ACCEPTED && cc_valid(mic_clear_diag_packet,MIC_NUCLEO_FW_BUILD_ID));
 assert(cc_u32(mic_clear_diag_packet+14)==1 && mic_clear_diag_packet[26]&1);
 auto frozen=std::array<uint8_t,43>{};memcpy(frozen.data(),mic_clear_diag_packet,43);
 apply(frame);assert(!memcmp(frozen.data(),mic_clear_diag_packet,43));
 for(unsigned gate=0;gate<6;++gate){
  reset();
  if(gate==0){mic_uart_tx.active=1;mic_uart_tx.head=1;mic_uart_tx.started_ms=94;}
  if(gate==1)mic_uart_tx.hard_error=1;
  if(gate==2){mic_uart_tx.active=1;mic_uart_tx.head=1;mic_uart_tx.started_ms=100;mic_uart_tx.late_reported=1;}
  if(gate==3)mic_uart_tx.head=4;
  if(gate==4)gpio.IDR=0;
  if(gate==5)tim.held=true;
  apply(frame);assert(uno_link.fault_latched && acks==0 && !tim.DIER && !starts);
  assert(mic_clear_diag_packet[37]==(gate<4?CC_TX_BLOCKED:CC_BREAK_BLOCKED));
 }
 reset();tim.moe=true;apply(frame);assert(!acks && !tim.DIER && uno_link.fault_latched);
 for(unsigned mask=1;mask<=0x8000;mask<<=1){
  reset();mci.CurrentFaults=mask;mci.State=FAULT_NOW;apply(frame);
  assert(uno_link.fault_latched && mci.CurrentFaults==mask && mci.PastFaults==4);
  assert(uno_link.first_current_faults==4 && mic_clear_diag_packet[37]==CC_MCSDK_REJECTED);
 }
 reset();mic_local_stop_latched=true;local_ok=false;apply(frame);
 assert(uno_link.fault_latched && mic_clear_diag_packet[37]==CC_LOCAL_STOP_BLOCKED);
 reset();mci.State=IDLE;mci.PastFaults=0;apply(frame);assert(!acks && !uno_link.fault_latched && !starts);
 reset();mic_uart_tx.active=1;mic_uart_tx.head=3;mic_uart_tx.started_ms=95;apply(frame);
 assert(!uno_link.fault_latched); // original5ms boundary, one reply slot reserved
 reset();mic_uart_tx.active=1;mic_uart_tx.head=0;mic_uart_tx.tail=0xfffffffe;mic_uart_tx.started_ms=0xfffffffd;
 tick=2;apply(frame);assert(!uno_link.fault_latched); // uint32 wrap and5ms boundary
 reset();mic_uart_tx.head=1;mic_uart_tx.active=1;mic_uart_tx.started_ms=100;apply(frame);
 for(unsigned i=0;i<43U*8U;++i){uint8_t bad[43];memcpy(bad,mic_clear_diag_packet,43);bad[i/8]^=1U<<(i%8);assert(!cc_valid(bad,MIC_NUCLEO_FW_BUILD_ID));}
 for(unsigned i=0;i<43;++i)printf("%02x",mic_clear_diag_packet[i]);puts("");
#else
 assert(uno_link.fault_latched && acks==0 && tim.DIER==0 && repeat_arms==0);
 puts("healthy_background_TX_rejects_CLEAR_before_Break_and_MCSDK");
#endif
 // No overwrite/abort of the owned active telemetry frame, even with CLEAR.
 (void)saved;assert(!starts && !locks);
}
