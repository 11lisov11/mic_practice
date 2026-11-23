/* Observation and additional fail-stop guards; never writes PWM/ADC/UART registers. */
#include "main.h"
#include "pin_pwm_diag.h"
#include "combined_io_diag.h"
#include "load_core.h"
volatile uint32_t mic_io_report[40];
static volatile uint32_t adc_seen,adc_active,adc_at,adc_enter,adc_cost,adc_gap,adc_bad;
static uint32_t adc_previous,sequence,publish_ms,uart_flags,uart_at,uart_frames,uart_completed;
void mic_io_init(void){publish_ms=HAL_GetTick()-50U;}
void mic_io_adc_enter(void){
 uint32_t now=DWT->CYCCNT;
 if(adc_previous){uint32_t g=now-adc_previous;if(g>adc_gap)adc_gap=g;}
 adc_previous=adc_at=adc_enter=now;++adc_seen;if(mic_pin_active())++adc_active;
 if(((ADC1->ISR|ADC2->ISR)&ADC_ISR_JQOVF)||!(ADC2->ISR&ADC_ISR_JEOS))++adc_bad;
}
void mic_io_adc_exit(void){uint32_t cost=DWT->CYCCNT-adc_enter;if(cost>adc_cost)adc_cost=cost;}
uint32_t mic_io_guard(void){
 const uint32_t stamp=adc_at,seen=adc_seen,now=DWT->CYCCNT;
 uint32_t bad=0;
 if(seen<100 || (uint32_t)(now-stamp)>SystemCoreClock/200U || adc_bad)bad|=256U;
 if(uart_flags || !uart_frames || !uart_completed || (uint32_t)(HAL_GetTick()-uart_at)>300U)bad|=512U;
 return bad;
}
void mic_io_poll(void){
 uint32_t u[16];mic_io_uart_snapshot(u);
 uart_flags=u[15];uart_at=u[13];uart_frames=u[2];uart_completed=u[6];
 uint32_t ms=HAL_GetTick();if((uint32_t)(ms-publish_ms)<50U)return;publish_ms=ms;
 uint32_t v[40]={0};v[0]=0x314f4943U;v[1]=2026102801U;v[2]=1;v[3]=40;
 v[5]=adc_seen;v[6]=adc_active;v[7]=adc_at;v[8]=adc_cost;v[9]=adc_gap;v[10]=adc_bad;
 v[11]=ADC1->CR;v[12]=ADC2->CR;v[13]=ADC1->ISR;v[14]=ADC2->ISR;
 v[15]=ADC1->JSQR;v[16]=ADC2->JSQR;v[17]=TIM1->CCR4;
 for(unsigned i=0;i<16;i++)v[18+i]=u[i];
 v[34]=RCC->CCIPR;v[35]=mic_io_guard();v[36]=SystemCoreClock;
 sequence+=2;v[4]=v[37]=sequence;v[38]=ld_crc(v+5,32);v[39]=0x43494f45U;
 mic_io_report[4]=sequence|1U;__DMB();for(unsigned i=0;i<40;i++)if(i!=4)mic_io_report[i]=v[i];__DMB();mic_io_report[4]=sequence;
}
