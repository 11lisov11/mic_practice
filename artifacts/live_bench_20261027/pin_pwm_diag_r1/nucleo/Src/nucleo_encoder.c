#include "main.h"
#include "nucleo_encoder.h"
#include "encoder_core.h"
#include "encoder_wire.h"
#include "fault_wire.h"
#include "release_wire.h"
static sr_probe release_probe[2];
static uint32_t release_park_cycles[2];
static uint8_t release_pending;
static sr_sample release_peek(void){
  sr_sample s;
  s.isr=I2C1->ISR;s.cr1=I2C1->CR1;s.cr2=I2C1->CR2;s.gpio=GPIOB->IDR;
  s.cycles=DWT->CYCCNT; /* Actual end of sequential MMIO reads, not scheduled time. */
  return s;
}
static void release_after_park(uint32_t pe_cycles){
  sr_sample s=release_peek();
  for(unsigned slot=0;slot<2;slot++)if(release_pending&(1U<<slot)){
    release_park_cycles[slot]=pe_cycles;sr_after_park(&release_probe[slot],s);
  }
  release_pending=0;
}
static void release_poll(void){
  if(!release_probe[0].active&&!release_probe[1].active)return;
  sr_sample s=release_peek();
  for(unsigned slot=0;slot<2;slot++)sr_poll(&release_probe[slot],s,SystemCoreClock);
}

#include "stm32g4xx_ll_i2c.h"

static ec_state enc;
static uint8_t sequence;
/* HSI16, PRESC=3, SCLDEL=5, SDADEL=2, SCLH=19, SCLL=23.
   Conservative standard-mode timing, ANF on/DNF2. Nominal under100kHz;
   physical edge timing still needs bench qualification. */
#define MIC_ENC_TIMING 0x30521317U
static uint32_t status(void*x){(void)x;return I2C1->ISR;}
static void clear(void*x){(void)x;I2C1->ICR=I2C_ICR_NACKCF|I2C_ICR_STOPCF|I2C_ICR_BERRCF|I2C_ICR_ARLOCF|I2C_ICR_OVRCF;}
static void capture_terminal(void*,uint8_t);
static void capture_before_reset(void*,uint8_t,uint32_t,uint32_t,uint32_t);
static uint8_t lines(void*x){(void)x;return (uint8_t)((GPIOB->IDR>>8)&3U);}
static void enable(void*x){(void)x;SET_BIT(I2C1->CR1,I2C_CR1_PE);(void)I2C1->CR1;__DSB();}
static void park(void*x){
  (void)x;CLEAR_BIT(I2C1->CR1,I2C_CR1_PE);(void)I2C1->CR1;__DSB();
  if(release_pending)release_after_park(DWT->CYCCNT);
  I2C1->CR2=0;
  // PE stays LOW until nonblocking preflight observes HIGH twice, >=2us
  // apart. This exceeds the RM0440 minimum of three APB clock cycles.
}
static void clear_berr(void*x){(void)x;I2C1->ICR=I2C_ICR_BERRCF;}
static void flush_tx(void*x){(void)x;I2C1->ISR=I2C_ISR_TXE;}
static void clear_nack(void*x){(void)x;I2C1->ICR=I2C_ICR_NACKCF;}
static bool stop_ready(void*x){(void)x;return (I2C1->CR2&(I2C_CR2_START|I2C_CR2_STOP))==0;}
static void request_stop(void*x){(void)x;SET_BIT(I2C1->CR2,I2C_CR2_STOP);}
static void reset(void*x){park(x);clear(x);flush_tx(x);}
static void completed(void*x){(void)x;I2C1->CR2=0;}
static void begin_write(void*x){(void)x;LL_I2C_HandleTransfer(I2C1,0x6c,LL_I2C_ADDRSLAVE_7BIT,1,LL_I2C_MODE_SOFTEND,LL_I2C_GENERATE_START_WRITE);}
static void write_byte(void*x,uint8_t v){(void)x;LL_I2C_TransmitData8(I2C1,v);}
static void begin_read(void*x){(void)x;LL_I2C_HandleTransfer(I2C1,0x6c,LL_I2C_ADDRSLAVE_7BIT,3,LL_I2C_MODE_AUTOEND,LL_I2C_GENERATE_START_READ);}
static uint8_t read_byte(void*x){(void)x;return LL_I2C_ReceiveData8(I2C1);}
static ec_io io={0,status,begin_write,write_byte,begin_read,read_byte,clear,reset,capture_before_reset,lines,enable,park,clear_berr,clear_nack,stop_ready,request_stop,flush_tx,capture_terminal,completed};
/* Main-loop diagnostics only. Never touches RXDR/TXDR, GPIO outputs, TIM1
   configuration, interrupt enables or any motor protection. */
