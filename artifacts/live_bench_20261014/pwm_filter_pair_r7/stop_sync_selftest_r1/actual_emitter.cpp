#include <array>
#include <vector>

#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#define __weak
#define TIM_SR_BIF (1U << 7)
#define TIM_SR_B2IF (1U << 8)
#define MC_DP_FAULT 0x400
#define MC_NO_FAULTS 0
#define MC_OVER_VOLT 2
#define MC_OVER_CURR 1
struct TIM_TypeDef { uint32_t SR, DIER, BDTR, CNT, ARR, CCR1, CCR2, CCR3; } timer;
struct { uint32_t IDR; } gpio;
#define TIM1 (&timer)
#define GPIOA (&gpio)
void __DMB() {}
#include "first_break_snapshot.h"
volatile mic_break_snapshot_t mic_first_break;
volatile mic_break_snapshot_t mic_first_start_break;
volatile uint32_t mic_break_start_window;
volatile uint32_t mic_break_irq_count;
volatile mic_break_context_t mic_break_context[2];
volatile uint32_t mic_break_context_index, mic_break_context_valid;
struct PWMC_Handle_t { bool OverVoltageFlag, OverCurrentFlag, driverProtectionFlag, BrakeActionLock; uint8_t Motor; };
struct { PWMC_Handle_t _Super; } PWM_Handle_M1;
unsigned off_calls, scheduler_calls, cases;
uint32_t clock_ms;
bool held_low;
uint32_t HAL_GetTick() { return clock_ms; }
bool LL_TIM_IsActiveFlag_BRK(TIM_TypeDef *t) { return (t->SR & TIM_SR_BIF) != 0; }
bool LL_TIM_IsActiveFlag_BRK2(TIM_TypeDef *t) { return (t->SR & TIM_SR_B2IF) != 0; }
void LL_TIM_ClearFlag_BRK(TIM_TypeDef *t) { if (!held_low) t->SR &= ~TIM_SR_BIF; }
void LL_TIM_ClearFlag_BRK2(TIM_TypeDef *t) { if (!held_low) t->SR &= ~TIM_SR_B2IF; }
void LL_TIM_DisableIT_BRK(TIM_TypeDef *t) { t->DIER &= ~(1U << 7); }
void PWMC_SwitchOffPWM(PWMC_Handle_t *) { ++off_calls; timer.BDTR &= ~(1U << 15); }
void MC_Scheduler() { ++scheduler_calls; }
void reset() {
 std::memset(const_cast<mic_break_snapshot_t *>(&mic_first_break),0,sizeof(mic_first_break));
 std::memset(const_cast<mic_break_snapshot_t *>(&mic_first_start_break),0,sizeof(mic_first_start_break));
 std::memset(const_cast<mic_break_context_t *>(mic_break_context),0,sizeof(mic_break_context));
 mic_break_start_window=0; mic_break_irq_count=0; mic_break_context_index=0; mic_break_context_valid=0;
 PWM_Handle_M1={}; off_calls=scheduler_calls=0; held_low=false; clock_ms=1234;
 timer={0,1U<<7,(1U<<12)|(1U<<15),37,4000,500,1500,2500}; gpio.IDR=0;
}
__weak void *PWMC_DP_Handler(PWMC_Handle_t *pHandle)
{
  void *tempPointer; //cstat !MISRAC2012-Rule-8.13
#ifdef NULL_PTR_CHECK_PWR_CUR_FDB
  if (MC_NULL == pHandle)
  {
    tempPointer = MC_NULL;
  }
  else
  {
#endif
    PWMC_SwitchOffPWM(pHandle);
    pHandle->driverProtectionFlag = true;
    tempPointer = &(pHandle->Motor);
#ifdef NULL_PTR_CHECK_PWR_CUR_FDB
  }
#endif
  return (tempPointer);
}
__weak uint16_t PWMC_IsFaultOccurred(PWMC_Handle_t *pHandle)
{
  uint16_t retVal = MC_NO_FAULTS;

  if (true == pHandle->OverVoltageFlag)
  {
    retVal = MC_OVER_VOLT;
    pHandle->OverVoltageFlag = false;
  }
  else
  {
    /* Nothing to do */
  }

  if (true == pHandle->OverCurrentFlag)
  {
    retVal |= MC_OVER_CURR;
    pHandle->OverCurrentFlag = false;
  }
  else
  {
    /* Nothing to do */
  }

  if (true == pHandle->driverProtectionFlag)
  {
    retVal |= MC_DP_FAULT;
    pHandle->driverProtectionFlag = false;
  }
  else
  {
    /* Nothing to do */
  }

  return (retVal);
}
void TIMx_BRK_M1_IRQHandler(void)
{
  /* USER CODE BEGIN TIMx_BRK_M1_IRQn 0 */

  /* USER CODE END TIMx_BRK_M1_IRQn 0 */
  mic_break_capture_first(HAL_GetTick());
  /* BIF cannot clear while the break level is active. Mask only its IRQ;
     hardware BKE remains enabled. A clean CLEAR rearms BIE in main.c. */
  if (LL_TIM_IsActiveFlag_BRK(TIM1) || LL_TIM_IsActiveFlag_BRK2(TIM1))
  {
    LL_TIM_DisableIT_BRK(TIM1);
  }
  if (LL_TIM_IsActiveFlag_BRK(TIM1))
  {
    LL_TIM_ClearFlag_BRK(TIM1);
    /* IPM SD reports driver protection, not DC-bus overvoltage. */
    PWMC_DP_Handler(&PWM_Handle_M1._Super);
  }
  if (LL_TIM_IsActiveFlag_BRK2(TIM1))
  {
    LL_TIM_ClearFlag_BRK2(TIM1);
    PWMC_DP_Handler(&PWM_Handle_M1._Super);
  }
  /* Systick is not executed due low priority so is necessary to call MC_Scheduler here.*/
  MC_Scheduler();

  /* USER CODE BEGIN TIMx_BRK_M1_IRQn 1 */

  /* USER CODE END TIMx_BRK_M1_IRQn 1 */
}


