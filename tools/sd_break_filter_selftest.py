"""Offline configuration execution and phase sweep; never contacts hardware."""
from pathlib import Path
import importlib.util
import json
import math
import re
import subprocess
import sys
import prepare_sd_break_filter_fix as package
from uart_tx_dma_selftest import body

C, BASE, ROOT = package.OUT, package.BASE, package.ROOT


def main():
    out = C / 'filter_selftest'
    out.mkdir(exist_ok=True)
    checks = []

    def check(value, name):
        checks.append(dict(name=name, passed=bool(value)))
        if not value:
            raise AssertionError(name)

    read = package.read
    # Prove all source differences are exactly identities + the declared filter
    # and readback predicate; retain the complete real UART/ISR/control code.
    for tree in ('nucleo/Inc', 'nucleo/Src', 'nucleo/Drivers', 'nucleo/Middlewares', 'UNOQ_MOTOR'):
        for p in (BASE / tree).rglob('*'):
            if not p.is_file():
                continue
            relative = p.relative_to(BASE)
            if tree in ('nucleo/Drivers', 'nucleo/Middlewares'):
                check((C / relative).read_bytes() == p.read_bytes(), 'unchanged library: ' + relative.as_posix())
                continue
            expected = read(p).replace(str(package.OLD[0]), str(package.NEW[0])).replace(str(package.OLD[1]), str(package.NEW[1]))
            if relative.as_posix() == 'nucleo/Src/main.c':
                expected = package.once(expected, package.FILTER_OLD, package.FILTER_NEW)
                expected = package.once(expected, package.CONFIG_OLD, package.CONFIG_NEW)
            check(read(C / relative) == expected, 'exact source scope: ' + relative.as_posix())
    ioc = next((C / 'nucleo').glob('*.ioc'))
    check(read(ioc).replace('TIM1.BreakFilter=9\n', 'TIM1.BreakFilter=3\n') == read(next((BASE / 'nucleo').glob('*.ioc'))), 'CubeMX regeneration retains BKF9')
    hmi_source = read(C / 'web_hmi/server.py')
    previous = hmi_source.replace('        (2026102001, 2026102002),\n', '').replace(',(2026102001,2026102002)', '').replace(',2026102002)', ')').replace(', 2026102002)', ')')
    check(previous == read(package.HMI), 'HMI changes only supported identities; all controls retained')
    spec = importlib.util.spec_from_file_location('filter_hmi', C / 'web_hmi/server.py')
    hmi = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = hmi
    spec.loader.exec_module(hmi)
    for uno, nuc in (package.OLD, package.NEW):
        check(hmi.manual_scalar_supported(dict(fw_build=uno, mc_fw_build=nuc, manual_scalar_capable=1)), 'manual pair ' + str(uno))
        check(hmi.sd_live_status(dict(mc_fw_build=nuc, mc_age_ms=0, bp_temp_flags=189))['config_ok'], 'live SD pair ' + str(nuc))
    oldcal = dict(fw_build=package.OLD[0], mc_fw_build=package.OLD[1], rpc_schema_version=3, mc_capabilities=1, mc_mcsdk_telemetry=1)
    check(hmi._vbus_calibration_identity_matches(oldcal, dict(oldcal, fw_build=package.NEW[0], mc_fw_build=package.NEW[1])), 'existing calibration remains compatible')
    source = read(C / 'nucleo/Src/main.c')
    init = body(source, 'MX_TIM1_Init')
    a = source.index('  const bool sd_config_ok =')
    b = source.index('\n  reply[21] |=', a)
    predicate = source[a:b] + '\n  return sd_config_ok;'
    # Execute actual initialization and live predicate against HAL call spies,
    # using the vendored STM32 HAL/CMSIS register definitions, not copied enums.
    host = r'''
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include "stm32g4xx_hal.h"
#include "stm32g4xx_ll_tim.h"
static TIM_TypeDef timer;
static GPIO_TypeDef gpio;
#undef TIM1
#undef GPIOA
#define TIM1 (&timer)
#define GPIOA (&gpio)
#define TIM_CLOCK_DIVIDER 1
#define PWM_PERIOD_CYCLES 10624
#define REP_COUNTER 1
#define HTMIN 1
#define DEAD_TIME_COUNTS 270
static TIM_HandleTypeDef htim1;
static TIM_BreakDeadTimeConfigTypeDef saved;
static TIMEx_BreakInputConfigTypeDef input;
static void Error_Handler(void) {exit(3);}
HAL_StatusTypeDef HAL_TIM_Base_Init(TIM_HandleTypeDef *h) {timer.CR1=h->Init.ClockDivision;return HAL_OK;}
HAL_StatusTypeDef HAL_TIM_PWM_Init(TIM_HandleTypeDef *h) {(void)h;return HAL_OK;}
HAL_StatusTypeDef HAL_TIM_SlaveConfigSynchro(TIM_HandleTypeDef *h,const TIM_SlaveConfigTypeDef *c) {(void)h;(void)c;return HAL_OK;}
HAL_StatusTypeDef HAL_TIMEx_MasterConfigSynchronization(TIM_HandleTypeDef *h,const TIM_MasterConfigTypeDef *c) {(void)h;(void)c;return HAL_OK;}
HAL_StatusTypeDef HAL_TIMEx_ConfigBreakInput(TIM_HandleTypeDef *h,uint32_t brk,const TIMEx_BreakInputConfigTypeDef *c) {(void)h;(void)brk;input=*c;return HAL_OK;}
HAL_StatusTypeDef HAL_TIM_PWM_ConfigChannel(TIM_HandleTypeDef *h,const TIM_OC_InitTypeDef *c,uint32_t ch) {(void)h;(void)c;(void)ch;return HAL_OK;}
HAL_StatusTypeDef HAL_TIMEx_ConfigBreakDeadTime(TIM_HandleTypeDef *h,const TIM_BreakDeadTimeConfigTypeDef *c) {(void)h;saved=*c;return HAL_OK;}
void HAL_TIM_MspPostInit(TIM_HandleTypeDef *h) {(void)h;}
INIT_BODY
static bool config_ok(void) {PREDICATE}
#define CHECK(v) do {if(!(v)){fprintf(stderr,"FAIL line %d\n",__LINE__);return 1;}}while(0)
int main(void) {
  MX_TIM1_Init();
  CHECK(saved.BreakFilter==9);
  CHECK(saved.BreakState==TIM_BREAK_ENABLE);
  CHECK(saved.BreakPolarity==TIM_BREAKPOLARITY_HIGH);
  CHECK(saved.BreakAFMode==TIM_BREAK_AFMODE_INPUT);
  CHECK(saved.AutomaticOutput==TIM_AUTOMATICOUTPUT_DISABLE);
  CHECK(saved.Break2State==TIM_BREAK2_DISABLE);
  CHECK(htim1.Init.ClockDivision==TIM_CLOCKDIVISION_DIV2);
  CHECK(input.Source==TIM_BREAKINPUTSOURCE_BKIN && input.Enable==TIM_BREAKINPUTSOURCE_ENABLE);
  CHECK(input.Polarity==TIM_BREAKINPUTSOURCE_POLARITY_LOW);
  timer.BDTR=TIM_BDTR_BKE|TIM_BDTR_BKP|LL_TIM_BREAK_FILTER_FDIV8_N8;
  timer.AF1=TIM1_AF1_BKINE|TIM1_AF1_BKINP;
  gpio.MODER=2U<<12;gpio.OTYPER=GPIO_PIN_6;gpio.PUPDR=1U<<12;gpio.AFR[0]=6U<<24;
  CHECK(config_ok());
  const uint32_t bdtr=timer.BDTR;
  timer.BDTR=bdtr^TIM_BDTR_BKE;CHECK(!config_ok());
  timer.BDTR=bdtr^TIM_BDTR_BKP;CHECK(!config_ok());
  timer.BDTR=bdtr|TIM_BDTR_AOE;CHECK(!config_ok());
  timer.BDTR=bdtr|TIM_BDTR_BKBID;CHECK(!config_ok());
  for(unsigned f=0;f<16;++f){timer.BDTR=(bdtr&~TIM_BDTR_BKF)|(f<<TIM_BDTR_BKF_Pos);CHECK(config_ok()==(f==9));}
  timer.BDTR=bdtr;timer.CR1=TIM_CLOCKDIVISION_DIV1;CHECK(!config_ok());
  timer.CR1=TIM_CLOCKDIVISION_DIV4;CHECK(!config_ok());
  timer.CR1=TIM_CLOCKDIVISION_DIV2;CHECK(config_ok());
  puts("PASS actual TIM1 init + live register predicate");return 0;
}
'''.replace('INIT_BODY', init).replace('PREDICATE', predicate)
    flags = ['gcc', '-std=c11', '-O2', '-DSTM32G431xx', '-Wno-pointer-to-int-cast', '-Wno-int-to-pointer-cast']
    for folder in ('Inc', 'Drivers/STM32G4xx_HAL_Driver/Inc', 'Drivers/CMSIS/Include', 'Drivers/CMSIS/Device/ST/STM32G4xx/Include'):
        flags += ['-I', str(C / 'nucleo' / folder)]
    mutations = [('', host), ('old_filter', host.replace('LL_TIM_BREAK_FILTER_FDIV8_N8 >> TIM_BDTR_BKF_Pos;', '3;')),
                 ('disable_break', host.replace('sBreakDeadTimeConfig.BreakState = TIM_BREAK_ENABLE;', 'sBreakDeadTimeConfig.BreakState = TIM_BREAK_DISABLE;')),
                 ('auto_restart', host.replace('sBreakDeadTimeConfig.AutomaticOutput = TIM_AUTOMATICOUTPUT_DISABLE;', 'sBreakDeadTimeConfig.AutomaticOutput = TIM_AUTOMATICOUTPUT_ENABLE;'))]
    for name, code in mutations:
        src = out / ((name or 'config') + '.c')
        exe = src.with_suffix('.exe')
        src.write_text(code, encoding='utf-8')
        p = subprocess.run(flags + [str(src), '-o', str(exe)], capture_output=True, text=True)
        (out / ((name or 'config') + '_compile.log')).write_text(p.stdout + p.stderr, encoding='utf-8')
        check(p.returncode == 0, 'compile actual initializer ' + name)
        p = subprocess.run([str(exe)], capture_output=True, text=True)
        (out / ((name or 'config') + '_run.log')).write_text(p.stdout + p.stderr, encoding='utf-8')
        check(p.returncode != 0 if name else p.returncode == 0, 'negative control ' + name if name else 'actual initializer + register faults')
    # Nominal hardware filter model, sweeping relative clock phase. These are
    # modeled digital samples, not measurements or guaranteed end-to-end delay.
    phases = 1024
    widths_ns = [0, 20, 40, 100, 200, 400, 600, 800, 1000, 24000, 70000]
    timing = []
    for width in widths_ns:
        counts = {}
        for code, period in ((3, 1e9 / 170000000), (9, 1e9 / 10625000)):
            accepted = 0
            for phase in range(phases):
                first = (phase + .5) / phases * period
                accepted += first + 7 * period < width
            counts[str(code)] = accepted
        timing.append(dict(width_ns=width, accepted_phases=counts))
        if width <= 600:
            check(counts['9'] == 0, 'BKF9 rejects width ' + str(width))
        if width >= 800:
            check(counts['9'] == phases, 'BKF9 accepts width ' + str(width))
        if width == 400:
            check(counts['3'] == phases, 'old filter accepts observed nominal 400 ns disturbance')
    result = dict(passed=True, checks=len(checks), details=checks, mutations_detected=3,
                  phase_cases=len(widths_ns) * 2 * phases, timing=timing,
                  hardware_commands=0, hardware_validated=False,
                  limitations=['HAL calls use spies; no live electrical timing was measured.',
                               'Filter model excludes input synchronization and analog uncertainty.',
                               'No evidence here establishes the physical source of SD.'])
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('passed', 'checks', 'mutations_detected', 'phase_cases', 'hardware_commands')}))


if __name__ == '__main__':
    main()
