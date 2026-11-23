#pragma once
#include <stdint.h>
#include <stdbool.h>
struct FakeADC {uint32_t CR,CFGR,SQR1,ISR,DR;};
struct FakeGPIO {uint32_t IDR;};struct FakeDWT {uint32_t CYCCNT;};
static FakeADC adc2;static FakeGPIO gpioa;static FakeDWT dwt;
#define ADC2 (&adc2)
#define GPIOA (&gpioa)
#define GPIOB ((void*)1)
#define TIM1 ((void*)2)
#define DWT (&dwt)
#define ADC_CR_ADEN 1U
#define ADC_CFGR_EXTEN 0x30U
#define ADC_CFGR_DMAEN 1U
#define ADC_CFGR_CONT 2U
#define ADC_SQR1_L 15U
#define ADC_SQR1_SQ1 (31U<<6)
#define ADC_SQR1_SQ1_Pos 6U
#define GPIO_PIN_6 64U
#define GPIO_PIN_11 2048U
#define GPIO_MODE_ANALOG 3U
#define GPIO_NOPULL 0U
#define LL_ADC_REG_SEQ_SCAN_DISABLE 0U
#define LL_ADC_REG_RANK_1 1U
#define LL_ADC_CHANNEL_14 14U
#define LL_ADC_REG_TRIG_SOFTWARE 0U
#define LL_ADC_SAMPLINGTIME_247CYCLES_5 6U
#define __HAL_RCC_GPIOB_CLK_ENABLE() ((void)0)
#define MIC_NUCLEO_FW_BUILD_ID 2026103102U
#define UNO_TX_TAG_DIAG 0U
#define HAL_OK 0
typedef struct {uint32_t Pin,Mode,Pull;} GPIO_InitTypeDef;
static uint32_t tick,starts,stops,gpio_init_pin,gpio_init_mode,gpio_init_pull,submits,last_seq;
static bool tim_moe,mic_last_control_reply_safe_off=true;
static struct {bool command_enabled;} uno_link;
static struct {uint32_t head,tail,hard_error;} mic_uart_tx;
static uint32_t HAL_GetTick(){return tick;}
static void HAL_GPIO_Init(void*,GPIO_InitTypeDef*p){gpio_init_pin=p->Pin;gpio_init_mode=p->Mode;gpio_init_pull=p->Pull;}
static void LL_ADC_REG_SetSequencerLength(FakeADC*a,uint32_t n){a->SQR1=n;}
static void LL_ADC_REG_SetSequencerRanks(FakeADC*a,uint32_t,uint32_t c){a->SQR1=c<<6;}
static void LL_ADC_REG_SetTriggerSource(FakeADC*a,uint32_t){a->CFGR&=~ADC_CFGR_EXTEN;}
static void LL_ADC_SetChannelSamplingTime(FakeADC*,uint32_t c,uint32_t){if(c!=14)__builtin_abort();}
static bool LL_ADC_REG_IsConversionOngoing(FakeADC*a){return (a->CR&2)!=0;}
static void LL_ADC_REG_StopConversion(FakeADC*a){++stops;a->CR&=~2U;}
static void LL_ADC_REG_StartConversion(FakeADC*a){++starts;a->CR|=2;}
static bool LL_ADC_IsActiveFlag_EOC(FakeADC*a){return (a->ISR&1)!=0;}
static bool LL_ADC_IsActiveFlag_OVR(FakeADC*a){return (a->ISR&4)!=0;}
static void LL_ADC_ClearFlag_EOC(FakeADC*a){a->ISR&=~1U;}
static void LL_ADC_ClearFlag_EOS(FakeADC*a){a->ISR&=~2U;}
static void LL_ADC_ClearFlag_OVR(FakeADC*a){a->ISR&=~4U;}
static bool LL_TIM_IsEnabledAllOutputs(void*){return tim_moe;}
static int uno_tx_submit(uint8_t*p,unsigned){++submits;last_seq=(uint32_t)p[10]|((uint32_t)p[11]<<8)|((uint32_t)p[12]<<16)|((uint32_t)p[13]<<24);return HAL_OK;}
