"""Offline checks of actual candidate code and recorded telemetry; no hardware."""
import copy
import difflib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import prepare_as5600_software_regression as package
BASE, OUT = package.BASE, package.OUT


def main():
    checks = []
    before = (BASE / 'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text()
    after = (OUT / 'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text()
    after = after.replace('FW_BUILD_ID = 2026102515U;', 'FW_BUILD_ID = 2026102513U;')
    after = after.replace('\n  else if (icmp(arg, "LEGACY")) mode = 3;', '')
    for f in package.FIELDS:
        after = after.replace(f'\n    s += " enc_diag_{f}="; s += String((unsigned long)g_as5600.diag_{f});', '')
    assert before == after
    checks.append('whole installed motor sketch unchanged outside identity/sensor selector/diagnostics')
    before = (BASE / 'UNOQ_MOTOR/as5600_teacher.h').read_text()
    after = (OUT / 'UNOQ_MOTOR/as5600_teacher.h').read_text()
    for f in package.FIELDS:
        after = after.replace(f'  uint32_t diag_{f} = 0;\n', '')
    assert before == after
    checks.append('angle validity, speed estimator and freshness rules unchanged')
    for p in (BASE / 'UNOQ_MOTOR').iterdir():
        if p.is_file() and p.name not in {'UNOQ_MOTOR.ino', 'as5600_teacher.h',
                                        'as5600_teacher.cpp', 'as5600_i2c_reader.h'}:
            assert p.read_bytes() == (OUT / 'UNOQ_MOTOR' / p.name).read_bytes(), p.name
    checks.append('all other control/protocol/ADC/SD headers unchanged')
    spec = importlib.util.spec_from_file_location('regression_hmi', OUT / 'web_hmi/server.py')
    mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
    line = 'DATA state=SAFE mode=VF pwm=0 enc_diag_mode=3 '
    line += ' '.join(f'enc_diag_{f}={i+1}' for i,f in enumerate(package.FIELDS))
    s = mod.RpcBridge._parse_status_string(line)
    assert s['enc_diag_mode'] == 3 and s['pwm'] == 0
    assert all(s[f'enc_diag_{f}'] == i+1 for i,f in enumerate(package.FIELDS))
    old = mod.RpcBridge._parse_status_string('DATA state=SAFE mode=VF pwm=0')
    assert all(old[f'enc_diag_{f}'] == 0 for f in package.FIELDS)
    checks += ['new diagnostic fields parsed as integers', 'legacy defaults']
    recorded = json.loads((BASE/'sw100_powered_5hz_r1/report.json').read_text())
    real = [x['status'] for x in recorded['samples']
            if x['status']['pwm'] == 1 and x['status']['mc_current_telemetry_valid'] == 1][-1]
    orig = mod.with_shunt_currents(copy.deepcopy(real))
    new = dict(real, fw_build=2026102515); new = mod.with_shunt_currents(new)
    assert new['mc_current_telemetry_valid'] == 1 and mod.manual_scalar_supported(new)
    for k in ('mc_current_zero_ready', 'mc_current_offsets_adc', 'mc_current_rms_a',
              'mc_current_coverage_pct', 'mc_break_wave_hex'):
        assert new[k] == orig[k], k
    wrong = dict(new, fw_build=2026102599)
    assert not mod.manual_scalar_supported(wrong)
    assert mod.with_shunt_currents(wrong)['mc_current_telemetry_valid'] == 0
    checks += ['recorded current/zero/SD telemetry equivalent for new pair', 'unknown pair rejected']
    historical = (ROOT/'UNOQ_MOTOR/as5600_teacher.cpp').read_text()
    previous = (ROOT/'artifacts/live_bench_20261024/current_adc_apex_fix_r1/UNOQ_MOTOR/as5600_teacher.cpp').read_text()
    expected = historical.replace('// Lowest preemptible priority; I2C waits leave UART/RPC runnable.',
        '// I2C blocks outside control ownership; sampling is not starved by bulk RPC TX.').replace(
        'CONFIG_NUM_PREEMPT_PRIORITIES - 1, 0, K_NO_WAIT', '4, 0, K_NO_WAIT')
    assert expected == previous
    comparison = dict(original_priority='CONFIG_NUM_PREEMPT_PRIORITIES-1 =14 on this kernel',
        installed_priority=4, native_driver_diff_only_priority_and_comment=True,
        diff=list(difflib.unified_diff(historical.splitlines(), previous.splitlines())),
        historical_success_report='artifacts/unoq_as5600_20261007/check_r1/report.json',
        historical_report_pwm=False, priority_causes_nack_proven=False)
    (OUT/'historical_comparison.json').write_text(json.dumps(comparison, indent=2)+'\n')
    checks.append('historical priority difference isolated; no register/address/clock change in that diff')
    worker = (OUT/'UNOQ_MOTOR/as5600_teacher.cpp').read_text()
    # Compile the actual packer against synthetic register banks. This tests
    # pin scoping without using the MCU or mocking a value returned by it.
    start = worker.index('uint32_t pin_config() {'); end = worker.index('\n}\n',start)+3
    func = worker[start:end]
    test = '''#include <stdint.h>
#include <cassert>
struct Gpio {uint32_t MODER, OTYPER, PUPDR, OSPEEDR, AFR[2];} bank{};
#define GPIOB (&bank)
''' + func + '''
int main(){
 bank.MODER=10U<<20; bank.OTYPER=3U<<10; bank.PUPDR=5U<<20;
 bank.OSPEEDR=15U<<20; bank.AFR[1]=0x44U<<8;
 auto x=pin_config();
 assert((x&15)==10 && ((x>>4)&3)==3 && ((x>>6)&15)==5);
 assert(((x>>10)&15)==15 && ((x>>14)&255)==0x44);
 bank.MODER^=~(15U<<20);bank.OTYPER^=~(3U<<10);
 bank.PUPDR^=~(15U<<20);bank.OSPEEDR^=~(15U<<20);bank.AFR[1]^=~(255U<<8);
 assert(pin_config()==x);
 bank.MODER^=1U<<20;assert(pin_config()!=x);
}
'''
    (OUT/'build/uno/pin_config_selftest.cpp').write_text(test)
    r = dict(passed=True, hardware_validated=False, installed=False, hardware_commands=0, checks=checks)
    (OUT/'offline-checks.json').write_text(json.dumps(r, indent=2)+'\n')
    print(json.dumps(r))


if __name__ == '__main__':
    main()
