"""Stage the LSO slip-aware guard and frozen capture access in E-stop."""
from hashlib import sha256
import json
import shutil

from prepare_air56_lso_stationary_flux import OUT as BASE, NEW as OLD, ROOT, replace

OUT = BASE.with_name('air56_lso_field_guard_r1')
NEW = (2026112311, 2026112312)


def native_tasks(source):
    source = replace(source, '#include "parameters_conversion.h"',
                     '#include "parameters_conversion.h"\n#include "air56_lso_field_guard.h"')
    start = source.index('static float air56_field_total;')
    end = source.index('void TSK_SetChargeBootCapDelayM1', start)
    source = source[:start] + '''static air56_field_guard air56_run_field __attribute__((section(".ccmram.air56_start_record")));
static air56_field_fault air56_first_field_fault __attribute__((section(".ccmram.air56_start_record")));

static bool AIR56_FieldReady(void)
{
  if (Mci[M1].State != RUN)
  {
    air56_run_field.initialized = false;
    return true;
  }
  if (!air56_run_field.initialized)
  {
    const float scale = 65536.0f * RSHUNT * AMPLIFICATION_GAIN / ADC_REFERENCE_VOLTAGE;
    air56_run_field = (air56_field_guard){ .flux_counts = air56_start_flux_A * scale, .initialized = true };
  }
  const ACIM_LSO_Handle_t *lso = pACIM_LSO[M1];
  const float reference = STC_GetMecSpeedRefUnit(pSTC[M1]) * ((float)POLE_PAIR_NUM / SPEED_UNIT);
  air56_field_fault fault;
  if (air56_field_check(&air56_run_field, FOCVars[M1].Iqd, FOCVars[M1].Iqdref.q,
                        reference, lso->fRotorFluxFreq_rads, lso->fRotorElSpeed_obs_rads, &fault) == 0)
  {
    return true;
  }
  LL_TIM_DisableAllOutputs(TIM1);
  if (air56_lso_trace.active && !air56_first_field_fault.magic)
  {
    fault.start_ms = air56_lso_trace.start_ms;
    fault.magic = AIR56_FIELD_MAGIC;
    air56_first_field_fault = fault;
  }
  return false;
}

''' + source[end:]
    return replace(source, '''    const uint32_t lso_cycles = DWT->CYCCNT - begin;
    PWMC_GetPhaseCurrents''', '''    const uint32_t lso_cycles = DWT->CYCCNT - begin;
    /* Exercise window closure and division on every OFF timing case. */
    const float test_field = (index & 2U) ? 13.0f : 20.0f;
    air56_field_guard guard = { .initialized = true, .flux_counts = 843.0f,
      .frames = AIR56_FIELD_WINDOW - 1U, .field_sum = (AIR56_FIELD_WINDOW - 1U) * test_field,
      .rotor_sum = (AIR56_FIELD_WINDOW - 1U) * 7.0f,
      .reference_sum = (AIR56_FIELD_WINDOW - 1U) * 1.2f,
      .iq_sum = (AIR56_FIELD_WINDOW - 1U) * 243, .iq_ref_sum = (AIR56_FIELD_WINDOW - 1U) * 300 };
    air56_field_fault field_fault;
    const unsigned guard_result = air56_field_check(&guard, (qd_t){ .q = 243, .d = 843 },
                                                    300, 1.2f, test_field, 7.0f, &field_fault);
    if (guard_result != ((index & 2U) ? 0U : AIR56_FIELD_SLIP_DISAGREEMENT)) { code |= MC_SW_ERROR; }
    PWMC_GetPhaseCurrents''')


def native_wire(source):
    source = replace(source, '''    if (!pwm && air56_lso_trace.magic && !air56_lso_trace.active &&
        air56_lso_trace.reason && (start_page || trip_page || air56_page <= (air56_lso_trace.rows + 1U) / 2U))''', '''    const bool field_page = air56_first_field_fault.magic == AIR56_FIELD_MAGIC && air56_page == 261U;
    if (!pwm && air56_lso_trace.magic && !air56_lso_trace.active &&
        air56_lso_trace.reason && (field_page || start_page || trip_page || air56_page <= (air56_lso_trace.rows + 1U) / 2U))''')
    source = replace(source, '        if (start_page)\n        {', '''        if (field_page)
        {
            memcpy(p + 7, &air56_first_field_fault, sizeof(air56_first_field_fault));
        }
        else if (start_page)
        {''')
    return replace(source, '''    const bool page = mode == 8 && flags == 0 && p[6] == 7 && p[7] == 0 &&
                      page_index <= 260U''', '''    const bool page = mode == 8 && (flags == 0 || flags == 2U) && p[6] == 7 && p[7] == 0 &&
                      page_index <= 261U''')


def uno(source):
    source = replace(source, 'page>260U', 'page>261U')
    return replace(source, '''  if(g_ma_pending && ma_config_allowed(enable_eff,estop_eff,clear_eff,force,g_state==STATE_SAFE)){
    ma_config_encode(pkt,g_ma_op,g_ma_index,g_ma_value);mode=8;g_ma_pending=false;
  }''', '''  // A read-only LSO page may travel with E-stop asserted. Never clear its flag.
  const bool stopped_page = g_ma_op == 7 && g_ma_index == 0 && g_ma_value <= 261U && estop_eff &&
                            !enable_eff && !clear_eff && !force && !g_pwm_enabled && g_state == STATE_SAFE;
  if (g_ma_pending && (stopped_page || ma_config_allowed(enable_eff,estop_eff,clear_eff,force,g_state==STATE_SAFE))) {
    ma_config_encode(pkt,g_ma_op,g_ma_index,g_ma_value);
    if (stopped_page) { pkt[3] = BP_FLAG_ESTOP; }
    mode = 8;
    g_ma_pending = false;
  }''')


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
    shutil.copyfile(ROOT / 'tools/air56_lso_field_guard.h', OUT / 'Inc/air56_lso_field_guard.h')
    for name, edit in (('Src/mc_tasks.c', native_tasks), ('Inc/air56_lso_uno.inc', native_wire),
                       ('UNOQ_MOTOR/UNOQ_MOTOR.ino', uno), ('web_hmi/server.py', lambda source: replace(
                           source, 'int(page[2]) <= 260', 'int(page[2]) <= 261'))):
        path = OUT / name
        source = path.read_text(encoding='utf8')
        for old, new in zip(OLD, NEW):
            source = source.replace(str(old), str(new))
        path.write_text(edit(source), encoding='utf8')
    (OUT / 'preserved_inputs_sha256.json').write_text(json.dumps(preserved, indent=2) + '\n', encoding='utf8')
    print(OUT)


if __name__ == '__main__':
    main()
