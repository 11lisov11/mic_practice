/* Same-priority CPU qualification: main prepares synthetic work while MOE=0;
 * the normal TIM1 update IRQ measures one pure kernel call. No IRQ mask, PWM,
 * MCSDK START or protection acknowledgment is used. */
static uint8_t id_profile_case,id_profile_n;
static volatile uint8_t id_profile_running,id_profile_pending,id_profile_done;
static volatile uint32_t id_profile_elapsed;
static volatile int id_profile_rc;
static uint32_t id_profile_maximum;
static mi_sample id_profile_input;
static ma_geometry id_profile_geometry;
static void mi_profile_finish(int okay){
 id_profile_pending=0;id_profile_running=0;id_profile_done=0;
 memset(&id_state,0,sizeof(id_state));id_prepared=0;
 id_profile_cycles=okay?id_profile_maximum:UINT32_MAX;
}
static void mi_native_profile_off(void){
 if(id_profile_attempted&&!id_profile_running)return;
 if(!id_profile_attempted){
  if(id_configured||id_state.active||id_state.ready||id_state.done||LL_TIM_IsEnabledAllOutputs(TIM1)||
    VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super)>20U)return;
  ma_current_sample real_sample;if(!mic_current_fast(&real_sample)||!real_sample.zero)return;
  id_profile_attempted=1;id_profile_running=1;id_profile_case=id_profile_n=0;id_profile_maximum=0;
  id_profile_geometry=(ma_geometry){TIM1->ARR,TIM1->ARR-128U,TW_AFTER+TNOISE+32U,112U,240U,
   (uint32_t)(DEADTIME_NS*ADV_TIM_CLK_MHz/1000U)};
 }
 if(LL_TIM_IsEnabledAllOutputs(TIM1)||VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super)>20U){mi_profile_finish(0);return;}
 if(id_profile_pending)return;
 if(id_profile_done){
  if(id_profile_elapsed>id_profile_maximum)id_profile_maximum=id_profile_elapsed;
  if(id_profile_rc!=MI_OK){mi_profile_finish(0);return;}
  id_profile_done=0;
  if(++id_profile_n==128){id_profile_n=0;if(++id_profile_case==8){mi_profile_finish(1);return;}}
 }
 unsigned k=id_profile_case;
 if(!id_profile_n){
  mi_config cfg;memset(&cfg,0,sizeof(cfg));cfg.run_id=k+1;cfg.kind=k<2?MI_DC:MI_AC;
  cfg.axis=(k%3)*2.0943951024f;cfg.amplitude=.3f;cfg.rs=12.23f;cfg.duration_ms=3000;
  cfg.gain=.95f;cfg.knee=.002f;for(unsigned j=0;j<3;j++)cfg.drop[j]=15;cfg.offset[0]=2;cfg.offset[1]=-2;
  if(cfg.kind==MI_AC){cfg.frequency=k<4?1:k<6?50:200;
   cfg.duration_ms=(uint32_t)ceilf(1000*(mi_settle_cycles(&cfg)+5)/cfg.frequency)+1;cfg.calibration_crc=mi_cal_crc(&cfg);}
  memset(&id_state,0,sizeof(id_state));if(!mi_begin(&id_state,&cfg,0)){mi_profile_finish(0);return;}
  id_state.response=cfg.amplitude;
 }
 const mi_config* cfg=&id_state.config;
 float offset=(k&1)?(cfg->kind==MI_DC?2.6f:(id_state.settle_cycles+.1f)/cfg->frequency):.1f;
 memset(&id_profile_input,0,sizeof(id_profile_input));id_profile_input.valid=1;id_profile_input.bus=k&1?250:350;
 id_profile_input.arr=id_profile_geometry.arr;id_profile_input.epoch=id_profile_n+1;
 id_profile_input.cycles=(uint32_t)(offset*SystemCoreClock)+id_profile_n*(SystemCoreClock/16000U);
 float phase=6.2831853072f*cfg->frequency*id_profile_input.cycles/SystemCoreClock;
 float current=cfg->kind==MI_DC?cfg->amplitude:cfg->amplitude*sinf(phase);
 id_profile_input.ia=current*id_state.axis_cos;id_profile_input.ib=current*id_state.axis_sin;
 for(unsigned j=0;j<3;j++)id_profile_input.ccr[j]=id_profile_geometry.arr/2;
 __DMB();id_profile_pending=1;
}
void ma_native_profile_tick(void){
 if(!id_profile_running||!id_profile_pending||LL_TIM_IsEnabledAllOutputs(TIM1))return;
 ma_output output;
 uint32_t begin=DWT->CYCCNT;
 int rc=mi_step(&id_state,&id_profile_geometry,&id_profile_input,id_profile_input.cycles+32,SystemCoreClock,&output);
 id_profile_elapsed=DWT->CYCCNT-begin;id_profile_rc=rc;id_profile_done=1;
 __DMB();id_profile_pending=0;
}
