
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include "superseded_reply.h"
static uint32_t clock_us=100000,g_bp_last_rsp_ms=100,g_nucleo_last_tx_ms=100;
static uint32_t g_nucleo_last_send_us=100000,g_nucleo_last_send_ms=100;
static const uint32_t BP_REPLY_TIMEOUT_MS=500,NUCLEO_RUN_REPLY_GUARD_US=8000,
 NUCLEO_SCALAR_MIN_SEND_US=50000,NUCLEO_RUN_MIN_SEND_US=50000,NUCLEO_HEARTBEAT_MS=50;
static const bool USE_EXTERNAL_PWM=true,NUCLEO_MCSDK_ACIM_BACKEND=true,USE_NUCLEO_UART_FALLBACK=true;
static bool g_estop_latched=false,g_io_test_mode=false,g_diag_pwm=false,g_duty_mode=false,g_clear_fault_req=false,
 g_pwm_enabled=true,g_nucleo_waiting_rsp=true,g_nucleo_waiting_clear=false;
static unsigned g_bp_fault_code=0,g_bp_status=0,g_mode=0,g_state=1;
enum{MODE_VF=0,STATE_VF_RUN=1,BP_STATUS_FAULT=8,BP_STATUS_TIMEOUT=16};
static uint8_t g_nucleo_waiting_seq=1,seq=1;
static SupersededReplies g_nucleo_superseded;
static unsigned writes;
static uint32_t millis(){return clock_us/1000;}static uint32_t micros(){return clock_us;}
static void nucleo_uart_poll(){}
static bool bp_fault_or_timeout(uint32_t now_ms) {
  bool bp_fault = (g_bp_fault_code != 0) ||
                  ((g_bp_status & BP_STATUS_FAULT) != 0u) ||
                  ((g_bp_status & BP_STATUS_TIMEOUT) != 0u);
  bool bp_stale = false;
  if (g_pwm_enabled) {
    if (g_bp_last_rsp_ms == 0) {
      if (g_nucleo_last_tx_ms != 0) {
        bp_stale = (uint32_t)(now_ms - g_nucleo_last_tx_ms) > BP_REPLY_TIMEOUT_MS;
      }
    } else {
      bp_stale = (uint32_t)(now_ms - g_bp_last_rsp_ms) > BP_REPLY_TIMEOUT_MS;
    }
  }
  return bp_fault || bp_stale;
}
static void attempt(float d_u, float d_v, float d_w, bool enable, bool force) {(void)d_u;(void)d_v;(void)d_w;
  if (!USE_EXTERNAL_PWM) {
    return;
  }
  uint32_t now = millis();
  uint32_t now_us = micros();
  const bool mcsdk_scalar =
      NUCLEO_MCSDK_ACIM_BACKEND && enable && !g_estop_latched && !g_io_test_mode;
  const bool local_scalar = mcsdk_scalar ||
      (enable && !g_estop_latched && !g_diag_pwm && !g_duty_mode &&
       g_mode == MODE_VF && g_state == STATE_VF_RUN);
  // When outputs are off we throttle updates to a heartbeat rate,
  // but if a CLEAR is pending we keep sending until it is acknowledged.
  if (!force && !enable && !g_clear_fault_req && (uint32_t)(now - g_nucleo_last_send_ms) < NUCLEO_HEARTBEAT_MS) {
    return;
  }
  if (!force && !g_estop_latched && USE_NUCLEO_UART_FALLBACK) {
    nucleo_uart_poll();
    if (g_nucleo_waiting_rsp) {
      if ((uint32_t)(now_us - g_nucleo_last_send_us) < NUCLEO_RUN_REPLY_GUARD_US) {
        return;
      }
      g_nucleo_superseded.retire(g_nucleo_waiting_seq, g_nucleo_last_send_us);
      g_nucleo_waiting_rsp = false;
    }
  }
  const uint32_t min_send_us = local_scalar ? NUCLEO_SCALAR_MIN_SEND_US : NUCLEO_RUN_MIN_SEND_US;
  if (!force && (enable || g_clear_fault_req) &&
      (uint32_t)(now_us - g_nucleo_last_send_us) < min_send_us) {
    return;
  }

 uint8_t seq=++::seq;const bool clear_eff=g_clear_fault_req;    if (force && g_nucleo_waiting_rsp) {
      g_nucleo_superseded.retire(g_nucleo_waiting_seq, g_nucleo_last_send_us);
    }
    g_nucleo_superseded.forget(seq);
    g_nucleo_waiting_rsp = true;
    g_nucleo_waiting_seq = seq;
    g_nucleo_waiting_clear = clear_eff;

 ++writes;g_nucleo_last_send_us=now_us;g_nucleo_last_send_ms=now;g_nucleo_last_tx_ms=now;
}

static void reset(){clock_us=100000;g_bp_last_rsp_ms=g_nucleo_last_tx_ms=g_nucleo_last_send_ms=100;
 g_nucleo_last_send_us=100000;g_nucleo_superseded={};g_nucleo_waiting_rsp=true;g_nucleo_waiting_seq=1;seq=1;writes=0;}
int main(){
 unsigned lost=0,accepted=0;
 for(unsigned delay=9000;delay<50000;delay+=1000){
  reset();
  for(unsigned t=1000;t<=delay;t+=1000){clock_us=100000+t;attempt(0,0,0,true,false);}
  bool retired=g_nucleo_superseded.consume(1,clock_us,500000);
  if(!retired&&g_nucleo_waiting_rsp&&g_nucleo_waiting_seq==1){++accepted;g_nucleo_waiting_rsp=false;g_bp_last_rsp_ms=millis();}
  else ++lost;
  assert(writes==0); // no actual replacement before50ms
 }
 assert(accepted==0&&lost==41);
 reset();clock_us=150000;attempt(0,0,0,true,false);assert(writes==1&&g_nucleo_waiting_seq==2);
 assert(g_nucleo_superseded.consume(1,151000,500000)); // genuinely replaced reply stays stale
 reset();clock_us=101000;attempt(0,0,0,false,true);assert(writes==1); // immediate STOP bypasses cadence
 assert(g_nucleo_superseded.consume(1,102000,500000));
 reset();clock_us=600000;assert(!bp_fault_or_timeout(millis()));clock_us=601000;assert(bp_fault_or_timeout(millis()));
 g_bp_status=BP_STATUS_FAULT;clock_us=100001;assert(bp_fault_or_timeout(millis()));
 printf("{\"accepted_current_replies\":%u,\"discarded_current_replies\":%u,\"genuine500ms_watchdog_preserved\":true}\n",accepted,lost);
}
