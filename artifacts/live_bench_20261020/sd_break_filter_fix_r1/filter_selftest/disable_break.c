
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include "stm32g4xx_hal.h"
#include "stm32g4xx_ll_tim.h"
static TIM_TypeDef timer;
static GPIO_TypeDef gpio;
#undef TIM1
#undef GPIOA
#define TIM1 (&timer)
#define GPIOA (&gpio)
#define TIM_CLOCK_DIVIDER 1
#define PWM_PERIOD_CYCLES 10624
#define REP_COUNTER 1
#define HTMIN 1
#define DEAD_TIME_COUNTS 270
static TIM_HandleTypeDef htim1;
static TIM_BreakDeadTimeConfigTypeDef saved;
static TIMEx_BreakInputConfigTypeDef input;
static void Error_Handler(void) {exit(3);}
HAL_StatusTypeDef HAL_TIM_Base_Init(TIM_HandleTypeDef *h) {timer.CR1=h->Init.ClockDivision;return HAL_OK;}
HAL_StatusTypeDef HAL_TIM_PWM_Init(TIM_HandleTypeDef *h) {(void)h;return HAL_OK;}
HAL_StatusTypeDef HAL_TIM_SlaveConfigSynchro(TIM_HandleTypeDef *h,const TIM_SlaveConfigTypeDef *c) {(void)h;(void)c;return HAL_OK;}
HAL_StatusTypeDef HAL_TIMEx_MasterConfigSynchronization(TIM_HandleTypeDef *h,const TIM_MasterConfigTypeDef *c) {(void)h;(void)c;return HAL_OK;}
HAL_StatusTypeDef HAL_TIMEx_ConfigBreakInput(TIM_HandleTypeDef *h,uint32_t brk,const TIMEx_BreakInputConfigTypeDef *c) {(void)h;(void)brk;input=*c;return HAL_OK;}
HAL_StatusTypeDef HAL_TIM_PWM_ConfigChannel(TIM_HandleTypeDef *h,const TIM_OC_InitTypeDef *c,uint32_t ch) {(void)h;(void)c;(void)ch;return HAL_OK;}
HAL_StatusTypeDef HAL_TIMEx_ConfigBreakDeadTime(TIM_HandleTypeDef *h,const TIM_BreakDeadTimeConfigTypeDef *c) {(void)h;saved=*c;return HAL_OK;}
void HAL_TIM_MspPostInit(TIM_HandleTypeDef *h) {(void)h;}
static void MX_TIM1_Init(void)
{

  /* USER CODE BEGIN TIM1_Init 0 */

  /* USER CODE END TIM1_Init 0 */

  TIM_SlaveConfigTypeDef sSlaveConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};
  TIMEx_BreakInputConfigTypeDef sBreakInputConfig = {0};
  TIM_OC_InitTypeDef sConfigOC = {0};
  TIM_BreakDeadTimeConfigTypeDef sBreakDeadTimeConfig = {0};

  /* USER CODE BEGIN TIM1_Init 1 */

  /* USER CODE END TIM1_Init 1 */
  htim1.Instance = TIM1;
  htim1.Init.Prescaler = ((TIM_CLOCK_DIVIDER) - 1);
  htim1.Init.CounterMode = TIM_COUNTERMODE_CENTERALIGNED1;
  htim1.Init.Period = ((PWM_PERIOD_CYCLES) / 2);
  htim1.Init.ClockDivision = TIM_CLOCKDIVISION_DIV2;
  htim1.Init.RepetitionCounter = (REP_COUNTER);
  htim1.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim1) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_Init(&htim1) != HAL_OK)
  {
    Error_Handler();
  }
  sSlaveConfig.SlaveMode = TIM_SLAVEMODE_TRIGGER;
  sSlaveConfig.InputTrigger = TIM_TS_ITR1;
  if (HAL_TIM_SlaveConfigSynchro(&htim1, &sSlaveConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_OC4REF;
  sMasterConfig.MasterOutputTrigger2 = TIM_TRGO2_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim1, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sBreakInputConfig.Source = TIM_BREAKINPUTSOURCE_BKIN;
  sBreakInputConfig.Enable = TIM_BREAKINPUTSOURCE_ENABLE;
  sBreakInputConfig.Polarity = TIM_BREAKINPUTSOURCE_POLARITY_LOW;
  if (HAL_TIMEx_ConfigBreakInput(&htim1, TIM_BREAKINPUT_BRK, &sBreakInputConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sConfigOC.OCMode = TIM_OCMODE_PWM1;
  sConfigOC.Pulse = ((PWM_PERIOD_CYCLES) / 4);
  sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
  sConfigOC.OCNPolarity = TIM_OCNPOLARITY_HIGH;
  sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;
  sConfigOC.OCIdleState = TIM_OCIDLESTATE_RESET;
  sConfigOC.OCNIdleState = TIM_OCNIDLESTATE_RESET;
  if (HAL_TIM_PWM_ConfigChannel(&htim1, &sConfigOC, TIM_CHANNEL_1) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_ConfigChannel(&htim1, &sConfigOC, TIM_CHANNEL_2) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_ConfigChannel(&htim1, &sConfigOC, TIM_CHANNEL_3) != HAL_OK)
  {
    Error_Handler();
  }
  sConfigOC.OCMode = TIM_OCMODE_PWM2;
  sConfigOC.Pulse = (((PWM_PERIOD_CYCLES) / 2) - (HTMIN));
  if (HAL_TIM_PWM_ConfigChannel(&htim1, &sConfigOC, TIM_CHANNEL_4) != HAL_OK)
  {
    Error_Handler();
  }
  sBreakDeadTimeConfig.OffStateRunMode = TIM_OSSR_ENABLE;
  sBreakDeadTimeConfig.OffStateIDLEMode = TIM_OSSI_ENABLE;
  sBreakDeadTimeConfig.LockLevel = TIM_LOCKLEVEL_OFF;
  sBreakDeadTimeConfig.DeadTime = ((DEAD_TIME_COUNTS) / 2);
  sBreakDeadTimeConfig.BreakState = TIM_BREAK_DISABLE;
  sBreakDeadTimeConfig.BreakPolarity = TIM_BREAKPOLARITY_HIGH;
  /* BKF=9: fDTS/8, eight consecutive samples. With TIM1=170 MHz,
   * CKD=2 this is 659..753 ns qualification (sampling phase dependent).
   * Reject sub-600 ns SD disturbances; retain BKE and hardware IPM shutdown.
   * This intentionally adds <1 us to MCU Break, not to internal IPM protection.
   * Do not replace by software debounce or automatic restart after a fault. */
  sBreakDeadTimeConfig.BreakFilter =
      LL_TIM_BREAK_FILTER_FDIV8_N8 >> TIM_BDTR_BKF_Pos;
  sBreakDeadTimeConfig.BreakAFMode = TIM_BREAK_AFMODE_INPUT;
  sBreakDeadTimeConfig.Break2State = TIM_BREAK2_DISABLE;
  sBreakDeadTimeConfig.Break2Polarity = TIM_BREAK2POLARITY_HIGH;
  sBreakDeadTimeConfig.Break2Filter = 3;
  sBreakDeadTimeConfig.Break2AFMode = TIM_BREAK_AFMODE_INPUT;
  sBreakDeadTimeConfig.AutomaticOutput = TIM_AUTOMATICOUTPUT_DISABLE;
  if (HAL_TIMEx_ConfigBreakDeadTime(&htim1, &sBreakDeadTimeConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM1_Init 2 */

  /* USER CODE END TIM1_Init 2 */
  HAL_TIM_MspPostInit(&htim1);

}
static bool config_ok(void) {  const bool sd_config_ok =
      ((GPIOA->MODER >> 12U) & 3U) == 2U &&
      (GPIOA->OTYPER & GPIO_PIN_6) != 0U &&
      ((GPIOA->PUPDR >> 12U) & 3U) == 1U &&
      ((GPIOA->AFR[0] >> 24U) & 15U) == 6U &&
      (TIM1->AF1 & (TIM1_AF1_BKINE | TIM1_AF1_BKINP)) ==
          (TIM1_AF1_BKINE | TIM1_AF1_BKINP) &&
      (TIM1->BDTR & (TIM_BDTR_BKE | TIM_BDTR_BKP | TIM_BDTR_BKBID)) ==
          (TIM_BDTR_BKE | TIM_BDTR_BKP) &&
      (TIM1->BDTR & TIM_BDTR_BKF) == LL_TIM_BREAK_FILTER_FDIV8_N8 &&
      (TIM1->CR1 & TIM_CR1_CKD) == TIM_CLOCKDIVISION_DIV2 &&
      (TIM1->BDTR & TIM_BDTR_AOE) == 0U;
  return sd_config_ok;}
#define CHECK(v) do {if(!(v)){fprintf(stderr,"FAIL line %d\n",__LINE__);return 1;}}while(0)
int main(void) {
  MX_TIM1_Init();
  CHECK(saved.BreakFilter==9);
  CHECK(saved.BreakState==TIM_BREAK_ENABLE);
  CHECK(saved.BreakPolarity==TIM_BREAKPOLARITY_HIGH);
  CHECK(saved.BreakAFMode==TIM_BREAK_AFMODE_INPUT);
  CHECK(saved.AutomaticOutput==TIM_AUTOMATICOUTPUT_DISABLE);
  CHECK(saved.Break2State==TIM_BREAK2_DISABLE);
  CHECK(htim1.Init.ClockDivision==TIM_CLOCKDIVISION_DIV2);
  CHECK(input.Source==TIM_BREAKINPUTSOURCE_BKIN && input.Enable==TIM_BREAKINPUTSOURCE_ENABLE);
  CHECK(input.Polarity==TIM_BREAKINPUTSOURCE_POLARITY_LOW);
  timer.BDTR=TIM_BDTR_BKE|TIM_BDTR_BKP|LL_TIM_BREAK_FILTER_FDIV8_N8;
  timer.AF1=TIM1_AF1_BKINE|TIM1_AF1_BKINP;
  gpio.MODER=2U<<12;gpio.OTYPER=GPIO_PIN_6;gpio.PUPDR=1U<<12;gpio.AFR[0]=6U<<24;
  CHECK(config_ok());
  const uint32_t bdtr=timer.BDTR;
  timer.BDTR=bdtr^TIM_BDTR_BKE;CHECK(!config_ok());
  timer.BDTR=bdtr^TIM_BDTR_BKP;CHECK(!config_ok());
  timer.BDTR=bdtr|TIM_BDTR_AOE;CHECK(!config_ok());
  timer.BDTR=bdtr|TIM_BDTR_BKBID;CHECK(!config_ok());
  for(unsigned f=0;f<16;++f){timer.BDTR=(bdtr&~TIM_BDTR_BKF)|(f<<TIM_BDTR_BKF_Pos);CHECK(config_ok()==(f==9));}
  timer.BDTR=bdtr;timer.CR1=TIM_CLOCKDIVISION_DIV1;CHECK(!config_ok());
  timer.CR1=TIM_CLOCKDIVISION_DIV4;CHECK(!config_ok());
  timer.CR1=TIM_CLOCKDIVISION_DIV2;CHECK(config_ok());
  puts("PASS actual TIM1 init + live register predicate");return 0;
}
