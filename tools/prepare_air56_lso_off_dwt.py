"""Build a side-by-side ST LSO image with an output-disabled DWT fixture."""

import re
import shutil

from instrument_air56_st_lso_reference import once
from prepare_air56_st_lso_reference import OUT
from install_foc_handover_feedback_release import read_json, sha


BASE = OUT
OUT = BASE.with_name('air56_st_lso_off_dwt_r1')


VOLTAGE = r'''
static inline alphabeta_t AIR56_CurrentVoltage(ab_t ab, int16_t angle,
    FOCVars_t *foc, PID_Handle_t *pid_q, PID_Handle_t *pid_d)
{
  const alphabeta_t alpha_beta = MCM_Clarke(ab);
  Vector_s16_Components vector;
  memcpy(&vector, &alpha_beta, sizeof(vector));
  vector = MCM_Park_Generic(vector, angle);
  qd_t measured;
  memcpy(&measured, &vector, sizeof(measured));

  int32_t iq = foc->Iqdref.q;
  if (iq < 0) { iq = 0; }
  if (iq > IQMAX) { iq = IQMAX; }
  const qd_t voltage = {
    .q = PI_Controller(pid_q, iq - measured.q),
    .d = PI_Controller(pid_d, (int32_t)DEFAULT_FLUX_COMPONENT_A - measured.d)
  };
  const qd_t limited = Circle_Limitation(&CircleLimitationM1, voltage);
  memcpy(&vector, &limited, sizeof(vector));
  vector = MCM_Rev_Park_Generic(vector, angle);
  alphabeta_t command;
  memcpy(&command, &vector, sizeof(command));

  foc->Iab = ab;
  foc->Ialphabeta = alpha_beta;
  foc->Iqd = measured;
  foc->Vqd = voltage;
  foc->Valphabeta = command;
  foc->hElAngle = angle;
  return command;
}

inline uint16_t FOC_CurrControllerM1(void)
{
  ab_t measured;
  PWMC_GetPhaseCurrents(pwmcHandle[M1], &measured);
  if ((Mci[M1].State == START || Mci[M1].State == RUN) &&
      air56_lso_overcurrent(measured.a, measured.b))
  {
    LL_TIM_DisableAllOutputs(TIM1);
    return MC_OVER_CURR;
  }
  const alphabeta_t applied = AIR56_CurrentVoltage(measured,
      ACIM_LSO_GetElAngle(pACIM_LSO[M1]), &FOCVars[M1], pPIDIq[M1], pPIDId[M1]);
  return PWMC_SetPhaseVoltage(pwmcHandle[M1], applied);
}
'''


