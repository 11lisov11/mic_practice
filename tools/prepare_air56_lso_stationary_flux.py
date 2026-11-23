"""Stage a fixed-axis magnetization and measured-flux handoff to the ST LSO."""
from hashlib import sha256
import json
import shutil

from prepare_air56_lso_start_record import OUT as BASE, NEW as OLD, ROOT, replace

OUT = BASE.with_name('air56_lso_stationary_flux_r1')
NEW = (2026112309, 2026112310)


def tasks(source):
    source = replace(source, '#include "air56_lso_start_record.h"',
                     '#include "air56_lso_start_record.h"\n#include "unit_conversions.h"')
    source = replace(source, 'static float air56_field_total;', '''static float air56_start_flux_A;
static float air56_field_total;''')
    source = replace(source, '              bACIM_MagnValidCount = 0;', '''              bACIM_MagnValidCount = 0;
              air56_start_flux_A = 0.0f;''')
    source = replace(source, '              FOC_InitAdditionalMethods(M1);', '''              /* The fast loop holds angle zero until RUN, including during this handoff. */
              pACIM_LSO[M1]->fIqds_obs_A = Convert_s16_to_A(FOCVars[M1].Iqd);
              pACIM_LSO[M1]->fFlux_qdr_obs.fS_Component2 = air56_start_flux_A;
              FOC_InitAdditionalMethods(M1);''')
    source = replace(source, '  ACIM_LSO_CalcAngle(pACIM_LSO[M1]);', '''  if (Mci[M1].State != START)
  {
    ACIM_LSO_CalcAngle(pACIM_LSO[M1]);
  }''')
    source = replace(source, '''  const alphabeta_t applied = AIR56_CurrentVoltage(measured,
      ACIM_LSO_GetElAngle(pACIM_LSO[M1]), &FOCVars[M1], pPIDIq[M1], pPIDId[M1]);''', '''  const int16_t angle = Mci[M1].State == START ? 0 : ACIM_LSO_GetElAngle(pACIM_LSO[M1]);
  const alphabeta_t applied = AIR56_CurrentVoltage(measured, angle, &FOCVars[M1], pPIDIq[M1], pPIDId[M1]);''')
    source = replace(source, '''  bool bRetVal = false;

  FOCVars[M1].Iqdref = STC_GetDefaultIqdref(pSTC[M1]);''', '''  bool bRetVal = false;

  FOCVars[M1].Iqdref = STC_GetDefaultIqdref(pSTC[M1]);
  const float id_A = Convert_s16_to_A(FOCVars[M1].Iqd).fS_Component2;
  /* In the stationary frame lambda_r / Lm follows Id with the rotor time constant. */
  air56_start_flux_A += (id_A - air56_start_flux_A) / (MEDIUM_FREQUENCY_TASK_RATE * TAU_R);''')
    start = source.index('  if(bACIM_MagnValidCount<MAGN_VALIDATION_TICKS)\n  {')
    inner = source.index('    const int16_t id_ref', start)
    end = source.index('\n  }\n  else\n  {\n    bRetVal = true;', inner)
    tail = source.index('return bRetVal;', end) + len('return bRetVal;')
    body = '\n'.join(line[2:] if line else '' for line in source[inner:end].splitlines())
    source = source[:start] + body + '''

  bRetVal = bACIM_MagnValidCount == MAGN_VALIDATION_TICKS &&
            air56_start_flux_A >= Convert_s16_to_A((qd_t){ .d = id_low }).fS_Component2 &&
            air56_start_flux_A <= Convert_s16_to_A((qd_t){ .d = id_high }).fS_Component2;
  return bRetVal;''' + source[tail:]
    return replace(source, '    bACIM_MagnValidCount++;',
                   '    if (bACIM_MagnValidCount < MAGN_VALIDATION_TICKS) { ++bACIM_MagnValidCount; }')


