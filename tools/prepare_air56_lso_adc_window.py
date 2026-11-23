"""Stage guarded three-shunt acquisition and bounded stationary magnetization."""
import json
from hashlib import sha256
import shutil

from prepare_air56_lso_run_handoff import OUT as BASE, NEW as OLD, ROOT, replace

OUT = BASE.with_name('air56_lso_adc_window_r1')
NEW = (2026112315, 2026112316)
DRIVER = 'MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLib/G4xx/Src/r3_2_g4xx_pwm_curr_fdbk.c'


def driver(source):
    source = replace(source, '#include "mc_type.h"', '''#include "mc_type.h"
#include "current_adc_window_plan.h"

/* Reuse the quiet aperture geometry validated on this three-shunt board. */
enum { AIR56_ADC_APEX_RESERVE = 128U, AIR56_ADC_SETTLE_TICKS = 771U, AIR56_ADC_ACQUIRE_TICKS = 112U };''')
    function = source.index('uint16_t R3_2_SetADCSampPointSectX(PWMC_Handle_t *pHdl)\n{')
    begin = source.index('    uint16_t SamplingPoint;', function)
    end = source.index('\n#ifdef NULL_PTR_CHECK_R3_2_PWM_CURR_FDB', begin)
    source = source[:begin] + '''    const uint16_t half = pHandle->Half_PWMPeriod;
    const mic_current_window_plan plan = mic_plan_current_window(pHdl->CntPhA, pHdl->CntPhB, pHdl->CntPhC,
        half > AIR56_ADC_APEX_RESERVE ? half - AIR56_ADC_APEX_RESERVE : 0U,
        AIR56_ADC_SETTLE_TICKS, AIR56_ADC_ACQUIRE_TICKS);
    if (!plan.valid)
    {
      /* Do not publish duties for a frame without two settled measurements. */
      returnValue = MC_DURATION;
    }
    else
    {
      static const uint8_t sectors[] = { SECTOR_5, SECTOR_2, SECTOR_1 }; /* UV, UW, VW */
      pHdl->Sector = sectors[plan.pair];
      pHandle->ADCTriggerEdge = LL_ADC_INJ_TRIG_EXT_RISING;
      returnValue = R3_2_WriteTIMRegisters(pHdl, (uint16_t)plan.trigger);
    }''' + source[end:]
    return source


