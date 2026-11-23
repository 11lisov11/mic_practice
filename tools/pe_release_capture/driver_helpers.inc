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
