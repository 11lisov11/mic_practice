"""Keep the official FOC implementation and add the established bench limits."""

import argparse
import json
import re
from pathlib import Path

from prepare_air56_st_lso_reference import OUT


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Expected one generated block: {old!r}')
    return text.replace(old,new)


def prepare(out):
    model = json.loads((out/'AIR56B2_profile.json').read_text(encoding='utf-8'))
    assert model['raw_trip_counts']==2252 and model['reference_limit_counts']==1334
    inc,src = out/'Inc',out/'Src'
    assert not (inc/'air56_st_lso_limits.h').exists()
    files = {name:(src/name).read_text(encoding='utf-8-sig')
             for name in ('main.c','mc_tasks.c','mc_interface.c','stm32g4xx_mc_it.c')}
    main = files['main.c']
    # Keep active-low PA6/BKIN, the deployed digital filter and manual re-arm.
    for line in ('sBreakInputConfig.Source = TIM_BREAKINPUTSOURCE_BKIN;',
                 'sBreakInputConfig.Enable = TIM_BREAKINPUTSOURCE_ENABLE;',
                 'sBreakInputConfig.Polarity = TIM_BREAKINPUTSOURCE_POLARITY_LOW;',
                 'sBreakDeadTimeConfig.BreakState = TIM_BREAK_ENABLE;',
                 'sBreakDeadTimeConfig.AutomaticOutput = TIM_AUTOMATICOUTPUT_DISABLE;'):
        assert line in main,line
    main,n = re.subn(r'sBreakDeadTimeConfig\.BreakFilter = \d+;',
                     'sBreakDeadTimeConfig.BreakFilter = 9;',main)
    assert n==1
    main = once(main,'  MX_MotorControl_Init();','''  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CYCCNT = 0;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
  MX_MotorControl_Init();''')
    files['main.c']=main
    tasks = once(files['mc_tasks.c'],'#include "mc_tasks.h"',
                 '#include "mc_tasks.h"\n#include "air56_st_lso_limits.h"')
    tasks = field_guard(tasks)
    marker = '/* USER CODE BEGIN Private variables */'
    if marker not in tasks:
        marker = 'ACIM_LSO_Handle_t *pACIM_LSO[NBR_OF_MOTORS];'
    tasks = once(tasks,marker,marker+'''
static volatile uint32_t air56_adc_stamp;
static uint32_t air56_last_packet_ms;
static uint32_t air56_start_ms;
static bool air56_run_started;

/* Called by the timer independently of ADC completion. An absent ADC
 * interrupt cannot hold the last duty cycle indefinitely. */
void AIR56_LsoWatchAdc(void)
{
  const MCI_State_t state = Mci[M1].State;
  if ((state == START || state == RUN) && LL_TIM_IsEnabledAllOutputs(TIM1) &&
      air56_lso_stale(DWT->CYCCNT, air56_adc_stamp, AIR56_LSO_ADC_AGE_CYCLES))
  {
    LL_TIM_DisableAllOutputs(TIM1);
    MCI_FaultProcessing(&Mci[M1], MC_DURATION, 0);
  }
}
''')
    tasks = once(tasks,'          MCP_ReceivedPacket(&MCP_Over_UartA);','''          MCP_ReceivedPacket(&MCP_Over_UartA);
          if (MCP_Over_UartA.txLength > 0U &&
              MCP_Over_UartA.txBuffer[MCP_Over_UartA.txLength - 1U] == MCP_CMD_OK)
          {
            air56_last_packet_ms = HAL_GetTick();
          }''')
    tasks = once(tasks,'      switch (Mci[M1].State)','''      const MCI_State_t bench_state = Mci[M1].State;
      if (bench_state == IDLE && Mci[M1].DirectCommand == MCI_START)
      {
        air56_start_ms = HAL_GetTick();
        air56_run_started = true;
      }
      if (air56_run_started &&
          air56_lso_stale(HAL_GetTick(), air56_start_ms, AIR56_LSO_RUN_MS))
      {
        Mci[M1].DirectCommand = MCI_NO_COMMAND;
        TSK_MF_StopProcessing(M1);
        air56_run_started = false;
        return;
      }
      if (air56_run_started && (bench_state == STOP || bench_state == IDLE) &&
          Mci[M1].DirectCommand != MCI_START)
      {
        air56_run_started = false;
      }
      if (air56_run_started &&
          air56_lso_stale(HAL_GetTick(), air56_last_packet_ms, AIR56_LSO_LINK_MS))
      {
        LL_TIM_DisableAllOutputs(TIM1);
        air56_run_started = false;
        Mci[M1].DirectCommand = MCI_NO_COMMAND;
        MCI_FaultProcessing(&Mci[M1], MC_SW_ERROR, 0);
        return;
      }
      switch (Mci[M1].State)''')
    tasks = once(tasks,'              Mci[M1].State = START;\n              R3_2_SwitchOnPWM',
                 '              air56_adc_stamp = DWT->CYCCNT;\n'
                 '              Mci[M1].State = START;\n              R3_2_SwitchOnPWM')
    tasks = once(tasks,'  ACIM_LSO_CalcAngle(pACIM_LSO[M1]);','''  const uint32_t air56_begin = DWT->CYCCNT;
  ACIM_LSO_CalcAngle(pACIM_LSO[M1]);''')
    tasks = once(tasks,'''  if(returnValue == MC_DURATION)
  {
    MCI_FaultProcessing(&Mci[M1], MC_DURATION, 0);
  }
  else
  {''','''  if ((Mci[M1].State == START || Mci[M1].State == RUN) &&
      DWT->CYCCNT - air56_begin > AIR56_LSO_FAST_CYCLES)
  {
    returnValue |= MC_DURATION;
  }
  if (returnValue != MC_NO_FAULTS)
  {
    LL_TIM_DisableAllOutputs(TIM1);
    MCI_FaultProcessing(&Mci[M1], returnValue, 0);
  }
  else
  {
    air56_adc_stamp = air56_begin;''')
    tasks = once(tasks,'  PWMC_GetPhaseCurrents(pwmcHandle[M1], &Iab);\n  Ialphabeta = MCM_Clarke(Iab);',
                 '''  PWMC_GetPhaseCurrents(pwmcHandle[M1], &Iab);
  if ((Mci[M1].State == START || Mci[M1].State == RUN) &&
      air56_lso_overcurrent(Iab.a, Iab.b))
  {
    LL_TIM_DisableAllOutputs(TIM1);
    return MC_OVER_CURR;
  }
  Ialphabeta = MCM_Clarke(Iab);''')
    # Preserve the calculated flux reference and magnitude cap even if an
    # external tool requests arbitrary Id/Iq or regenerative torque.
    tasks = once(tasks,'''  Vqd.q = PI_Controller(pPIDIq[M1], (int32_t)(FOCVars[M1].Iqdref.q) - Iqd.q);
  Vqd.d = PI_Controller(pPIDId[M1], (int32_t)(FOCVars[M1].Iqdref.d) - Iqd.d);''','''  int32_t iq_ref = FOCVars[M1].Iqdref.q;
  if (iq_ref < 0) { iq_ref = 0; }
  if (iq_ref > IQMAX) { iq_ref = IQMAX; }
  Vqd.q = PI_Controller(pPIDIq[M1], iq_ref - Iqd.q);
  /* The ACIM generator emits DEFAULT_FLUX_COMPONENT_A in integer current
   * units, as used by SpeednTorqCtrlM1.IdrefDefault. */
  Vqd.d = PI_Controller(pPIDId[M1], (int32_t)DEFAULT_FLUX_COMPONENT_A - Iqd.d);''')
    begin = tasks.index('/* USER CODE BEGIN START_STOP_BTN */',tasks.index('void UI_HandleStartStopButton_cb'))
    end = tasks.index('/* USER CODE END START_STOP_BTN */',begin)
    tasks = tasks[:begin]+'''/* USER CODE BEGIN START_STOP_BTN */
  /* The local button is STOP only. Motor Pilot is the command owner. */
  (void)MCI_StopMotor(&Mci[M1]);
'''+tasks[end:]
    files['mc_tasks.c']=tasks
    it = once(files['stm32g4xx_mc_it.c'],'    R3_2_TIMx_UP_IRQHandler(&PWM_Handle_M1);',
              '    extern void AIR56_LsoWatchAdc(void);\n'
              '    AIR56_LsoWatchAdc();\n    R3_2_TIMx_UP_IRQHandler(&PWM_Handle_M1);')
    files['stm32g4xx_mc_it.c']=it
    interface = once(files['mc_interface.c'],'''  pHandle->lastCommand = MCI_CMD_EXECSPEEDRAMP;
  pHandle->hFinalSpeed = hFinalSpeed;''','''  if (hFinalSpeed < 0 || hFinalSpeed > RPM_2_SPEED_UNIT(300))
  {
    pHandle->CommandState = MCI_COMMAND_EXECUTED_UNSUCCESSFULLY;
    return;
  }
  if (hDurationms < 1000U) { hDurationms = 1000U; }
  pHandle->lastCommand = MCI_CMD_EXECSPEEDRAMP;
  pHandle->hFinalSpeed = hFinalSpeed;''')
    for command,args in (('EXECTORQUERAMP','  (void)hFinalTorque;\n  (void)hDurationms;\n'),
                         ('SETCURRENTREFERENCES','  (void)Iqdref;\n')):
        start = interface.index('  pHandle->lastCommand = MCI_CMD_'+command+';')
        end = interface.index('\n}',start)
        interface = interface[:start]+args+'''  pHandle->CommandState = MCI_COMMAND_EXECUTED_UNSUCCESSFULLY;'''+interface[end:]
    interface=guard_start(interface)
    files['mc_interface.c']=interface
    header = Path(__file__).with_name('air56_st_lso_limits.h').read_text(encoding='utf-8')
    (inc/'air56_st_lso_limits.h').write_text(header,encoding='utf-8')
    for name,text in files.items():
        (src/name).write_text(text,encoding='utf-8')


