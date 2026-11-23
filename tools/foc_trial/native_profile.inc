/* Isolated synthetic CPU probe. Runs only with MOE=0, low bus and real zero.
 * Main prepares cases; real TIM1 IRQ measures pure FOC, main measures observer.
 * No synthetic sample enters current feedback or saved physical captures. */
static ma_controller fe_test_controller;
static ma_observer fe_test_observer;
static ma_geometry fe_test_geometry;
static float fe_test_x[6],fe_test_ia,fe_test_ib,fe_test_bus,fe_test_ref;
static ma_output fe_test_out;
static volatile uint8_t fe_pending,fe_finished;
static volatile uint32_t fe_elapsed;
static volatile int fe_rc;
static uint8_t fe_started,fe_complete,fe_fault,fe_case,fe_n;
static uint32_t fe_fast_cycles,fe_observer_cycles;
static volatile uint8_t fe_trial_done;
static uint32_t fe_trial_begin;

static unsigned fe_flags(void){
 return (fe_complete&&!fe_fault?FE_READY:0)|
  (fe_started&&!fe_complete&&!fe_fault?FE_BUSY:0)|(fe_trial_done?FE_DONE:0);
}
static int fe_profile_allowed(unsigned algorithm){
 return profile_ready&&(qualification==7||
  (qualification==FE_ESTIMATED&&algorithm==MA_FOC&&fe_model_exact(&model)&&
   (fe_flags()&FE_READY)&&!fe_fault));
}
static int fe_profile_tick(void){
 if(!fe_pending||LL_TIM_IsEnabledAllOutputs(TIM1))return 0;
 const uint32_t begin=DWT->CYCCNT;
 fe_rc=ma_control(&fe_test_controller,&model,fe_test_x,&fe_test_geometry,MA_FOC,
   fe_test_ia,fe_test_ib,fe_test_ref,fe_test_bus,1.f/16000U,1,&fe_test_out);
 fe_elapsed=DWT->CYCCNT-begin;__DMB();fe_finished=1;fe_pending=0;return 1;
}
static void fe_profile_service(void){
 if(qualification!=FE_ESTIMATED||fe_complete||fe_fault)return;
 if(LL_TIM_IsEnabledAllOutputs(TIM1)||
    VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super)>20U)return;
 ma_current_sample real_sample;
 if(!mic_current_fast(&real_sample)||!real_sample.zero)return;
 if(!fe_started){
  fe_started=1;fe_case=fe_n=0;
  fe_test_geometry=(ma_geometry){TIM1->ARR,TIM1->ARR-128U,TW_AFTER+TNOISE+32U,
   112U,240U,(uint32_t)(DEADTIME_NS*ADV_TIM_CLK_MHz/1000U)};
 }
 if(fe_pending)return;
 if(fe_finished){
  fe_finished=0;
  if(fe_elapsed>fe_fast_cycles)fe_fast_cycles=fe_elapsed;
  if(fe_rc||!fe_elapsed||fe_elapsed>FE_FAST_BUDGET){fe_fault=(uint8_t)(fe_rc?fe_rc:MA_STALE);return;}
  /* One foreground observer call per case; timer/ADC/UART interrupts stay on. */
  if(!fe_n){
   const uint32_t begin=DWT->CYCCNT;
   int rc=ma_observe(&fe_test_observer,&model,fe_test_ia,fe_test_ib,
                    fe_test_out.va,fe_test_out.vb,.001f);
   uint32_t cycles=DWT->CYCCNT-begin;
   if(cycles>fe_observer_cycles)fe_observer_cycles=cycles;
   if(rc||!cycles||cycles>FE_OBSERVER_BUDGET){fe_fault=(uint8_t)(rc?rc:MA_STALE);return;}
  }
  if(++fe_n==8){fe_n=0;if(++fe_case==FE_CASES){fe_complete=1;return;}}
 }
 if(!fe_n){
  ma_reset(&fe_test_observer,&fe_test_controller);
  float angle=(fe_case%16U)*.3926990817f,c=cosf(angle),s=sinf(angle);
  float current=(fe_case&16U)?.75f:.2f;
  fe_test_ia=current*c;fe_test_ib=current*s;
  fe_test_x[0]=fe_test_ia;fe_test_x[1]=fe_test_ib;
  fe_test_x[2]=model.flux*c;fe_test_x[3]=model.flux*s;
  fe_test_x[4]=(fe_case&32U)?314.1592654f:31.41592654f;fe_test_x[5]=0;
  for(unsigned i=0;i<6;i++)fe_test_observer.x[i]=fe_test_x[i];
  fe_test_controller.time_s=(fe_case&8U)?1.f:.05f;
  fe_test_bus=(fe_case&4U)?250.f:350.f;fe_test_ref=(fe_case&2U)?50.f:5.f;
 }
 __DMB();fe_pending=1;
}