#include "break_wire.h"
enum { RUN=6, UNO_REPLY_TIMEOUT_MS=5, HAL_OK=0 };
struct { bool command_enabled; } uno_link;
uint32_t mic_break_diag_tx_errors;
bool mic_last_control_reply_safe_off=true;
int huart1, mc_state, transmit_status;
std::vector<std::array<uint8_t,UV3_FRAME>> sent;
int MC_GetSTMStateMotor1() { return mc_state; }
bool LL_TIM_IsEnabledAllOutputs(TIM_TypeDef *t) { return (t->BDTR & (1U<<15))!=0; }
int HAL_UART_Transmit(int *,uint8_t *packet,unsigned length,unsigned timeout) {
 assert(length==UV3_FRAME && timeout==5);
 std::array<uint8_t,UV3_FRAME> copy{}; std::memcpy(copy.data(),packet,length);
 sent.push_back(copy); return transmit_status;
}
static void mic_send_break_page(uint32_t now_ms) {
  static uint32_t last_ms;
  static uint8_t slot;
  if (!mic_last_control_reply_safe_off || uno_link.command_enabled || mic_break_start_window != 0U ||
      LL_TIM_IsEnabledAllOutputs(TIM1) || MC_GetSTMStateMotor1() == RUN ||
      (uint32_t)(now_ms-last_ms) < 200U) return;
  last_ms = now_ms;
  const unsigned kind = slot / BW_PAGES;
  const unsigned page = slot % BW_PAGES;
  const volatile mic_break_snapshot_t *record = kind == 0U ? &mic_first_break : &mic_first_start_break;
  uint8_t raw[BW_BYTES] = {0};
  if (record->magic == MIC_BREAK_MAGIC) {
    __DMB();
    const volatile uint8_t *bytes = (const volatile uint8_t *)record;
    for (unsigned i=0;i<BW_BYTES;++i) raw[i]=bytes[i];
  }
  uint8_t packet[UV3_FRAME];
  bw_packet(packet,raw,kind,page);
  /* A diagnostic TX failure is counted separately; normal control TX fault
     handling remains unchanged. No START/CLEAR or retry loop occurs here. */
  if (HAL_UART_Transmit(&huart1,packet,UV3_FRAME,UNO_REPLY_TIMEOUT_MS) != HAL_OK)
    bw_increment(&mic_break_diag_tx_errors);
  slot=(uint8_t)((slot+1U)%(2U*BW_PAGES));
}
void published(int tx_status,uint8_t status){
  mic_last_control_reply_safe_off = (tx_status == HAL_OK) && ((status & 0x22U) == 0U);
}
int main() {
 reset(); timer.BDTR&=~(1U<<15); uint32_t now=200; unsigned count=0;
 uno_link.command_enabled=true; mic_send_break_page(now); assert(sent.empty()); ++count;
 uno_link.command_enabled=false; mic_break_start_window=1;
 mic_send_break_page(now); assert(sent.empty()); ++count;
 mic_break_start_window=0; timer.BDTR|=1U<<15;
 mic_send_break_page(now); assert(sent.empty()); ++count;
 timer.BDTR&=~(1U<<15); mc_state=RUN;
 mic_send_break_page(now); assert(sent.empty()); ++count;
 mc_state=0; mic_send_break_page(now); assert(sent.size()==1 && sent[0][2]==BW_VERSION); ++count;
 mic_send_break_page(now+199); assert(sent.size()==1); ++count;
 bw_receiver rx{};
 bw_receive(&rx,sent[0].data(),BW_NUCLEO_BUILD,true,now);
 for(unsigned i=1;i<8;++i) {
  now+=200; mic_send_break_page(now);
  bw_receive(&rx,sent.back().data(),BW_NUCLEO_BUILD,true,now);
 }
 assert(rx.complete[0] && rx.complete[1] && bw_u32(rx.data[0])==0 && bw_u32(rx.data[1])==0); ++count;
 // Actual recorded IRQ is propagated through emitter and assembler, without RUN.
 timer.SR=TIM_SR_BIF; clock_ms=now; mic_break_start_window=1;
 TIMx_BRK_M1_IRQHandler(); mic_break_start_window=0;
 bw_reset(&rx);
 for(unsigned i=0;i<8;++i) {
  now+=200; mic_send_break_page(now); bw_receive(&rx,sent.back().data(),BW_NUCLEO_BUILD,true,now);
 }
 assert(rx.complete[0] && rx.complete[1] && bw_u32(rx.data[1])==MIC_BREAK_MAGIC);
 assert(bw_u32(rx.data[1]+16)&TIM_SR_BIF); ++count;
 transmit_status=1; now+=200; mic_send_break_page(now);
 assert(mic_break_diag_tx_errors==1 && (timer.BDTR&(1U<<12))); ++count;
 mic_break_diag_tx_errors=UINT32_MAX; now+=200; mic_send_break_page(now);
 assert(mic_break_diag_tx_errors==UINT32_MAX); ++count;

 // The encoded reply says ON, but the timer is now physically OFF.
 // A page must wait for a successful OFF reply published to the UART peer.
 transmit_status=HAL_OK;timer.BDTR&=~(1U<<15);mc_state=0;
 const auto sent_before=sent.size();
 published(HAL_OK,0x6d);now+=200;mic_send_break_page(now);
 assert(!mic_last_control_reply_safe_off && sent.size()==sent_before);++count;
 published(HAL_OK,0x0d);now+=200;mic_send_break_page(now);
 assert(mic_last_control_reply_safe_off && sent.size()==sent_before+1);++count;
 published(1,0x0d);now+=200;mic_send_break_page(now);
 assert(!mic_last_control_reply_safe_off && sent.size()==sent_before+1);++count;
 published(HAL_OK,0x03);now+=200;mic_send_break_page(now);
 assert(!mic_last_control_reply_safe_off && sent.size()==sent_before+1);++count;
 std::printf("{\"pass\":true,\"emitter_cases\":%u}\n",count);
}
