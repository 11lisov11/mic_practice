/* Real logic edges on PC6/7/8, never on the motor connector.
 * PD2 AF4 receives the existing active-low SD through a PA6--PD2 jumper.
 * TIM8 BKIN is active low, no automatic output rearm. TIM1 is untouched.
 * The enclosing diagnostic retains its one-shot 5s DWT deadline and guards.
 */
#include "main.h"
#include "load_core.h"
#include "logic_edges.h"

#define EDGE_PINS (GPIO_PIN_6|GPIO_PIN_7|GPIO_PIN_8)
#define ALL_PINS (EDGE_PINS|GPIO_PIN_9)
#define EDGE_MODES ((3U<<12)|(3U<<14)|(3U<<16))
#define EDGE_GPIO ((1U<<12)|(1U<<14)|(1U<<16))
#define EDGE_AF ((2U<<12)|(2U<<14)|(2U<<16))
#define EDGE_PWM12 ((6U<<4)|(6U<<12)|TIM_CCMR1_OC1PE|TIM_CCMR1_OC2PE)
#define EDGE_PWM3 ((6U<<4)|TIM_CCMR2_OC3PE)
#define EDGE_CC (TIM_CCER_CC1E|TIM_CCER_CC2E|TIM_CCER_CC3E)
#define EDGE_BAD 256U
volatile uint32_t mic_logic_edge_report[12];

