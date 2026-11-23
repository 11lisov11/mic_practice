"""Stage the motor-side START/RUN diagnostic on the sealed LSO firmware pair."""
from hashlib import sha256
import json
from pathlib import Path
import shutil

from prepare_air56_hmi_bounded_stop import OUT as HMI
from prepare_air56_lso_trip_capture import OUT as BASE, ROOT, replace

OUT = BASE.with_name('air56_lso_start_record_r1')
OLD = (2026112305, 2026112306)
NEW = (2026112307, 2026112308)


def edit(name, change, base=BASE):
    (OUT / name).write_text(change((base / name).read_text(encoding='utf8')), encoding='utf8')


def ids(source):
    for old, new in zip(OLD, NEW):
        source = source.replace(str(old), str(new))
    return source


def tasks(source):
    source = replace(source, '#include "air56_lso_capture.h"',
                     '#include "air56_lso_capture.h"\n#include "air56_lso_start_record.h"')
    source = replace(source, 'volatile air56_trace air56_lso_trace;',
                     '''volatile air56_trace air56_lso_trace;
static air56_lso_start_record air56_start_record __attribute__((section(".ccmram.air56_start_record")));''')
    source = replace(source, '  air56_lso_trace.start_ms = now;', '''  air56_start_record = (air56_lso_start_record){
    .magic = AIR56_START_RECORD_MAGIC, .start_ms = now, .id_min = INT16_MAX, .id_max = INT16_MIN,
    .speed_target = Mci[M1].hFinalSpeed, .ramp_command_state = (uint8_t)Mci[M1].CommandState
  };
  air56_lso_trace.start_ms = now;''')
    source = replace(source, '  air56_lso_trace.reason = reason;', '''  air56_start_record.end_ms = now;
  air56_start_record.terminal_state = (uint8_t)Mci[M1].State;
  air56_start_record.terminal_faults = MCI_GetCurrentFaults(&Mci[M1]) | MCI_GetOccurredFaults(&Mci[M1]);
  air56_start_record.stop_reason = (uint16_t)reason;
  air56_lso_trace.reason = reason;''')
    source = replace(source, '''              MCI_ExecBufferedCommands(&Mci[M1]); /* Exec the speed ramp after changing of the speed sensor */
              Mci[M1].State = RUN;''', '''              MCI_ExecBufferedCommands(&Mci[M1]); /* Exec the speed ramp after changing of the speed sensor */
              Mci[M1].State = RUN;
              if (air56_lso_trace.active)
              {
                air56_start_record.stages |= AIR56_START_RUN_ENTERED;
                air56_start_record.run_enter_ms = HAL_GetTick();
                air56_start_record.ramp_command_state = (uint8_t)Mci[M1].CommandState;
                air56_start_record.speed_target = Mci[M1].hFinalSpeed;
              }''')
    source = replace(source, '''            /* USER CODE BEGIN MediumFrequencyTask M1 3 */''', '''            if (air56_lso_trace.active)
            {
              const int16_t speed_ref = STC_GetMecSpeedRefUnit(pSTC[M1]);
              const int16_t iq_ref = FOCVars[M1].Iqdref.q;
              ++air56_start_record.run_checks;
              air56_start_record.speed_ref = speed_ref;
              if (speed_ref > air56_start_record.max_speed_ref) { air56_start_record.max_speed_ref = speed_ref; }
              if (iq_ref > air56_start_record.iq_ref_max) { air56_start_record.iq_ref_max = iq_ref; }
              air56_start_record.last_run_id = FOCVars[M1].Iqd.d;
              air56_start_record.last_run_iq = FOCVars[M1].Iqd.q;
            }

            /* USER CODE BEGIN MediumFrequencyTask M1 3 */''')
    return replace(source, '''    if((FOCVars[M1].Iqd.d >= ((int16_t)((float)FOCVars[M1].Iqdref.d * LOWER_BW_LIMIT_PERC)))&&
       (FOCVars[M1].Iqd.d <= ((int16_t)((float)FOCVars[M1].Iqdref.d * UPPER_BW_LIMIT_PERC))))
    {
      bACIM_MagnValidCount++;
    }
    else
    {
      bACIM_MagnValidCount = 0;
    }''', '''    const int16_t id_ref = FOCVars[M1].Iqdref.d;
    const int16_t id = FOCVars[M1].Iqd.d;
    const int16_t id_low = (int16_t)((float)id_ref * LOWER_BW_LIMIT_PERC);
    const int16_t id_high = (int16_t)((float)id_ref * UPPER_BW_LIMIT_PERC);
    const bool in_band = id >= id_low && id <= id_high;
    if (in_band)
    {
      bACIM_MagnValidCount++;
    }
    else
    {
      bACIM_MagnValidCount = 0;
    }
    if (air56_lso_trace.active)
    {
      if (!air56_start_record.checks)
      {
        air56_start_record.stages |= AIR56_START_CHECK_SEEN;
        air56_start_record.first_check_ms = HAL_GetTick();
      }
      ++air56_start_record.checks;
      if (in_band) { ++air56_start_record.in_band; }
      air56_start_record.id_ref = id_ref;
      air56_start_record.iq_ref = FOCVars[M1].Iqdref.q;
      air56_start_record.id_low = id_low;
      air56_start_record.id_high = id_high;
      air56_start_record.id_last = id;
      air56_start_record.iq_last = FOCVars[M1].Iqd.q;
      air56_start_record.last_streak = bACIM_MagnValidCount;
      if (id < air56_start_record.id_min) { air56_start_record.id_min = id; }
      if (id > air56_start_record.id_max) { air56_start_record.id_max = id; }
      if (bACIM_MagnValidCount > air56_start_record.max_streak)
      {
        air56_start_record.max_streak = bACIM_MagnValidCount;
      }
    }''')