static uint32_t fault_record[2][FC_WORDS];
static uint8_t fault_ready, fault_pending;
static uint32_t poll_previous_cycles,poll_gap,poll_max_gap;
static uint32_t previous_isr,previous_cr2,previous_gpio,previous_cycles;
static bool poll_seen;
static void capture_before_reset(void*ctx,uint8_t cause,uint32_t isr,uint32_t ms,uint32_t cycles){
  (void)ctx;
  uint32_t bdtr=TIM1->BDTR;
  uint8_t wanted=(uint8_t)((fault_ready&1U?0U:1U)|((bdtr&32768U)&&!(fault_ready&2U)?2U:0U));
  fault_pending=wanted;
  if(!wanted)return;
  unsigned slot=(wanted&1U)?0U:1U;uint32_t *r=fault_record[slot];
  r[0]=FC_MAGIC;r[1]=FC_PEER;r[2]=ms;r[3]=cycles;
  r[4]=(uint32_t)cause|((uint32_t)enc.stage<<8)|((uint32_t)enc.state<<16)|((uint32_t)enc.n<<24);
  r[5]=isr;r[6]=I2C1->ISR;r[7]=GPIOB->IDR;r[8]=I2C1->ISR;
  r[9]=I2C1->CR1;r[10]=I2C1->CR2;r[11]=I2C1->TIMINGR;
  r[12]=GPIOB->MODER;r[13]=GPIOB->OTYPER;r[14]=GPIOB->AFR[1];r[15]=RCC->CCIPR;
  r[16]=bdtr;r[17]=TIM1->CNT;r[18]=TIM1->CR1;r[19]=TIM1->ARR;
  r[20]=TIM1->CCR1;r[21]=TIM1->CCR2;r[22]=TIM1->CCR3;
  r[23]=poll_gap;r[24]=poll_max_gap;r[25]=cycles-enc.begin_cycles;
  r[26]=enc.errors;r[27]=enc.reads;r[28]=previous_isr;r[29]=previous_cr2;
  r[30]=previous_gpio;r[31]=previous_cycles;r[32]=SystemCoreClock;r[33]=RCC->CFGR;
  r[34]=DWT->CYCCNT;r[35]=0;r[36]=0;r[37]=0;r[38]=0;r[39]=0;
  if(wanted==3U)memcpy(fault_record[1],r,FC_BYTES);
}
static void capture_terminal(void*ctx,uint8_t flags){
  (void)ctx;
  if(!fault_pending)return;
  uint32_t isr=I2C1->ISR,cr1=I2C1->CR1,cr2=I2C1->CR2,gpio=GPIOB->IDR,cyc=DWT->CYCCNT;
  for(unsigned slot=0;slot<2;++slot)if(fault_pending&(1U<<slot)){
    uint32_t *r=fault_record[slot];r[4]|=(uint32_t)flags<<26;r[35]=isr;r[36]=cr1;r[37]=cr2;r[38]=gpio;r[39]=cyc;
    sr_arm(&release_probe[slot],cyc,gpio);release_pending|=(uint8_t)(1U<<slot);
  }
  fault_ready|=fault_pending;fault_pending=0;
}
bool mic_encoder_fault_packet(uint8_t*p,unsigned slot,unsigned page){
  if(slot>1||page>=FC_PAGES||!(fault_ready&(1U<<slot)))return false;
  /* Called only with TIM1 outputs OFF by the independent main TX scheduler. */
  fc_packet(p,fault_record[slot],slot,page,uv3_crc32c((const uint8_t*)fault_record[slot],FC_BYTES));
  return true;
}