static void seal(void){
  uint32_t v[11];for(unsigned i=0;i<11;i++)v[i]=mic_logic_edge_report[i];
  __DMB();mic_logic_edge_report[11]=ld_crc(v,11);
}
static void gpio_low(void){
  HAL_GPIO_WritePin(GPIOC,ALL_PINS,GPIO_PIN_RESET);
  GPIO_InitTypeDef g={0};g.Pin=ALL_PINS;g.Mode=GPIO_MODE_OUTPUT_PP;
  g.Pull=GPIO_NOPULL;g.Speed=GPIO_SPEED_FREQ_VERY_HIGH;HAL_GPIO_Init(GPIOC,&g);
}
void mic_edges_init(void){
  __HAL_RCC_GPIOC_CLK_ENABLE();__HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_TIM8_CLK_ENABLE();__HAL_RCC_TIM8_FORCE_RESET();__HAL_RCC_TIM8_RELEASE_RESET();
  gpio_low();
  GPIO_InitTypeDef g={0};g.Pin=GPIO_PIN_2;g.Mode=GPIO_MODE_AF_PP;
  g.Alternate=GPIO_AF4_TIM8;g.Pull=GPIO_NOPULL;g.Speed=GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOD,&g);
  TIM8->CR1=TIM1->CR1&(TIM_CR1_CMS|TIM_CR1_CKD|TIM_CR1_ARPE);
  TIM8->PSC=TIM1->PSC;TIM8->ARR=TIM1->ARR;TIM8->RCR=TIM1->RCR;
  TIM8->CCMR1=EDGE_PWM12;TIM8->CCMR2=EDGE_PWM3;TIM8->CCER=EDGE_CC;
  TIM8->CCR1=TIM8->CCR2=TIM8->CCR3=0;
  TIM8->AF1=TIM1_AF1_BKINE; /* No input inversion. */
  /* BKP=0: active LOW; BKF=0: asynchronous; AOE=0: never auto rearm.
   * LOCK1 protects the auxiliary break configuration until reset. */
  TIM8->BDTR=(TIM1->BDTR&TIM_BDTR_DTG)|TIM_BDTR_BKE|
    TIM_BDTR_OSSI|TIM_BDTR_OSSR|TIM_BDTR_LOCK_0;
  TIM8->EGR=TIM_EGR_UG;TIM8->SR=0;
  for(unsigned i=0;i<12;i++)mic_logic_edge_report[i]=0;
  mic_logic_edge_report[0]=0x3147454cU;mic_logic_edge_report[1]=LD_BUILD;seal();
}
uint32_t mic_edges_guard(void){
  const uint32_t flags=mic_logic_edge_report[10];
  const bool on=(flags&3U)==1U;
  if(!(GPIOA->IDR&GPIO_PIN_6)||!(GPIOD->IDR&GPIO_PIN_2)||(TIM8->SR&TIM_SR_BIF))return EDGE_BAD;
  if((GPIOD->MODER&(3U<<4))!=(2U<<4)||(GPIOD->AFR[0]&(15U<<8))!=(4U<<8))return EDGE_BAD;
  if((TIM8->BDTR&~TIM_BDTR_MOE)!=((TIM1->BDTR&TIM_BDTR_DTG)|TIM_BDTR_BKE|
      TIM_BDTR_OSSI|TIM_BDTR_OSSR|TIM_BDTR_LOCK_0)||TIM8->AF1!=TIM1_AF1_BKINE)return EDGE_BAD;
  if(TIM8->DIER||TIM8->SMCR||TIM8->CCER!=EDGE_CC||TIM8->CCMR1!=EDGE_PWM12||TIM8->CCMR2!=EDGE_PWM3)return EDGE_BAD;
  if(TIM8->PSC!=TIM1->PSC||TIM8->ARR!=TIM1->ARR||TIM8->RCR!=TIM1->RCR)return EDGE_BAD;
  if((TIM8->CR1&~(TIM_CR1_CEN|TIM_CR1_DIR))!=(TIM1->CR1&(TIM_CR1_CMS|TIM_CR1_CKD|TIM_CR1_ARPE)))return EDGE_BAD;
  if((GPIOC->MODER&EDGE_MODES)!=(on?EDGE_AF:EDGE_GPIO))return EDGE_BAD;
  if(on){
    if(!(TIM8->BDTR&TIM_BDTR_MOE)||!(TIM8->CR1&TIM_CR1_CEN)||(TIM8->SR&TIM_SR_BIF))return EDGE_BAD;
    if((GPIOC->AFR[0]&0xff000000U)!=0x44000000U||(GPIOC->AFR[1]&15U)!=4U)return EDGE_BAD;
  }else if((TIM8->BDTR&TIM_BDTR_MOE)||(TIM8->CR1&TIM_CR1_CEN)||(GPIOC->ODR&ALL_PINS))return EDGE_BAD;
  return 0;
}
void mic_edges_begin(void){
  uint32_t reads,errors;mic_encoder_load_counters(&reads,&errors);
  mic_logic_edge_report[4]=reads;mic_logic_edge_report[5]=errors;seal();
}
bool mic_edges_update(uint32_t elapsed,uint32_t hz){
  if(mic_edges_guard())return false;
  TIM8->CCR1=TIM1->CCR1;TIM8->CCR2=TIM1->CCR2;TIM8->CCR3=TIM1->CCR3;
  if(elapsed<2U*hz)return true;
  if(!mic_logic_edge_report[10]){
    uint32_t reads,errors;mic_encoder_load_counters(&reads,&errors);
    mic_logic_edge_report[6]=reads;mic_logic_edge_report[7]=errors;
    TIM8->EGR=TIM_EGR_UG;
    /* Do not clear a latched BKIN event and never rearm after it. */
    if(TIM8->SR&TIM_SR_BIF)return false;
    GPIO_InitTypeDef g={0};g.Pin=EDGE_PINS;g.Mode=GPIO_MODE_AF_PP;
    g.Alternate=GPIO_AF4_TIM8;g.Pull=GPIO_NOPULL;g.Speed=GPIO_SPEED_FREQ_VERY_HIGH;
    HAL_GPIO_Init(GPIOC,&g);
    HAL_GPIO_WritePin(GPIOC,GPIO_PIN_9,GPIO_PIN_SET);
    mic_logic_edge_report[2]=DWT->CYCCNT;mic_logic_edge_report[10]=1;
    TIM8->BDTR|=TIM_BDTR_MOE;TIM8->CR1|=TIM_CR1_CEN;seal();
    if(mic_edges_guard())return false;
  }
  return (mic_logic_edge_report[10]&3U)==1U;
}
void mic_edges_stop(bool fault){
  TIM8->BDTR&=~TIM_BDTR_MOE;TIM8->CR1&=~TIM_CR1_CEN;gpio_low();
  if(!(mic_logic_edge_report[10]&2U)){
    uint32_t reads,errors;mic_encoder_load_counters(&reads,&errors);
    mic_logic_edge_report[3]=DWT->CYCCNT;
    mic_logic_edge_report[8]=reads;mic_logic_edge_report[9]=errors;
    mic_logic_edge_report[10]|=2U|(fault?4U:0U);seal();
  }
}
