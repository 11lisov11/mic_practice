void mic_current_adc_irq(void) {
  if(!initialized || !LL_ADC_IsActiveFlag_JEOS(ADC1))return;
  /* Bind the completed sample to one update epoch BEFORE changing shadows.
   * UPDATE latches all CCRs, then the VF task writes the following cycle.
   * OC4 preload is mandatory: changing a shadow must not create a trigger now. */
  uint32_t epoch0=peak_epoch,cycles0=DWT->CYCCNT;
  uint16_t current_ccr[4];
  for(unsigned i=0;i<4;++i)current_ccr[i]=peak_active_ccr[i];
  uint16_t current_update_cnt=peak_update_cnt,current_update_cr1=peak_update_cr1;
  uint32_t epoch1=peak_epoch;
  uint32_t u=TIM1->CCR1,v=TIM1->CCR2,w=TIM1->CCR3,old_trigger=TIM1->CCR4;
  uint32_t count=TIM1->CNT,direction=TIM1->CR1&TIM_CR1_DIR;
  uint8_t early=(uint8_t)(!direction && count>=old_trigger && count<TIM1->ARR-24U);
  uint32_t isr1=ADC1->ISR,isr2=ADC2->ISR,jsqr1=0,jsqr2=0;
  if(!peak.frozen){jsqr1=ADC1->JSQR;jsqr2=ADC2->JSQR;}
  uint8_t both=(uint8_t)LL_ADC_IsActiveFlag_JEOS(ADC2);
  if(!both || ((isr1|isr2)&ADC_ISR_JQOVF))lost_sync=1;
  uint16_t a=(uint16_t)(ADC1->JDR1>>4),b=(uint16_t)(ADC2->JDR1>>4);
  LL_ADC_ClearFlag_JEOS(ADC1);LL_ADC_ClearFlag_JEOS(ADC2);
  uint8_t active=(uint8_t)(LL_TIM_IsEnabledAllOutputs(TIM1)!=0);
  uint16_t bus=VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super);
  uint8_t captured_pair=pending_pair,valid0=pending_valid,active0=pending_active;
  uint8_t context_ok=(uint8_t)(epoch0==epoch1 && epoch1==peak_epoch &&
      current_ccr[3]==old_trigger);
  uint8_t geometry_ok=(uint8_t)mic_current_window_safe(captured_pair,
      current_ccr[0],current_ccr[1],current_ccr[2],current_ccr[3],
      CM_SETTLE_TICKS,CM_ACQUIRE_TICKS);
  /* Raw trigger eligibility is deliberately independent of geometry: retain
   * an invalid-window spike as evidence, but NEVER include it in RMS/peak. */
  uint8_t raw_eligible=(uint8_t)(both && !lost_sync && context_ok &&
      active0 && active && state.zero_ready);
  uint8_t eligible=(uint8_t)(raw_eligible && valid0 && geometry_ok);
  uint8_t pair=active?cm_choose_pair(u,v,w):(pending_pair==0?2:0);
  mic_current_window_plan plan=mic_plan_current_window(u,v,w,
      TIM1->ARR-CM_BEFORE_TOP,CM_SETTLE_TICKS,CM_ACQUIRE_TICKS);
  if(!active){plan.trigger=TIM1->ARR-CM_BEFORE_TOP;plan.valid=1;}
  else pair=plan.pair;
  /* Even if no safe interval exists, keep ADC heartbeat at the bounded latest
   * point and explicitly invalidate the following measurement. */
  if(!plan.valid)plan.trigger=TIM1->ARR-CM_BEFORE_TOP;
  LL_TIM_OC_SetCompareCH4(TIM1,plan.trigger);
  pending_valid=(uint8_t)(early && plan.valid && epoch0==peak_epoch);
  pending_active=active;
  queue_pair(pair);
  uint16_t queue_cnt=(uint16_t)TIM1->CNT,queue_dir=(uint16_t)(TIM1->CR1&TIM_CR1_DIR);
  uint32_t queue_cycles=DWT->CYCCNT-cycles0;
  if(epoch0!=peak_epoch)pending_valid=0;
  /* Publish next context before zero statistics and diagnostic work. */
  cm_sample(&state,HAL_GetTick(),active,captured_pair,a,b,eligible,
            bus<=20U && both && !lost_sync && early && context_ok);
  if(!peak.frozen && (active || peak.running)) {
    if(queue_cycles>peak.blob.header.reserved)peak.blob.header.reserved=queue_cycles;
    pc_sample sample={0};
    sample.cycles=cycles0;sample.epoch_before=epoch0;sample.epoch_after=epoch1;
    sample.isr1=isr1;sample.isr2=isr2;sample.jsqr1=jsqr1;sample.jsqr2=jsqr2;
    for(unsigned i=0;i<4;++i){sample.active_ccr[i]=current_ccr[i];sample.offset[i]=state.offset[i];}
    sample.update_cnt=current_update_cnt;sample.update_cr1=current_update_cr1;
    sample.preload_ccr[0]=(uint16_t)u;sample.preload_ccr[1]=(uint16_t)v;
    sample.preload_ccr[2]=(uint16_t)w;sample.preload_ccr[3]=(uint16_t)plan.trigger;
    sample.cnt=(uint16_t)count;sample.arr=(uint16_t)TIM1->ARR;sample.cr1=(uint16_t)direction;
    sample.raw[0]=a;sample.raw[1]=b;sample.pair=captured_pair;sample.next_pair=pair;
    sample.cnt_exit=queue_cnt;sample.bus_v=bus;
    sample.reference_deci_hz=(uint16_t)(pACIM_VF_Component_M1->fFlux_Freq_Hz*10.0f);
    uint8_t accepted=(uint8_t)(eligible && a>=16 && b>=16 && a<=4079 && b<=4079);
    sample.flags=(uint16_t)((active?1:0)|(valid0?2:0)|(active0?4:0)|(both?8:0)|
        (lost_sync?16:0)|(early?32:0)|(accepted?64:0)|(!context_ok?128:0)|
        (((isr1|isr2)&ADC_ISR_JQOVF)?256:0)|(queue_dir?512:0)|
        (!geometry_ok?1024:0));
    int32_t ia=(int32_t)state.offset[cm_path1(captured_pair)]-a;
    int32_t ib=(int32_t)state.offset[cm_path2(captured_pair)]-b,ic=-ia-ib;
    uint32_t mag=(uint32_t)(ia<0?-ia:ia),m=(uint32_t)(ib<0?-ib:ib);
    if(m>mag)mag=m;
    m=(uint32_t)(ic<0?-ic:ic);
    if(m>mag)mag=m;
    pc_push(&peak,&sample,HAL_GetTick(),active,raw_eligible,mag);
  }
}