PROBE = r'''
/* Independent RAM-backed devices. Only register reads use real TIM1/ADC. */
static TIM_TypeDef air56_test_tim;
static ADC_TypeDef air56_test_adc1, air56_test_adc2;
static R3_2_Params_t air56_test_params = {
  .TIMx = &air56_test_tim, .Tafter = TW_AFTER, .Tbefore = TW_BEFORE,
  .ADCDataReg1 = { &air56_test_adc1, &air56_test_adc1, &air56_test_adc1,
                  &air56_test_adc1, &air56_test_adc1, &air56_test_adc1 },
  .ADCDataReg2 = { &air56_test_adc2, &air56_test_adc2, &air56_test_adc2,
                  &air56_test_adc2, &air56_test_adc2, &air56_test_adc2 }
};

enum { AIR56_DWT_CASES = 64, AIR56_DWT_ITERATIONS = 8 };
volatile struct {
  uint32_t format, cases_done, max_cycles, max_lso_cycles, failures;
  uint32_t cycles[AIR56_DWT_CASES], lso_cycles[AIR56_DWT_CASES];
} air56_off_dwt = { .format = 0x414C5331U };

bool AIR56_OffDwtReady(void)
{
  return air56_off_dwt.cases_done == AIR56_DWT_CASES && air56_off_dwt.failures == 0;
}

void AIR56_OffDwtService(void)
{
  static uint32_t last_ms;
  const uint32_t index = air56_off_dwt.cases_done;
  const uint32_t now = HAL_GetTick();
  if (index >= AIR56_DWT_CASES || now == last_ms ||
      (TIM1->BDTR & (TIM_BDTR_MOE | TIM_BDTR_AOE | TIM_BDTR_BKE)) != TIM_BDTR_BKE ||
      VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super) >= 20U)
  {
    return;
  }
  last_ms = now;

  FOCVars_t foc = {0};
  PID_Handle_t id = *pPIDId[M1], iq = *pPIDIq[M1];
  PI_Float_Handle_t speed = *pACIM_LSO[M1]->fPI;
  ACIM_LSO_Handle_t lso = *pACIM_LSO[M1];
  BusVoltageSensor_Handle_t bus = BusVoltageSensor_M1._Super;
  PWMC_R3_2_Handle_t pwm = PWM_Handle_M1;
  pwm.pParams_str = &air56_test_params;
  pwm._Super.pFctGetPhaseCurrents = &R3_2_GetPhaseCurrents;
  pwm._Super.pFctSetADCSampPointSectX = &R3_2_SetADCSampPointSectX;
  pwm.PhaseAOffset = pwm.PhaseBOffset = pwm.PhaseCOffset = 32768U;
  id.wIntegralTerm = iq.wIntegralTerm = 0;
  bus.AvBusVoltage_d = (uint16_t)(((index & 16U ? 350U : 250U) * 65536U) / bus.ConversionFactor);
  lso.pFOCVars = &foc;
  lso.fPI = &speed;
  ACIM_LSO_Init(&lso, &bus);
  ACIM_LSO_Clear(&lso);
  lso.fFlux_qdr_obs.fS_Component2 = (index & 8U) ? 0.50f : 0.05f;
  lso.fRotorFlux_Angle_rad = (float)(index % 16U) * 0.3926990817f;
  if (index & 32U) { lso.fRotorFlux_Angle_rad = 6.282f; }
  lso.fIqds_obs_A.fS_Component1 = 0.12f;
  lso.fIqds_obs_A.fS_Component2 = 0.40f;
  foc.Iqdref.q = (index & 8U) ? IQMAX : 0;
  foc.Iqd.q = 200;
  foc.Iqd.d = DEFAULT_FLUX_COMPONENT_A;
  foc.Vqd.q = (index & 16U) ? 26000 : 900;
  foc.Vqd.d = (index & 16U) ? 15000 : 1400;
  const int32_t a = (int32_t)((index % 8U) * 290U) - 1000;
  const int32_t b = (index & 8U) ? 625 : -525;
  const int32_t c = -a - b;
  uint32_t worst = 0, worst_lso = 0;
  uint16_t code = MC_NO_FAULTS;
  for (uint32_t j = 0; j < AIR56_DWT_ITERATIONS; ++j)
  {
    const uint8_t sector = (uint8_t)((index + j) % 6U);
    pwm._Super.Sector = sector;
    air56_test_adc1.JDR1 = (uint32_t)(32768 - (sector == SECTOR_1 || sector == SECTOR_6 ? b : a));
    air56_test_adc2.JDR1 = (uint32_t)(32768 - (sector == SECTOR_4 || sector == SECTOR_5 ? b : c));
    ab_t measured;
    const uint32_t begin = DWT->CYCCNT;
    ACIM_LSO_CalcAngle(&lso);
    const uint32_t lso_cycles = DWT->CYCCNT - begin;
    PWMC_GetPhaseCurrents(&pwm._Super, &measured);
    if (air56_lso_overcurrent(measured.a, measured.b)) { code |= MC_OVER_CURR; }
    const alphabeta_t applied = AIR56_CurrentVoltage(measured,
        ACIM_LSO_GetElAngle(&lso), &foc, &iq, &id);
    code |= PWMC_SetPhaseVoltage(&pwm._Super, applied);
    const uint32_t cycles = DWT->CYCCNT - begin;
    if (cycles > worst) { worst = cycles; }
    if (lso_cycles > worst_lso) { worst_lso = lso_cycles; }
  }
  if (!worst || worst > AIR56_LSO_FAST_CYCLES || code != MC_NO_FAULTS)
  {
    ++air56_off_dwt.failures;
  }
  if (worst > air56_off_dwt.max_cycles) { air56_off_dwt.max_cycles = worst; }
  if (worst_lso > air56_off_dwt.max_lso_cycles) { air56_off_dwt.max_lso_cycles = worst_lso; }
  air56_off_dwt.cycles[index] = worst;
  air56_off_dwt.lso_cycles[index] = worst_lso;
  __DMB();
  air56_off_dwt.cases_done = index + 1U;
}
'''


def prepare():
    manifest = read_json(BASE/'verification.json')
    assert manifest['passed'] and manifest['hardware_commands']==0
    for name,digest in manifest['images_sha256'].items():
        assert sha(BASE/'image'/name)==digest
    shutil.copytree(BASE,OUT,ignore=shutil.ignore_patterns('pc_workspace','Debug','image',
                                                         '*.exe','*.log','limit_checks.c'))
    src=OUT/'Src'
    task_path=src/'mc_tasks.c'
    tasks=task_path.read_text(encoding='utf8')
    start=tasks.index('  inline uint16_t FOC_CurrControllerM1(void)')
    end=tasks.index('  return(hCodeError);\n}',start)+len('  return(hCodeError);\n}')
    assert 'FOCVars[M1].Valphabeta = Valphabeta;' in tasks[start:end]
    tasks=tasks[:start]+VOLTAGE+PROBE+tasks[end:]
    assert '#define DEBUG_LSO' not in (OUT/'Inc/acim_lso_parameters.h').read_text(encoding='utf8')
    task_path.write_text(tasks,encoding='utf8')
    main=src/'main.c'
    text=once(main.read_text(encoding='utf8'),'    /* USER CODE BEGIN 3 */',
              '    /* USER CODE BEGIN 3 */\n    extern void AIR56_OffDwtService(void);\n    AIR56_OffDwtService();')
    main.write_text(text,encoding='utf8')
    interface=src/'mc_interface.c'
    text=once(interface.read_text(encoding='utf8'),'  const uint32_t break_config = TIM1->BDTR;',
              '  extern bool AIR56_OffDwtReady(void);\n  if (!AIR56_OffDwtReady()) { return false; }\n'
              '  const uint32_t break_config = TIM1->BDTR;')
    interface.write_text(text,encoding='utf8')
    shutil.copyfile(BASE/'generation.log',OUT/'generation.log')


if __name__=='__main__':
    prepare()