#include "bus_clear.h"
static bc_state bus_clear;
static bool bus_clear_allowed;
static uint32_t bus_clear_saved_mode,bus_clear_saved_odr;
static void bc_gpio_enter(void*x){
  (void)x;
  bus_clear_saved_mode=GPIOB->MODER&(15U<<16);
  bus_clear_saved_odr=GPIOB->ODR&(3U<<8);
  /* Latch both released BEFORE changing AF to output; OTYPER is already OD. */
  GPIOB->BSRR=3U<<8;__DSB();
  MODIFY_REG(GPIOB->MODER,15U<<16,5U<<16);__DSB();
}
static void bc_gpio_scl(void*x,bool low){(void)x;GPIOB->BSRR=1U<<(low?24:8);__DSB();}
static void bc_gpio_sda(void*x,bool low){(void)x;GPIOB->BSRR=1U<<(low?25:9);__DSB();}
static void bc_gpio_leave(void*x){
  (void)x;GPIOB->BSRR=3U<<8;__DSB();
  MODIFY_REG(GPIOB->MODER,15U<<16,bus_clear_saved_mode);__DSB();
  GPIOB->BSRR=bus_clear_saved_odr|(((3U<<8)&~bus_clear_saved_odr)<<16);
}
static bc_io bus_clear_io={0,lines,bc_gpio_enter,bc_gpio_scl,bc_gpio_sda,bc_gpio_leave};
void mic_encoder_allow_bus_clear(bool allowed){bus_clear_allowed=allowed;}
static bool bus_clear_service(void){
  const bool allowed=bus_clear_allowed && !(TIM1->BDTR&TIM_BDTR_MOE) &&
    !(I2C1->CR1&I2C_CR1_PE) && enc.configured && !enc.state && !enc.prepare && !enc.recovering;
  if(bus_clear.active){bc_poll(&bus_clear,&bus_clear_io,DWT->CYCCNT,SystemCoreClock,allowed);return true;}
  /* Freeze the original first fault AND its PE0 observations before recovery.
     One attempt per boot; no new GPIO recovery while PWM or START is pending. */
  if(allowed && !bus_clear.attempted && enc.primary_busy && (fault_ready&1U) &&
     release_probe[0].complete && lines(0)==1U){
    bc_begin(&bus_clear,&bus_clear_io,DWT->CYCCNT);return true;
  }
  return false;
}
bool mic_encoder_bus_clear_packet(uint8_t*p){
  if(!bus_clear.attempted||bus_clear.active||!bus_clear.result)return false;
  memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=0xde;p[3]=1;
  p[4]=bus_clear.result;p[5]=bus_clear.pulses;ew_p32(p+6,EW_PEER);
  p[10]=bus_clear.before;p[11]=bus_clear.released;p[12]=bus_clear.after;
  ew_p32(p+14,bus_clear.duration_us);ew_p32(p+18,bus_clear.begin);
  ew_p32(p+22,uv3_crc32c((const uint8_t*)fault_record[0],FC_BYTES));
  uv3_seal(p);return true;
}

