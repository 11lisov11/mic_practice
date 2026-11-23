/* OFF-only PB11/ADC2_IN14 observation. No writes to ADC1, JSQR, injected
 * sampling, comparator, TIM1 or GPIOA/SD. All waits are asynchronous. */
#include "stm32g4xx_ll_adc.h"
#include "cin_wire.h"
static struct {
 cd_record last;
 uint32_t next_ms,start_ms,start_cycles;
 uint8_t pending,sd_before;
} cin_diag;
static void cin_diag_init(void){
 GPIO_InitTypeDef pin={0};__HAL_RCC_GPIOB_CLK_ENABLE();
 pin.Pin=GPIO_PIN_11;pin.Mode=GPIO_MODE_ANALOG;pin.Pull=GPIO_NOPULL;
 HAL_GPIO_Init(GPIOB,&pin);
 LL_ADC_REG_SetSequencerLength(ADC2,LL_ADC_REG_SEQ_SCAN_DISABLE);
 LL_ADC_REG_SetSequencerRanks(ADC2,LL_ADC_REG_RANK_1,LL_ADC_CHANNEL_14);
 LL_ADC_REG_SetTriggerSource(ADC2,LL_ADC_REG_TRIG_SOFTWARE);
 LL_ADC_SetChannelSamplingTime(ADC2,LL_ADC_CHANNEL_14,LL_ADC_SAMPLINGTIME_247CYCLES_5);
 cin_diag.next_ms=HAL_GetTick()+5000U;
}
static void cin_diag_finish(uint32_t now,uint8_t reason){
 cd_record*r=&cin_diag.last;++r->sequence;if(!r->sequence)++r->sequence;
 r->start_ms=cin_diag.start_ms;r->end_ms=now;
 r->cycles=DWT->CYCCNT-cin_diag.start_cycles;r->vref_mv=3290;
 r->reason=reason;r->flags=cin_diag.sd_before?CD_SD_BEFORE:0;
 if(GPIOA->IDR&GPIO_PIN_6)r->flags|=CD_SD_AFTER;
 if(reason==CD_OK)r->flags|=CD_VALID;
 else{r->raw=0;if(r->errors!=UINT32_MAX)++r->errors;}
 cin_diag.pending=0;cin_diag.next_ms=now+100U;
}
static void cin_diag_service(uint32_t now,bool safe_off,bool zero_ready){
 if(cin_diag.pending){
  if(!safe_off){
   if(LL_ADC_REG_IsConversionOngoing(ADC2))LL_ADC_REG_StopConversion(ADC2);
   cin_diag_finish(now,CD_UNSAFE);return;
  }
  if(LL_ADC_IsActiveFlag_OVR(ADC2)){
   LL_ADC_ClearFlag_OVR(ADC2);cin_diag_finish(now,CD_OVERRUN);return;
  }
  /* A late EOC must not be mistaken for a fresh simultaneous observation. */
  if((uint32_t)(now-cin_diag.start_ms)>=2U){
   if(LL_ADC_REG_IsConversionOngoing(ADC2))LL_ADC_REG_StopConversion(ADC2);
   LL_ADC_ClearFlag_EOC(ADC2);LL_ADC_ClearFlag_EOS(ADC2);
   if(cin_diag.last.timeouts!=UINT32_MAX)++cin_diag.last.timeouts;
   cin_diag_finish(now,CD_TIMEOUT);return;
  }
  if(LL_ADC_IsActiveFlag_EOC(ADC2)){
   /* This ADC uses left-aligned 12-bit data, unlike a default HAL example. */
   cin_diag.last.raw=(uint16_t)((ADC2->DR>>4)&4095U);
   LL_ADC_ClearFlag_EOC(ADC2);LL_ADC_ClearFlag_EOS(ADC2);
   cin_diag_finish(now,CD_OK);return;
  }
  return;
 }
 if(!safe_off||!zero_ready||(int32_t)(now-cin_diag.next_ms)<0)return;
 cin_diag.start_ms=now;cin_diag.start_cycles=DWT->CYCCNT;
 cin_diag.sd_before=(GPIOA->IDR&GPIO_PIN_6)!=0;
 if(!(ADC2->CR&ADC_CR_ADEN)||
    (ADC2->CFGR&(ADC_CFGR_EXTEN|ADC_CFGR_DMAEN|ADC_CFGR_CONT))||
    (ADC2->SQR1&(ADC_SQR1_L|ADC_SQR1_SQ1))!=(14U<<ADC_SQR1_SQ1_Pos)){
  cin_diag_finish(now,CD_CONFIG);return;
 }
 if(LL_ADC_REG_IsConversionOngoing(ADC2)){
  cin_diag_finish(now,CD_BUSY);return;
 }
 LL_ADC_ClearFlag_EOC(ADC2);LL_ADC_ClearFlag_EOS(ADC2);LL_ADC_ClearFlag_OVR(ADC2);
 cin_diag.pending=1;LL_ADC_REG_StartConversion(ADC2);
}
static void mic_send_cin_page(uint32_t now){
 static uint32_t sent;
 if(!cin_diag.last.sequence||sent==cin_diag.last.sequence||LL_TIM_IsEnabledAllOutputs(TIM1)||
    uno_link.command_enabled||!mic_last_control_reply_safe_off||
    (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||mic_uart_tx.hard_error)return;
 uint8_t p[UV3_FRAME];cd_packet(p,&cin_diag.last,MIC_NUCLEO_FW_BUILD_ID);
 if(uno_tx_submit(p,UNO_TX_TAG_DIAG)==HAL_OK)sent=cin_diag.last.sequence;
 (void)now;
}
