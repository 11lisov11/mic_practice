"""Stage the LSO first-overcurrent recorder without accessing either board."""
import json
import shutil
from hashlib import sha256
from pathlib import Path

from prepare_air56_lso_timing_aspep import ROOT, replace

BASE = ROOT / 'artifacts/live_bench_20261122/air56_st_lso_uart_startup_r1'
OUT = ROOT / 'artifacts/live_bench_20261123/air56_lso_trip_capture_r1'
OLD = (2026112303, 2026112304)
NEW = (2026112305, 2026112306)
DRIVER = Path('MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLib/G4xx/Src/r3_2_g4xx_pwm_curr_fdbk.c')


def change(path, edit):
    file = OUT / path
    file.write_text(edit(file.read_text(encoding='utf8')), encoding='utf8')


def update_ids(source):
    for before, after in zip(OLD, NEW):
        source = source.replace(str(before), str(after))
    return source


def capture_raw_read(source):
    start = source.index('__weak void R3_2_GetPhaseCurrents(')
    end = source.index('__weak void R3_2_GetPhaseCurrents_OVM(', start)
    driver = replace(source[start:end],
        '    ADCDataReg2 = pHandle->pParams_str->ADCDataReg2[Sector]->JDR1;',
        '''    ADCDataReg2 = pHandle->pParams_str->ADCDataReg2[Sector]->JDR1;
    extern volatile uint32_t air56_trip_raw_pair;
    extern volatile uint32_t air56_trip_adc_timer;
    air56_trip_raw_pair = (ADCDataReg1 & 0xFFFFU) | (ADCDataReg2 << 16);
    air56_trip_adc_timer = (TIMx->CNT & 0xFFFFU) | (TIMx->CR1 << 16);''')
    return source[:start] + driver + source[end:]


def motor_task(source):
    source = replace(source, 'volatile air56_trace air56_lso_trace;',
        '''volatile air56_trace air56_lso_trace;
volatile uint32_t air56_trip_raw_pair;
volatile uint32_t air56_trip_adc_timer;
static volatile uint32_t air56_trip_record[16];
static volatile bool air56_trip_saved;

/* Published only after PWM is disabled; CLEAR leaves this record intact. */
static void air56_save_overcurrent(const ab_t *measured)
{
  if (!air56_lso_trace.active || air56_trip_saved) { return; }
  const PWMC_R3_2_Handle_t *pwm = (const PWMC_R3_2_Handle_t *)pwmcHandle[M1];
  air56_trip_record[0] = 0x3150434CU; /* LCP1 */
  air56_trip_record[1] = air56_lso_trace.start_ms;
  air56_trip_record[2] = HAL_GetTick();
  air56_trip_record[3] = DWT->CYCCNT - air56_lso_trace.start_cycles;
  air56_trip_record[4] = air56_lso_trace.injected_samples;
  air56_trip_record[5] = air56_trip_raw_pair;
  air56_trip_record[6] = pwm->PhaseAOffset;
  air56_trip_record[7] = pwm->PhaseBOffset;
  air56_trip_record[8] = pwm->PhaseCOffset;
  air56_trip_record[9] = (uint16_t)measured->a | ((uint32_t)(uint16_t)measured->b << 16);
  air56_trip_record[10] = pwm->_Super.Sector;
  const uint32_t adc_timer = air56_trip_adc_timer;
  air56_trip_record[11] = (adc_timer & 0xFFFFU) | (TIM1->ARR << 16);
  air56_trip_record[12] = (adc_timer >> 16) | (TIM1->SR << 16);
  air56_trip_record[13] = (TIM1->CCR1 & 0xFFFFU) | (TIM1->CCR2 << 16);
  air56_trip_record[14] = (TIM1->CCR3 & 0xFFFFU) | (TIM1->CCR4 << 16);
  air56_trip_record[15] = (ADC1->ISR & 0xFFFFU) | (ADC2->ISR << 16);
  __DMB();
  air56_trip_saved = true;
}''')
    return replace(source, '''    LL_TIM_DisableAllOutputs(TIM1);
    return MC_OVER_CURR;''', '''    LL_TIM_DisableAllOutputs(TIM1);
    air56_save_overcurrent(&measured);
    return MC_OVER_CURR;''')


def nucleo_wire(source):
    source = update_ids(source)
    source = replace(source, 'page_index <= 256U', 'page_index <= 258U')
    source = replace(source, '''    if (!pwm && air56_lso_trace.magic && !air56_lso_trace.active &&
        air56_lso_trace.reason && air56_page <= (air56_lso_trace.rows + 1U) / 2U)''',
        '''    const bool trip_page = air56_trip_saved && (air56_page == 257U || air56_page == 258U);
    if (!pwm && air56_lso_trace.magic && !air56_lso_trace.active &&
        air56_lso_trace.reason && (trip_page || air56_page <= (air56_lso_trace.rows + 1U) / 2U))''')
    return replace(source, '''        if (!air56_page)
        {''', '''        if (trip_page)
        {
            const unsigned first = 8U * (air56_page - 257U);
            for (unsigned i = 0; i < 8U; ++i) { air56_uput(p + 7 + 4 * i, air56_trip_record[first + i], 4); }
        }
        else if (!air56_page)
        {''')


def main():
    approved = json.loads((BASE / 'uart_startup_PC.json').read_text(encoding='utf8'))
    assert approved['passed'] and approved['pair'] == list(OLD)
    for filename, digest in approved['images_sha256'].items():
        assert sha256((BASE / 'image' / filename).read_bytes()).hexdigest() == digest
    preserved = {}
    for path in OUT.parent.glob('lso_2304_5hz_*'):
        for file in path.rglob('*'):
            if file.is_file():
                preserved[file.relative_to(ROOT).as_posix()] = sha256(file.read_bytes()).hexdigest()
    OUT.mkdir()
    for name in ('Drivers', 'Inc', 'MCSDK_v6.4.2-Full', 'Src', 'STM32CubeIDE', 'UNOQ_MOTOR', 'libraries', 'web_hmi'):
        shutil.copytree(BASE / name, OUT / name, ignore=shutil.ignore_patterns('Debug', 'Release', '__pycache__', '*.pyc'))
    for name in ('ACIM-AIR56B2-LSO_FOC.ioc', 'generation.log', 'AIR56B2_profile.json'):
        shutil.copyfile(BASE / name, OUT / name)
    change(DRIVER, capture_raw_read)
    change('Src/mc_tasks.c', motor_task)
    change('Inc/air56_lso_uno.inc', nucleo_wire)
    change('UNOQ_MOTOR/UNOQ_MOTOR.ino',
           lambda source: replace(update_ids(source), 'page>256U', 'page>258U'))
    change('web_hmi/server.py',
           lambda source: replace(update_ids(source), 'int(page[2]) <= 256', 'int(page[2]) <= 258'))
    for filename, digest in preserved.items():
        assert sha256((ROOT / filename).read_bytes()).hexdigest() == digest
    (OUT / 'preserved_inputs_sha256.json').write_text(json.dumps(preserved, indent=2) + '\n', encoding='utf8')
    print(OUT)


if __name__ == '__main__':
    main()
