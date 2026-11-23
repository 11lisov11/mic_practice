/* One CPU-only timing self-check per native boot, in actual flash, while OFF.
 * Fake inputs stay inside this isolated kernel state and are never published as
 * ADC readings, physical data, or identification results. No IRQ is masked.
 * The existing hardware/current/voltage protections remain in force.
 */
static void mi_native_profile_off(void){
 if(id_profile_attempted||id_configured||id_state.active||id_state.ready||id_state.done||
    LL_TIM_IsEnabledAllOutputs(TIM1)||
    VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super)>20U)return;
 ma_current_sample real_sample;
 if(!mic_current_fast(&real_sample)||!real_sample.zero)return;
 id_profile_attempted=1;uint32_t maximum=0;int okay=1;
 ma_geometry g={TIM1->ARR,TIM1->ARR-128U,TW_AFTER+TNOISE+32U,112U,240U,
  (uint32_t)(DEADTIME_NS*ADV_TIM_CLK_MHz/1000U)};
 for(unsigned k=0;k<8;k++){
  mi_config cfg;memset(&cfg,0,sizeof(cfg));cfg.run_id=k+1;cfg.kind=k<2?MI_DC:MI_AC;
  cfg.axis=(k%3)*2.0943951024f;cfg.amplitude=.3f;cfg.rs=12.23f;cfg.duration_ms=3000;
  cfg.gain=.95f;cfg.knee=.002f;for(unsigned j=0;j<3;j++)cfg.drop[j]=15;cfg.offset[0]=2;cfg.offset[1]=-2;
  if(cfg.kind==MI_AC){cfg.frequency=k<4?1:k<6?50:200;
   cfg.duration_ms=(uint32_t)ceilf(1000*(mi_settle_cycles(&cfg)+5)/cfg.frequency)+1;cfg.calibration_crc=mi_cal_crc(&cfg);}
  memset(&id_state,0,sizeof(id_state));if(!mi_begin(&id_state,&cfg,0)){okay=0;break;}
  id_state.response=cfg.amplitude;ma_output out;
  for(unsigned n=0;n<128;n++){
   const float offset=(k&1)?(cfg.kind==MI_DC?2.6f:(mi_settle_cycles(&cfg)+.1f)/cfg.frequency):.1f;
   mi_sample input;memset(&input,0,sizeof(input));input.valid=1;input.bus=k&1?250:350;input.arr=g.arr;input.epoch=n+1;
   input.cycles=(uint32_t)(offset*SystemCoreClock)+n*(SystemCoreClock/16000U);
   float phase=6.2831853072f*cfg.frequency*input.cycles/SystemCoreClock;
   float current=cfg.kind==MI_DC?cfg.amplitude:cfg.amplitude*sinf(phase);
   input.ia=current*id_state.axis_cos;input.ib=current*id_state.axis_sin;
   for(unsigned j=0;j<3;j++)input.ccr[j]=g.arr/2;
   uint32_t begin=DWT->CYCCNT;
   int rc=mi_step(&id_state,&g,&input,input.cycles+32,SystemCoreClock,&out);
   uint32_t elapsed=DWT->CYCCNT-begin;if(elapsed>maximum)maximum=elapsed;
   if(rc!=MI_OK){okay=0;break;}
  }
  if(!okay)break;
 }
 /* Only temporary synthetic state is discarded; no real record can exist here. */
 memset(&id_state,0,sizeof(id_state));id_prepared=0;
 id_profile_cycles=okay?maximum:UINT32_MAX;
}
