#pragma once
#include <stdint.h>
#include <stdbool.h>
struct IsrReg {uint32_t value=1;operator uint32_t()const{return value;}void operator=(uint32_t v){if(v&1U)value|=1U;}};
struct IcrReg {IsrReg*isr;uint32_t last=0;void operator=(uint32_t v){last=v;isr->value&=~v;}};
struct I2cRegs {uint32_t CR1=0,CR2=0,TIMINGR=0;IsrReg ISR;IcrReg ICR{&ISR};uint32_t OAR1=0,OAR2=0,TXDR=0,RXDR=0;};
static void mock_bsrr(uint32_t);
struct BsrrReg {void operator=(uint32_t v){mock_bsrr(v);}};
struct GpioRegs {uint32_t IDR=0,MODER=0,OTYPER=0,AFR[2]={},ODR=0;BsrrReg BSRR;};
typedef struct {uint32_t BDTR,CNT,CR1,ARR,CCR1,CCR2,CCR3;} TimRegs;
typedef struct {uint32_t CR,CCIPR,CFGR;} RccRegs;
typedef struct {uint32_t CYCCNT,CTRL;} DwtRegs;
typedef struct {uint32_t DEMCR;} DebugRegs;
static I2cRegs test_i2c;
static GpioRegs test_gpio;
static TimRegs test_tim;
static RccRegs test_rcc;
static DwtRegs test_dwt;
static DebugRegs test_debug;
#define I2C1 (&test_i2c)
#define GPIOB (&test_gpio)
#define TIM1 (&test_tim)
#define RCC (&test_rcc)
#define DWT (&test_dwt)
#define CoreDebug (&test_debug)
#define CoreDebug_DEMCR_TRCENA_Msk 0x1000000U
#define DWT_CTRL_CYCCNTENA_Msk 1U
#define I2C_CR1_PE 1U
#define I2C_CR1_DNF_Pos 8U
#define I2C_CR1_DNF (15U<<8)
#define I2C_CR1_ANFOFF (1U<<12)
#define I2C_ICR_NACKCF 16U
#define I2C_ICR_STOPCF 32U
#define I2C_ICR_BERRCF 256U
#define I2C_ICR_ARLOCF 512U
#define I2C_ICR_OVRCF 1024U
#define RCC_CR_HSIRDY 2U
#define RCC_CCIPR_I2C1SEL (3U<<12)
#define RCC_CCIPR_I2C1SEL_1 (2U<<12)
#define GPIO_PIN_8 256U
#define GPIO_PIN_9 512U
#define GPIO_MODE_AF_OD 1U
#define GPIO_NOPULL 0U
#define GPIO_SPEED_FREQ_LOW 0U
#define GPIO_AF4_I2C1 4U
static unsigned mock_pe_enables,mock_pe_disables;
static inline void mock_set(uint32_t*r,uint32_t b){if(r==&test_i2c.CR1&&(b&1))++mock_pe_enables;*r|=b;}
#define SET_BIT(r,b) mock_set(&(r),(b))
static bool mock_release_scl;
static inline void mock_clear(uint32_t*r,uint32_t b){if(r==&test_i2c.CR1&&(b&1))++mock_pe_disables;*r&=~b;if(r==&test_i2c.CR1&&(b&I2C_CR1_PE)){test_i2c.ISR.value=1;test_i2c.CR2&=~0x400e000U;if(mock_release_scl)test_gpio.IDR|=256;}}
#define CLEAR_BIT(r,b) mock_clear(&(r),(b))
#define MODIFY_REG(r,c,s) ((r)=((r)&~(c))|(s))
#define __DSB() ((void)0)
#define __HAL_RCC_GPIOB_CLK_ENABLE() ((void)0)
#define __HAL_RCC_I2C1_CLK_ENABLE() ((void)0)
typedef struct {uint32_t Pin,Mode,Pull,Speed,Alternate;} GPIO_InitTypeDef;
static inline void HAL_GPIO_Init(GpioRegs*g,GPIO_InitTypeDef*v){(void)v;g->MODER=10U<<16;g->OTYPER=0x300;g->AFR[1]=0x44;}
static uint32_t test_tick;
static uint32_t SystemCoreClock=170000000;
static inline uint32_t HAL_GetTick(void){return test_tick;}