static bool config_ok(void){
  return enc.configured && (GPIOB->MODER&(15U<<16))==(10U<<16) &&
      (GPIOB->OTYPER&(3U<<8))==(3U<<8) &&
      (GPIOB->AFR[1]&255U)==0x44U &&
      ((I2C1->CR1&I2C_CR1_PE)!=0)==enc.pe_on &&
      (I2C1->CR1&(I2C_CR1_ANFOFF|I2C_CR1_DNF))==(2U<<I2C_CR1_DNF_Pos) &&
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
    clear(0); // Remain parked until the first bounded acquisition.
    CoreDebug->DEMCR|=CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CTRL|=DWT_CTRL_CYCCNTENA_Msk; /* Never reset an existing counter. */
  }
  ec_init(&enc,SystemCoreClock,ready);
  enc.configured=config_ok()?1:0;
  if(!enc.configured)enc.cause=EC_SETUP;
}
void mic_encoder_poll(void){
  release_poll();
  if(bus_clear_service())return;
  if(enc.configured && !config_ok()){
    ec_finish(&enc,&io,HAL_GetTick(),DWT->CYCCNT,SystemCoreClock,EC_SETUP,I2C1->ISR);
    enc.configured=0;
  }
  uint32_t cyc=DWT->CYCCNT;
  poll_gap=poll_seen?cyc-poll_previous_cycles:0U;
  if(poll_gap>poll_max_gap)poll_max_gap=poll_gap;
  poll_previous_cycles=cyc;poll_seen=true;
  uint32_t isr=I2C1->ISR,cr2=I2C1->CR2,gpio=GPIOB->IDR;
  ec_poll(&enc,&io,HAL_GetTick(),cyc,SystemCoreClock);
  previous_isr=isr;previous_cr2=cr2;previous_gpio=gpio;previous_cycles=cyc;
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

void mic_encoder_health_snapshot(uint32_t*v){
  v[0]=enc.primary_nack;v[1]=enc.timeouts;v[2]=enc.primary_busy;v[3]=enc.primary_arlo;
  v[4]=enc.primary_ovr;v[5]=enc.primary_short;v[6]=enc.primary_setup;v[7]=enc.berr_clears;
  v[8]=enc.clean_stops;v[9]=enc.forced_resets;v[10]=enc.stop_requests;
  v[11]=enc.cleanup_expired;v[12]=enc.parks;v[13]=enc.cleanup_flags;
}

bool mic_encoder_release_packet(uint8_t*p,unsigned slot,unsigned page){
  if(slot>1||page>=PR_PAGES||!(fault_ready&(1U<<slot)))return false;
  const sr_probe*q=&release_probe[slot];
  if(q->active||(!q->count&&!q->flags))return false;
  uint32_t r[PR_WORDS]={0};const uint32_t*parent=fault_record[slot];
  r[0]=PR_MAGIC;r[1]=PR_PEER;r[2]=uv3_crc32c((const uint8_t*)parent,FC_BYTES);
  r[3]=(uint32_t)q->flags|((uint32_t)q->count<<8)|((uint32_t)sr_result(q)<<16);
  r[4]=q->terminal_cycles;r[5]=q->terminal_gpio;r[6]=parent[32];r[7]=parent[2];
  for(unsigned i=0;i<q->count;i++){
    const sr_sample*s=&q->after[i];unsigned n=8+5*i;
    r[n]=s->cycles;r[n+1]=s->isr;r[n+2]=s->cr1;r[n+3]=s->cr2;r[n+4]=s->gpio;
  }
  r[23]=release_park_cycles[slot];r[24]=uv3_crc32c((const uint8_t*)r,96);
  pr_packet(p,r,slot,page,uv3_crc32c((const uint8_t*)r,PR_BYTES));return true;
}

/* Read-only export for the ST-LINK diagnostic report; no state reset. */
void mic_encoder_load_snapshot(uint32_t *v){
 v[0]=enc.reads;v[1]=enc.errors;v[2]=enc.primary_nack;v[3]=enc.timeouts;
 v[4]=enc.primary_busy;v[5]=enc.primary_arlo;v[6]=enc.berr_clears;
 v[7]=enc.forced_resets;v[8]=enc.parks;v[9]=enc.raw;v[10]=enc.status;
 v[11]=(enc.bus_ok?1U:0U)|(enc.angle_ok?2U:0U)|(enc.speed_ok?4U:0U);
 v[12]=I2C1->ISR;v[13]=I2C1->CR1;v[14]=GPIOB->IDR;
 v[15]=enc.sample_ms;v[16]=fault_ready;
}