def guard_start(interface):
    interface = once(interface,'#include "mc_interface.h"','#include "mc_interface.h"\n#include "main.h"')
    signature = '__weak bool MCI_StartMotor(MCI_Handle_t *pHandle)\n{\n  bool RetVal;'
    return once(interface,signature,signature+'''
  const uint32_t break_config = TIM1->BDTR;
  if (!(GPIOA->IDR & GPIO_PIN_6) || !(break_config & TIM_BDTR_BKE) ||
      !(TIM1->DIER & TIM_DIER_BIE) || (TIM1->SR & TIM_SR_BIF))
  {
    return false;
  }''')


def field_guard(tasks):
    tasks = once(tasks,'#include "air56_st_lso_limits.h"',
                 '#include "air56_st_lso_limits.h"\n#include <string.h>')
    declarations = 'static uint16_t FOC_CurrControllerM1(void);'
    tasks = once(tasks,declarations,declarations+'''
static float air56_field_total;
static float air56_field_limit;
static uint16_t air56_field_frames;

/* Same 16 ms field-rate supervision and 0.75 Hz margin as the experimental
 * profile, expressed using the ST angle derivative in rad/s. */
static bool AIR56_FieldReady(void)
{
  if (Mci[M1].State != RUN)
  {
    air56_field_frames = 0;
    air56_field_total = 0.0f;
    air56_field_limit = 0.0f;
    return true;
  }
  const float rate = pACIM_LSO[M1]->fRotorFluxFreq_rads;
  uint32_t bits;
  memcpy(&bits, &rate, sizeof(bits));
  if ((bits & 0x7f800000U) == 0x7f800000U) { return false; }
  const int16_t reference = STC_GetMecSpeedRefUnit(pSTC[M1]);
  const float hz = (float)reference * ((float)POLE_PAIR_NUM / SPEED_UNIT);
  air56_field_total += rate;
  air56_field_limit += (hz + 0.75f) * 6.2831853072f;
  if (++air56_field_frames < 256U) { return true; }
  const bool allowed = air56_field_total <= air56_field_limit &&
                      air56_field_total >= -air56_field_limit;
  air56_field_frames = 0;
  air56_field_total = 0.0f;
  air56_field_limit = 0.0f;
  return allowed;
}
''')
    return once(tasks,'  returnValue = FOC_CurrControllerM1();',
                '  returnValue = AIR56_FieldReady() ? FOC_CurrControllerM1() : MC_SPEED_FDBK;')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUT)
    prepare(parser.parse_args().output.resolve())
