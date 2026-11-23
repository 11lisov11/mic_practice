/* Native commissioning additions; compiled in the same TU as the existing
 * native controller. No START, fault CLEAR, or protection-register writes. */
static int mi_native_prepare(void){
  ma_current_sample sample;
  if(!id_configured||id_state.active||id_state.ready||id_state.done||!mic_current_fast(&sample)||!sample.zero)return 0;
  memset(&cached_sample,0,sizeof(cached_sample));running=0;return 1;
}
static int mi_native_config(const uint8_t*f){
  uint32_t raw=ma_u32(f+8);unsigned op=f[6],index=f[7];
  if(id_state.active)return 0;
  if(op==4){
    if(index>=15||id_state.ready)return 0;
    memcpy((uint8_t*)&id_staged+4*index,&raw,4);id_stage_mask|=(uint16_t)(1U<<index);return 1;
  }
  if(op==5&&index==0){
    if(id_state.ready||id_staged.run_id==id_state.config.run_id||id_stage_mask!=32767U||uv3_crc32c((uint8_t*)&id_staged,sizeof(id_staged))!=raw||!mi_config_valid(&id_staged))return 0;
    id_config=id_staged;id_configured=1;id_stage_mask=0;return 1;
  }
  if(op==6&&index==0&&mi_ack(&id_state,raw)){id_configured=0;return 1;}
  return 0;
}
int ma_native_complete(void){return selected==4&&id_state.done;}
static int mi_native_service(void){
  if(!LL_TIM_IsEnabledAllOutputs(TIM1)){
    if(id_state.active)mi_stop(&id_state,MI_EXTERNAL_STOP,DWT->CYCCNT);
    if(id_state.done&&!id_state.ready)(void)mi_seal(&id_state,MIC_NATIVE_BUILD,SystemCoreClock);
  }
  if(selected==4){if(!LL_TIM_IsEnabledAllOutputs(TIM1))running=0;return 1;}
  return 0;
}
static uint16_t mi_native_fast(void){
  const uint32_t begin=DWT->CYCCNT;ma_current_sample sample;
  int got=mic_current_fast(&sample);
  if(got&&sample.valid&&sample.zero)cached_sample=sample;
  else if(!got&&cached_sample.valid){sample=cached_sample;got=1;}
  if(!running){running=1;start_cycles=begin;}
  if(!got||!sample.valid||!sample.zero){
    if(got&&sample.zero&&(uint32_t)(begin-start_cycles)<SystemCoreClock/1000U){
      TIM1->CCR1=TIM1->ARR/2;TIM1->CCR2=TIM1->ARR/2;TIM1->CCR3=TIM1->ARR/2;return MC_NO_ERROR;
    }
    mi_stop(&id_state,MI_STALE,begin);return MC_SW_ERROR;
  }
  if(!id_state.active){
    if(id_state.done)return MC_SW_ERROR;
    if(!id_configured||!mi_begin(&id_state,&id_config,sample.cycles))return MC_SW_ERROR;
  }
  mi_sample point;memset(&point,0,sizeof(point));point.cycles=sample.cycles;point.epoch=sample.epoch;
  point.ia=ma_amps(sample.counts[0]);point.ib=(ma_amps(sample.counts[0])+2*ma_amps(sample.counts[1]))*.5773502692f;
  point.bus=sample.bus_v;point.arr=sample.arr;point.valid=sample.valid;
  for(unsigned i=0;i<3;i++)point.ccr[i]=sample.ccr[i];
  ma_geometry geometry={TIM1->ARR,TIM1->ARR-128U,TW_AFTER+TNOISE+32U,112U,240U,
    (uint32_t)(DEADTIME_NS*ADV_TIM_CLK_MHz/1000U)};
  ma_output out;int rc=mi_step(&id_state,&geometry,&point,begin,SystemCoreClock,&out);
  if(rc==MI_COMPLETE){PWM_SwitchOffPWM(&PWM_ParamsM1);return MC_NO_ERROR;}
  if(rc!=MI_OK)return MC_SW_ERROR;
  const uint32_t elapsed=DWT->CYCCNT-begin;if(elapsed>max_fast_cycles)max_fast_cycles=elapsed;
  if(elapsed>SystemCoreClock/16000U/2U){mi_stop(&id_state,MI_OVERRUN,begin);return MC_DURATION;}
  TIM1->CCR1=out.ccr[0];TIM1->CCR2=out.ccr[1];TIM1->CCR3=out.ccr[2];return MC_NO_ERROR;
}
void ma_id_status(uint8_t*p,uint32_t build){
  memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=ID_STATUS_WIRE;p[3]=1;p[4]=4;
  p[5]=(id_configured?1:0)|(id_state.active?2:0)|(id_state.ready?4:0)|(id_state.done?8:0);
  id_put(p+6,build);id_put(p+10,id_configured?uv3_crc32c((uint8_t*)&id_config,sizeof(id_config)):0);
  id_put(p+14,id_state.ready?id_state.crc:0);id_put(p+18,id_config.run_id);id_put(p+22,id_config.kind);
  uint32_t raw;memcpy(&raw,&id_config.frequency,4);id_put(p+26,raw);id_put(p+30,id_config.duration_ms);
  id_put(p+34,id_state.accepted);p[38]=id_state.fault;uv3_seal(p);
}
int ma_id_page(uint8_t*p,uint32_t build,unsigned page){
  if(!id_state.ready||LL_TIM_IsEnabledAllOutputs(TIM1)||page>=MI_PAGES)return 0;
  memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=ID_PAGE_WIRE;p[3]=1;p[4]=(uint8_t)page;p[5]=MI_PAGES;
  id_put(p+6,build);id_put(p+10,id_state.crc);unsigned offset=24*page,n=MI_BYTES-offset;if(n>24)n=24;
  memcpy(p+14,id_state.bytes+offset,n);uv3_seal(p);return 1;
}
