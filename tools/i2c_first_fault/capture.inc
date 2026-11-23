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
static void capture_after_reset(void){
  if(!fault_pending)return;
  uint32_t isr=I2C1->ISR,cr1=I2C1->CR1,cr2=I2C1->CR2,gpio=GPIOB->IDR,cyc=DWT->CYCCNT;
  for(unsigned slot=0;slot<2;++slot)if(fault_pending&(1U<<slot)){
    uint32_t *r=fault_record[slot];r[35]=isr;r[36]=cr1;r[37]=cr2;r[38]=gpio;r[39]=cyc;
  }
  fault_ready|=fault_pending;fault_pending=0;
}
bool mic_encoder_fault_packet(uint8_t*p,unsigned slot,unsigned page){
  if(slot>1||page>=FC_PAGES||!(fault_ready&(1U<<slot)))return false;
  /* Called only with TIM1 outputs OFF by the independent main TX scheduler. */
  fc_packet(p,fault_record[slot],slot,page,uv3_crc32c((const uint8_t*)fault_record[slot],FC_BYTES));
  return true;
}