def wire(source):
    source = replace(source, '    p[13] = fault ? (uint8_t)Mci[M1].State : 0;',
                     '    if (fault) { p[13] = (uint8_t)Mci[M1].State; }')
    source = replace(source, '    p[18] = 1;', '''    p[18] = 1;
    const ACIM_LSO_Handle_t *observer = pACIM_LSO[M1];
    if (observer && pwm && !fault && Mci[M1].State == RUN)
    {
        const float rpm = observer->fRotorSpeed_RPM;
        uint32_t serialized;
        memcpy(&serialized, &rpm, sizeof(serialized));
        if ((serialized & 0x7f800000U) != 0x7f800000U)
        {
            p[17] = 1;
            air56_uput(p + 27, serialized, sizeof(serialized));
        }
    }''')
    source = replace(source, '''    if (air56_lso_trace.active && (MCI_GetCurrentFaults(&Mci[M1]) ||
        MCI_GetOccurredFaults(&Mci[M1]) || !air56_break_ready() || !in_bus_range))''', '''    uint8_t stop_causes = 0;
    if (air56_lso_trace.active)
    {
        if (MCI_GetCurrentFaults(&Mci[M1])) { stop_causes |= 1U; }
        if (MCI_GetOccurredFaults(&Mci[M1])) { stop_causes |= 2U; }
        if (!air56_break_config()) { stop_causes |= 4U; }
        if (!(GPIOA->IDR & GPIO_PIN_6)) { stop_causes |= 8U; }
        if (!(TIM1->DIER & TIM_DIER_BIE)) { stop_causes |= 16U; }
        if (TIM1->SR & TIM_SR_BIF) { stop_causes |= 32U; }
        if (!in_bus_range) { stop_causes |= 64U; }
    }
    if (stop_causes)''')
    return replace(source, '        air56_capture_finish(AIR56_END_FAULT, now);', '''        air56_start_record.reserved = stop_causes;
        air56_capture_finish(AIR56_END_FAULT, now);''')


def main():
    report = json.loads((BASE / 'verification.json').read_text(encoding='utf8'))
    assert report['passed'] and report['pair'] == list(OLD)
    for name, expected in report['images_sha256'].items():
        assert sha256((BASE / 'image' / name).read_bytes()).hexdigest() == expected
    assert sha256((BASE / 'web_hmi/server.py').read_bytes()).hexdigest() == report['web_hmi_sha256']
    preserved = json.loads((BASE / 'preserved_inputs_sha256.json').read_text(encoding='utf8'))
    for folder in OUT.parent.glob('lso_230*_*/capture'):
        for path in folder.iterdir():
            if path.is_file():
                preserved[path.relative_to(ROOT).as_posix()] = sha256(path.read_bytes()).hexdigest()
    OUT.mkdir()
    for name in ('Drivers', 'Inc', 'MCSDK_v6.4.2-Full', 'Src', 'STM32CubeIDE', 'UNOQ_MOTOR', 'libraries', 'web_hmi'):
        shutil.copytree(BASE / name, OUT / name, ignore=shutil.ignore_patterns('Debug', 'Release', '__pycache__', '*.pyc'))
    for name in ('ACIM-AIR56B2-LSO_FOC.ioc', 'generation.log', 'AIR56B2_profile.json'):
        shutil.copyfile(BASE / name, OUT / name)
    for name in ('Src/mc_tasks.c', 'Inc/air56_lso_uno.inc', 'UNOQ_MOTOR/UNOQ_MOTOR.ino', 'web_hmi/server.py'):
        path = OUT / name
        source = path.read_text(encoding='utf8')
        for old, new in zip(OLD, NEW):
            source = source.replace(str(old), str(new))
        if name == 'Src/mc_tasks.c':
            source = tasks(source)
        if name == 'Inc/air56_lso_uno.inc':
            source = wire(source)
        path.write_text(source, encoding='utf8')
    (OUT / 'preserved_inputs_sha256.json').write_text(json.dumps(preserved, indent=2) + '\n', encoding='utf8')
    print(OUT)


if __name__ == '__main__':
    main()
