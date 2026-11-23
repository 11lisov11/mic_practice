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
