#include "main.h"
#include "nucleo_encoder.h"
#include "encoder_core.h"
#include "encoder_wire.h"
#include "stm32g4xx_ll_i2c.h"

static ec_state enc;
static uint8_t sequence;
/* HSI16, PRESC=3, SCLDEL=5, SDADEL=2, SCLH=19, SCLL=23.
   Conservative standard-mode timing, ANF on/DNF2. Nominal under100kHz;
   physical edge timing still needs bench qualification. */
#define MIC_ENC_TIMING 0x30521317U
static uint32_t status(void*x){(void)x;return I2C1->ISR;}
static void clear(void*x){(void)x;I2C1->ICR=I2C_ICR_NACKCF|I2C_ICR_STOPCF|I2C_ICR_BERRCF|I2C_ICR_ARLOCF|I2C_ICR_OVRCF;}
static void reset(void*x){
  (void)x;CLEAR_BIT(I2C1->CR1,I2C_CR1_PE);(void)I2C1->CR1;
  __DSB();I2C1->CR2=0;clear(0);SET_BIT(I2C1->CR1,I2C_CR1_PE);
}
static void begin_write(void*x){(void)x;LL_I2C_HandleTransfer(I2C1,0x6c,LL_I2C_ADDRSLAVE_7BIT,1,LL_I2C_MODE_SOFTEND,LL_I2C_GENERATE_START_WRITE);}
static void write_byte(void*x,uint8_t v){(void)x;LL_I2C_TransmitData8(I2C1,v);}
static void begin_read(void*x){(void)x;LL_I2C_HandleTransfer(I2C1,0x6c,LL_I2C_ADDRSLAVE_7BIT,3,LL_I2C_MODE_AUTOEND,LL_I2C_GENERATE_START_READ);}
static uint8_t read_byte(void*x){(void)x;return LL_I2C_ReceiveData8(I2C1);}
static ec_io io={0,status,begin_write,write_byte,begin_read,read_byte,clear,reset};
static bool config_ok(void){
  return enc.configured && (GPIOB->MODER&(15U<<16))==(10U<<16) &&
      (GPIOB->OTYPER&(3U<<8))==(3U<<8) &&
      (GPIOB->AFR[1]&255U)==0x44U && (I2C1->CR1&I2C_CR1_PE)!=0 &&
      I2C1->TIMINGR==MIC_ENC_TIMING;
}
void mic_encoder_init(void){
  /* Only this peripheral clock mux; no SYSCLK/PWM/ADC clock changes. */
  bool ready=(RCC->CR&RCC_CR_HSIRDY)!=0;
  if(ready){
    __HAL_RCC_GPIOB_CLK_ENABLE();__HAL_RCC_I2C1_CLK_ENABLE();
    MODIFY_REG(RCC->CCIPR,RCC_CCIPR_I2C1SEL,RCC_CCIPR_I2C1SEL_1);
    CLEAR_BIT(I2C1->CR1,I2C_CR1_PE);
    GPIO_InitTypeDef g={0};g.Pin=GPIO_PIN_8|GPIO_PIN_9;
    g.Mode=GPIO_MODE_AF_OD;g.Pull=GPIO_NOPULL;g.Speed=GPIO_SPEED_FREQ_LOW;g.Alternate=GPIO_AF4_I2C1;
    HAL_GPIO_Init(GPIOB,&g);
    I2C1->CR1=2U<<I2C_CR1_DNF_Pos;I2C1->TIMINGR=MIC_ENC_TIMING;
    I2C1->CR2=0;I2C1->OAR1=0;I2C1->OAR2=0;
    clear(0);SET_BIT(I2C1->CR1,I2C_CR1_PE);
    CoreDebug->DEMCR|=CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CTRL|=DWT_CTRL_CYCCNTENA_Msk; /* Never reset an existing counter. */
  }
  ec_init(&enc,SystemCoreClock,ready);
  enc.configured=config_ok()?1:0;
  if(!enc.configured)enc.cause=EC_SETUP;
}
void mic_encoder_poll(void){
  if(enc.configured && !config_ok()){
    enc.configured=0;enc.cause=EC_SETUP;enc.bus_ok=false;enc.angle_ok=false;ec_speed_reset(&enc);
  }
  ec_poll(&enc,&io,HAL_GetTick(),DWT->CYCCNT,SystemCoreClock);
}
void mic_encoder_packet(uint8_t*p,uint32_t fw){
  memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=EW_VERSION;p[4]=sequence++;
  uint32_t age=HAL_GetTick()-enc.sample_ms;
  bool fresh=(enc.reads||enc.errors) && age<EW_TTL_MS;
  p[3]=(uint8_t)((fresh&&enc.bus_ok?1U:0U)|(fresh&&enc.angle_ok?2U:0U)|
      (fresh&&enc.speed_ok?4U:0U)|(config_ok()?8U:0U));
  p[5]=enc.cause;ew_p32(p+6,fw);ew_p16(p+10,(uint16_t)(age>65535U?65535U:age));
  p[12]=enc.status;p[13]=enc.stage;ew_p16(p+14,enc.raw);
  float rpm=enc.rpm;if(rpm>32767)rpm=32767;if(rpm< -32767)rpm=-32767;
  ew_p16(p+16,(uint16_t)(int16_t)(rpm+(rpm>=0?0.5f:-0.5f)));
  ew_p32(p+18,enc.reads);ew_p32(p+22,enc.errors);ew_p16(p+26,enc.timeouts);
  ew_p16(p+28,enc.resets);ew_p32(p+30,enc.last_isr);ew_p16(p+34,enc.duration_us);
  p[36]=(uint8_t)((GPIOB->IDR>>8)&3U);p[37]=(uint8_t)(I2C1->CR1&1U);p[38]=EW_FORMAT;
  uv3_seal(p);
}