def tasks(source):
    source = replace(source, 'static float air56_start_flux_A;', '''static float air56_start_flux_A;
static uint16_t air56_magnetization_steps;
static volatile int16_t air56_magnetization_id;

enum { AIR56_MAGNETIZATION_STEPS = 30 }; /* 60 ms at the 500 Hz medium task rate. */

static void AIR56_CurrentPILimits(PID_Handle_t *pid, int16_t limit, uint16_t divisor)
{
  PID_SetUpperOutputLimit(pid, limit);
  PID_SetLowerOutputLimit(pid, -limit);
  PID_SetUpperIntegralTermLimit(pid, (int32_t)limit * divisor);
  PID_SetLowerIntegralTermLimit(pid, -(int32_t)limit * divisor);
}''')
    source = replace(source, '              air56_start_flux_A = 0.0f;', '''              air56_start_flux_A = 0.0f;
              air56_magnetization_steps = 0;
              air56_magnetization_id = 0;
              /* About 6.2 V holds the target Id at the profile Rs. A 60 ms
               * slew leaves inductive and inverter-drop margin at 14 V per
               * axis. Convert against the maximum admitted bus to cap dq
               * voltage below 20 V throughout stationary magnetization.
               */
              const int16_t voltage_limit = (int16_t)(14.0f * 1.7320508076f * 32767.0f / 350.0f);
              AIR56_CurrentPILimits(pPIDIq[M1], voltage_limit, T_KIDIV);
              AIR56_CurrentPILimits(pPIDId[M1], voltage_limit, F_KIDIV);''')
    source = replace(source, '''              MCI_ExecBufferedCommands(&Mci[M1]); /* Exec the speed ramp after changing of the speed sensor */
              Mci[M1].State = RUN;''', '''              MCI_ExecBufferedCommands(&Mci[M1]); /* Exec the speed ramp after changing of the speed sensor */
              const uint32_t handoff_mask = __get_PRIMASK();
              __disable_irq();
              AIR56_CurrentPILimits(pPIDIq[M1], INT16_MAX, T_KIDIV);
              AIR56_CurrentPILimits(pPIDId[M1], INT16_MAX, F_KIDIV);
              Mci[M1].State = RUN;
              __set_PRIMASK(handoff_mask);''')
    source = replace(source, '''    FOCVars_t *foc, PID_Handle_t *pid_q, PID_Handle_t *pid_d)
{''', '''    FOCVars_t *foc, PID_Handle_t *pid_q, PID_Handle_t *pid_d, int16_t id_ref)
{''')
    source = replace(source, 'PI_Controller(pid_d, (int32_t)DEFAULT_FLUX_COMPONENT_A - measured.d)',
                     'PI_Controller(pid_d, (int32_t)id_ref - measured.d)')
    source = replace(source, '''  const int16_t angle = Mci[M1].State == START ? 0 : ACIM_LSO_GetElAngle(pACIM_LSO[M1]);
  const alphabeta_t applied = AIR56_CurrentVoltage(measured, angle, &FOCVars[M1], pPIDIq[M1], pPIDId[M1]);''', '''  const bool magnetizing = Mci[M1].State == START;
  const int16_t angle = magnetizing ? 0 : ACIM_LSO_GetElAngle(pACIM_LSO[M1]);
  const int16_t id_ref = magnetizing ? air56_magnetization_id : DEFAULT_FLUX_COMPONENT_A;
  const alphabeta_t applied = AIR56_CurrentVoltage(measured, angle, &FOCVars[M1], pPIDIq[M1], pPIDId[M1], id_ref);''')
    source = replace(source, '''        ACIM_LSO_GetElAngle(&lso), &foc, &iq, &id);''',
                     '''        ACIM_LSO_GetElAngle(&lso), &foc, &iq, &id, DEFAULT_FLUX_COMPONENT_A);''')
    source = replace(source, '''  const int16_t id_ref = FOCVars[M1].Iqdref.d;
  const int16_t id = current.d;''', '''  const int16_t id_ref = FOCVars[M1].Iqdref.d;
  if (air56_magnetization_steps < AIR56_MAGNETIZATION_STEPS)
  {
    ++air56_magnetization_steps;
    air56_magnetization_id = (int16_t)(DEFAULT_FLUX_COMPONENT_A * air56_magnetization_steps / AIR56_MAGNETIZATION_STEPS);
  }
  const int16_t id = current.d;''')
    return replace(source, '  if (in_band && iq_ready)',
                   '  if (air56_magnetization_steps == AIR56_MAGNETIZATION_STEPS && in_band && iq_ready)')


def main():
    report = json.loads((BASE / 'verification.json').read_text(encoding='utf8'))
    assert report['passed'] and report['pair'] == list(OLD)
    for name, expected in report['images_sha256'].items():
        assert sha256((BASE / 'image' / name).read_bytes()).hexdigest() == expected
    assert sha256((BASE / 'web_hmi/server.py').read_bytes()).hexdigest() == report['web_hmi_sha256']
    preserved = json.loads((BASE / 'preserved_inputs_sha256.json').read_text(encoding='utf8'))
    for folder in OUT.parent.glob('lso_23*'):
        if folder.is_dir():
            for path in folder.rglob('*'):
                if path.is_file():
                    preserved[path.relative_to(ROOT).as_posix()] = sha256(path.read_bytes()).hexdigest()
    OUT.mkdir()
    for name in ('Drivers', 'Inc', 'MCSDK_v6.4.2-Full', 'Src', 'STM32CubeIDE', 'UNOQ_MOTOR', 'libraries', 'web_hmi'):
        shutil.copytree(BASE / name, OUT / name, ignore=shutil.ignore_patterns('Debug', 'Release', '__pycache__', '*.pyc'))
    for name in ('ACIM-AIR56B2-LSO_FOC.ioc', 'generation.log', 'AIR56B2_profile.json'):
        shutil.copyfile(BASE / name, OUT / name)
    shutil.copyfile(ROOT / 'tools/current_adc_window_plan.h', OUT / 'Inc/current_adc_window_plan.h')
    edits = {'Src/mc_tasks.c': tasks, DRIVER: driver, 'Inc/air56_lso_uno.inc': lambda s: s,
             'UNOQ_MOTOR/UNOQ_MOTOR.ino': lambda s: s, 'web_hmi/server.py': lambda s: s}
    for name, edit in edits.items():
        path = OUT / name
        source = path.read_text(encoding='utf8')
        for old, new in zip(OLD, NEW):
            source = source.replace(str(old), str(new))
        path.write_text(edit(source), encoding='utf8')
    (OUT / 'preserved_inputs_sha256.json').write_text(json.dumps(preserved, indent=2) + '\n', encoding='utf8')
    print(OUT)


if __name__ == '__main__':
    main()