#define I2C_ISR_TXE 1U
#define I2C_CR2_START (1U<<13)
#define I2C_CR2_STOP (1U<<14)

#define TIM_BDTR_MOE 32768U
static unsigned mock_gpio_writes,mock_edges,mock_release_on=4;static bool mock_external_sda;
static void mock_bsrr(uint32_t v){++mock_gpio_writes;uint32_t old=test_gpio.ODR;test_gpio.ODR=(old|(v&65535U))&~(v>>16);if((test_gpio.MODER&(15U<<16))==(5U<<16)){if(!(old&256U)&&(test_gpio.ODR&256U)&&++mock_edges>=mock_release_on)mock_external_sda=false;test_gpio.IDR=(test_gpio.IDR&~0x300U)|(test_gpio.ODR&256U)|((!mock_external_sda&&(test_gpio.ODR&512U))?512U:0U);}}

#include <cstring>
#define __DMB() ((void)0)
typedef struct {uint32_t CR1,CR2,DIER,PSC,ARR,CNT,EGR,SR;} WireTimer;
typedef struct {uint32_t CCR,CNDTR,CPAR,CMAR;} WireDmaChannel;
typedef struct {uint32_t ISR,IFCR;} WireDma;
[[maybe_unused]] static WireTimer mock_tim4;
[[maybe_unused]] static WireDmaChannel mock_ch4;
[[maybe_unused]] static WireDma mock_dma2;
#define TIM4 (&mock_tim4)
#define DMA2_Channel4 (&mock_ch4)
#define DMA2 (&mock_dma2)
#define TIM_CR1_CEN 1U
#define TIM_DIER_UDE 256U
#define TIM_EGR_UG 1U
#define DMA_CCR_EN 1U
#define DMA_CCR_HTIE 4U
#define DMA_CCR_TCIE 2U
#define DMA_CCR_TEIE 8U
#define DMA_REQUEST_TIM4_UP 71U
#define DMA_PERIPH_TO_MEMORY 0U
#define DMA_PINC_DISABLE 0U
#define DMA_MINC_ENABLE 128U
#define DMA_PDATAALIGN_WORD 512U
#define DMA_MDATAALIGN_HALFWORD 1024U
#define DMA_CIRCULAR 32U
#define DMA_PRIORITY_LOW 0U
#define __HAL_RCC_TIM4_CLK_ENABLE() ((void)0)
#define __HAL_RCC_DMA2_CLK_ENABLE() ((void)0)
#define RCC_HCLK_DIV1 0U
#define HAL_OK 0U
typedef struct {uint32_t APB1CLKDivider;} RCC_ClkInitTypeDef;
typedef struct {uint32_t Request,Direction,PeriphInc,MemInc,PeriphDataAlignment,MemDataAlignment,Mode,Priority;} WireDmaInit;
typedef struct {WireDmaChannel*Instance;WireDmaInit Init;} DMA_HandleTypeDef;
static uint32_t mock_wire_hz=170000000U;static bool mock_dma_fail;
static DMA_HandleTypeDef mock_dma_init;
static inline void HAL_RCC_GetClockConfig(RCC_ClkInitTypeDef*c,uint32_t*l){c->APB1CLKDivider=RCC_HCLK_DIV1;*l=0;}
static inline uint32_t HAL_RCC_GetPCLK1Freq(){return mock_wire_hz;}
static inline unsigned HAL_DMA_Init(DMA_HandleTypeDef*d){mock_dma_init=*d;return mock_dma_fail?1U:0U;}
static inline unsigned HAL_DMA_Start(DMA_HandleTypeDef*d,uint32_t p,uint32_t m,uint32_t n){
  if(mock_dma_fail)return 1;
  d->Instance->CNDTR=n;d->Instance->CPAR=p;d->Instance->CMAR=m;
  d->Instance->CCR=DMA_CCR_EN|DMA_CIRCULAR|DMA_MINC_ENABLE|DMA_PDATAALIGN_WORD|DMA_MDATAALIGN_HALFWORD;
  return 0;
}