def wire(source):
    source = replace(ids(source), 'page_index <= 258U', 'page_index <= 260U')
    source = replace(source, '''    if (!pwm && air56_lso_trace.magic && !air56_lso_trace.active &&
        air56_lso_trace.reason && (trip_page || air56_page <= (air56_lso_trace.rows + 1U) / 2U))''',
        '''    const bool start_page = air56_start_record.magic == AIR56_START_RECORD_MAGIC &&
                            (air56_page == 259U || air56_page == 260U);
    if (!pwm && air56_lso_trace.magic && !air56_lso_trace.active &&
        air56_lso_trace.reason && (start_page || trip_page || air56_page <= (air56_lso_trace.rows + 1U) / 2U))''')
    return replace(source, '        if (trip_page)\n        {', '''        if (start_page)
        {
            const uint8_t *raw = (const uint8_t *)&air56_start_record;
            const unsigned offset = 32U * (air56_page - 259U);
            for (unsigned i = 0; i < 32U; ++i) { p[7 + i] = raw[offset + i]; }
        }
        else if (trip_page)
        {''')


def main():
    source_report = json.loads((BASE / 'verification.json').read_text(encoding='utf8'))
    hmi_report = json.loads((HMI / 'verification.json').read_text(encoding='utf8'))
    assert source_report['passed'] and source_report['pair'] == list(OLD)
    assert hmi_report['passed'] and sha256((HMI / 'server.py').read_bytes()).hexdigest() == hmi_report['server_sha256']
    for name, expected in source_report['images_sha256'].items():
        assert sha256((BASE / 'image' / name).read_bytes()).hexdigest() == expected
    preserved = {}
    for folder in OUT.parent.glob('lso_230*_*/capture'):
        for file in folder.iterdir():
            if file.is_file():
                preserved[file.relative_to(ROOT).as_posix()] = sha256(file.read_bytes()).hexdigest()
    OUT.mkdir()
    for name in ('Drivers', 'Inc', 'MCSDK_v6.4.2-Full', 'Src', 'STM32CubeIDE', 'UNOQ_MOTOR', 'libraries', 'web_hmi'):
        shutil.copytree(BASE / name, OUT / name, ignore=shutil.ignore_patterns('Debug', 'Release', '__pycache__', '*.pyc'))
    for name in ('ACIM-AIR56B2-LSO_FOC.ioc', 'generation.log', 'AIR56B2_profile.json'):
        shutil.copyfile(BASE / name, OUT / name)
    shutil.copyfile(ROOT / 'tools/air56_lso_start_record.h', OUT / 'Inc/air56_lso_start_record.h')
    edit('Src/mc_tasks.c', tasks)
    edit('STM32CubeIDE/STM32G431RBTX_FLASH.ld', lambda s: replace(
        s, '    _eccmram = .;', '    *(.ccmram.air56_start_record)\n    _eccmram = .;'))
    edit('Inc/air56_lso_uno.inc', wire)
    edit('UNOQ_MOTOR/UNOQ_MOTOR.ino', lambda s: replace(ids(s), 'page>258U', 'page>260U'))
    server = replace(ids((HMI / 'server.py').read_text(encoding='utf8')), 'int(page[2]) <= 258', 'int(page[2]) <= 260')
    (OUT / 'web_hmi/server.py').write_text(server, encoding='utf8')
    (OUT / 'preserved_inputs_sha256.json').write_text(json.dumps(preserved, indent=2) + '\n', encoding='utf8')
    print(OUT)


if __name__ == '__main__':
    main()
