
#include <cassert>
#include <cstdint>
#include <cstdio>
struct TIM_TypeDef { uint32_t BDTR = 0; };
TIM_TypeDef timer;
#define TIM1 (&timer)
enum { GPIO_PIN_SET=1, IDLE=0, RUN=1, STOPPING=2, MC_NO_FAULTS=0,
       Start_Stop_GPIO_Port=0, Start_Stop_Pin=13, LL_EXTI_LINE_13=13,
       LL_TIM_OSSI_ENABLE=1 };
bool held=false, pending=false, irq_deferred=false;
uint32_t mask=0;
unsigned injection=0, calls=0, starts=0, checks=0, stops=0;
int state=IDLE;
unsigned current_faults=0, occurred_faults=0;
uint8_t bMCBootCompleted=1;
void UI_HandleStartStopButton_cb();
void press() {
 held=true; pending=true;
 if (mask) irq_deferred=true;
 else { pending=false; UI_HandleStartStopButton_cb(); }
}
void boundary() { if (injection && ++calls == injection) press(); }
int HAL_GPIO_ReadPin(int,int) { boundary(); return held ? 0 : GPIO_PIN_SET; }
bool LL_EXTI_IsActiveFlag_0_31(int) { boundary(); return pending; }
uint32_t __get_PRIMASK() { return mask; }
void __disable_irq() { mask=1; }
void __set_PRIMASK(uint32_t m) {
 mask=m;
 if (!mask && irq_deferred) {
   irq_deferred=false; pending=false; UI_HandleStartStopButton_cb();
 }
}
void LL_TIM_DisableAllOutputs(TIM_TypeDef *t) { t->BDTR &= ~0x8000U; }
void LL_TIM_EnableAllOutputs(TIM_TypeDef *t) { boundary(); t->BDTR |= 0x8000U; }
bool LL_TIM_IsEnabledAllOutputs(TIM_TypeDef *t) { return bool(t->BDTR & 0x8000U); }
void LL_TIM_ClearFlag_UPDATE(TIM_TypeDef*) {}
void LL_TIM_EnableIT_UPDATE(TIM_TypeDef*) {}
int MC_GetSTMStateMotor1() { return state; }
unsigned MC_GetCurrentFaultsMotor1() { return current_faults; }
unsigned MC_GetOccurredFaultsMotor1() { return occurred_faults; }
bool MC_StopMotor1() { ++stops; if (state != IDLE) state=STOPPING; return state!=IDLE; }
bool MC_StartMotor1() { ++starts; return true; }
struct PWM_Handle_t { TIM_TypeDef *TIMx; };
void check(bool v) { ++checks; assert(v); }
volatile uint32_t mic_local_stop_latched;
static bool mic_local_button_pending(void) {
  return HAL_GPIO_ReadPin(Start_Stop_GPIO_Port, Start_Stop_Pin) != GPIO_PIN_SET ||
         LL_EXTI_IsActiveFlag_0_31(LL_EXTI_LINE_13);
}
bool mic_local_stop_blocked(void) {
  if (mic_local_button_pending()) mic_local_stop_latched = 1U;
  return mic_local_stop_latched != 0U;
}
void UI_HandleStartStopButton_cb(void) {
  mic_local_stop_latched = 0U;
  LL_TIM_DisableAllOutputs(TIM1);
  if (bMCBootCompleted != 0U) (void)MC_StopMotor1();
}
void mic_local_stop_enable_outputs(TIM_TypeDef *timer) {
  /* Only the MOE publication is atomic; BKIN remains hardware-active. */
  const uint32_t mask = __get_PRIMASK();
  __disable_irq();
  if (mic_local_stop_blocked()) LL_TIM_DisableAllOutputs(timer);
  else LL_TIM_EnableAllOutputs(timer);
  __set_PRIMASK(mask);
}
bool mic_local_stop_clear(void) {
  const uint32_t mask = __get_PRIMASK();
  __disable_irq();
  const bool allowed = !mic_local_button_pending() &&
      !LL_TIM_IsEnabledAllOutputs(TIM1) && MC_GetSTMStateMotor1() == IDLE &&
      MC_GetCurrentFaultsMotor1() == MC_NO_FAULTS &&
      MC_GetOccurredFaultsMotor1() == MC_NO_FAULTS;
  if (allowed) mic_local_stop_latched = 0U;
  __set_PRIMASK(mask);
  return allowed;
}
void PWM_SwitchOnPWM(PWM_Handle_t *pHandle)
{

  /* Clear the TIMx Update */
  LL_TIM_ClearFlag_UPDATE(pHandle->TIMx);
  
  /* Enable the TIMx Update - it is used as HFT time base to perform the V/F conntrol */  
  LL_TIM_EnableIT_UPDATE(pHandle->TIMx);
 
  /* Main PWM Output Enable */
  pHandle->TIMx->BDTR |= LL_TIM_OSSI_ENABLE;
  mic_local_stop_enable_outputs(pHandle->TIMx);  
  
}
void reset() {
 held=pending=irq_deferred=false; mask=0; injection=calls=starts=stops=0;
 state=IDLE; current_faults=occurred_faults=0;
 mic_local_stop_latched=0; timer.BDTR=0;
 bMCBootCompleted=1;
}
int main() {
 PWM_Handle_t pwm{TIM1};
 reset(); bMCBootCompleted=0; press();
 check(mic_local_stop_latched==1 && stops==0);
 held=false; PWM_SwitchOnPWM(&pwm); check(!LL_TIM_IsEnabledAllOutputs(TIM1));
 reset(); PWM_SwitchOnPWM(&pwm); check(LL_TIM_IsEnabledAllOutputs(TIM1));
 state=RUN; press(); check(!LL_TIM_IsEnabledAllOutputs(TIM1));
 check(mic_local_stop_latched==1 && state==STOPPING);
 held=false; state=IDLE;
 for (unsigned i=0;i<1000;++i) {
   if (!mic_local_stop_blocked()) MC_StartMotor1();
   PWM_SwitchOnPWM(&pwm);
   check(!LL_TIM_IsEnabledAllOutputs(TIM1));
 }
 check(starts==0); check(mic_local_stop_latched==1);
 check(mic_local_stop_clear()); check(!LL_TIM_IsEnabledAllOutputs(TIM1));
 if (!mic_local_stop_blocked()) MC_StartMotor1();
 PWM_SwitchOnPWM(&pwm); check(starts==1 && LL_TIM_IsEnabledAllOutputs(TIM1));
 // Pending start publication cannot re-enable MOE after a serviced button IRQ.
 reset(); MC_StartMotor1(); press(); held=false;
 PWM_SwitchOnPWM(&pwm); check(!LL_TIM_IsEnabledAllOutputs(TIM1));
 // Inject edges before/during the atomic output enable operation.
 for (unsigned n=1;n<=3;++n) {
   reset(); injection=n; PWM_SwitchOnPWM(&pwm);
   check(held); check(mic_local_stop_latched==1);
   check(!LL_TIM_IsEnabledAllOutputs(TIM1)); check(mask==0);
 }
 reset(); mic_local_stop_latched=1; held=true;
 check(!mic_local_stop_clear()); check(mic_local_stop_latched==1);
 held=false; pending=true; check(!mic_local_stop_clear());
 pending=false; state=STOPPING; check(!mic_local_stop_clear());
 state=IDLE; timer.BDTR=0x8000; check(!mic_local_stop_clear());
 timer.BDTR=0; current_faults=4; check(!mic_local_stop_clear());
 current_faults=0; occurred_faults=4; check(!mic_local_stop_clear());
 occurred_faults=0; check(mic_local_stop_clear());
 for (unsigned n=1;n<=2;++n) {
   reset(); mic_local_stop_latched=1; injection=n;
   check(!mic_local_stop_clear()); check(mic_local_stop_latched==1);
 }
 reset(); mask=1; PWM_SwitchOnPWM(&pwm); check(mask==1);
 press(); check(mic_local_stop_blocked()); PWM_SwitchOnPWM(&pwm);
 check(!LL_TIM_IsEnabledAllOutputs(TIM1)); __set_PRIMASK(0);
 std::printf("checks=%u\n",checks);
}
