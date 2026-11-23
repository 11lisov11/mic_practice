"""Test the exact detached fixture interlock, STOP code, peer decoder and HMI."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

from ipm_break_wifi_selftest import load_module
from local_stop_wait_selftest import PREAMBLE, CASES
from nucleo_button_restart_audit import function
ROOT=Path('C:\\mic_practice')
NUCLEO=Path('C:\\mic_practice\\artifacts\\live_bench_20261014\\pwm_filter_pair_r5\\production\\nucleo')
from prepare_nucleo_local_stop import PWM
from web_hmi_command_guard_selftest import safe_status


def body(text, name):
    match = re.search(r'(?:static\s+)?(?:bool|void)\s+' + name + r'\([^;]*?\)\s*\{', text)
    if not match:
        raise RuntimeError(name)
    end, depth = match.end(), 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[match.start():end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    fixture, out = args.fixture.resolve(), args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'pass':False, 'hardware_commands':0, 'cases':{}}

    def run_host(name, program):
        unit = out / (name + '.cpp')
        unit.write_text(program, encoding='utf-8')
        exe = unit.with_suffix('.exe')
        built = subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', str(unit), '-o', str(exe)],
                               capture_output=True, text=True)
        (out / (name + '_build.log')).write_text(built.stdout + built.stderr)
        if built.returncode:
            raise RuntimeError(name + ' compilation failed')
        result = subprocess.run([str(exe)], capture_output=True, text=True)
        (out / (name + '_run.log')).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(name + ' failed')
        report['cases'][name] = {'pass':True, 'stdout':result.stdout.strip()}

    source = (fixture / 'nucleo/Src/main.c').read_text(encoding='utf-8')
    original = (NUCLEO / 'Src/main.c').read_text(encoding='utf-8')
    names = ('mic_local_button_pending', 'mic_local_stop_blocked', 'UI_HandleStartStopButton_cb',
             'mic_local_stop_enable_outputs', 'mic_local_stop_clear')
    for name in names:
        assert body(source, name) == body(original, name), name
    publication = function((fixture / 'nucleo' / PWM).read_text(), 'PWM_SwitchOnPWM')
    assert (fixture / 'nucleo' / PWM).read_bytes() == (NUCLEO / PWM).read_bytes()
    core = 'volatile uint32_t mic_local_stop_latched;\n' + '\n'.join(body(source, n) for n in names)
    run_host('local_stop', PREAMBLE + core + '\n' + publication + CASES)
    # Reuse the established adversarial vectors, embedding the exact new interlock.
    suite = ast.parse((ROOT / 'tools/mcsdk_logic_bench_selftest.py').read_text())
    main_node = next(n for n in suite.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    vectors = {n.targets[0].id:ast.literal_eval(n.value) for n in main_node.body
               if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
               and isinstance(n.value, ast.Constant)
               and n.targets[0].id in ('preamble', 'cases')}
    tasks = (fixture / 'nucleo/Src/mc_tasks.c').read_text(encoding='utf-8')
    start = tasks.index('/* UNPOWERED MCSDK FIXTURE ONLY.')
    end = tasks.index('__weak void TSK_SafetyTask_PWMOFF', start)
    state = tasks[start:end]
    assert '>= 3000U' in state and '>= 15000U' not in state
    cases = vectors['cases'].replace('14999', '2999').replace('15000', '3000')
    run_host('bus_and_run_limits', vectors['preamble'] + state + cases)
    header = (fixture / 'UNOQ_MOTOR/nucleo_fault_diagnostics.h').as_posix()
    run_host('peer_decoder', '#include <cassert>\n#include "' + header + '"\n' + r'''
int main() {
 uint8_t reply[42]={}; reply[11]=0x98; reply[15]=4;
 assert(decode_nucleo_fault_diagnostics(reply,true,2026101495).valid);
 assert(decode_nucleo_fault_diagnostics(reply,true,2026101495).current_faults==4);
 assert(decode_nucleo_fault_diagnostics(reply,true,2026101408).valid);
 assert(!decode_nucleo_fault_diagnostics(reply,true,2026101297).valid);
 assert(!decode_nucleo_fault_diagnostics(reply,false,2026101495).valid);
}
''')
    module = load_module(fixture / 'web_hmi/server.py')
    s = safe_status(fw_build=2026101494, mc_fw_build=2026101495, freq_cmd=5, vdc=0,
                    bp_vdc=0, bp_vbus_raw=0, bp_status=1, bp_fault=0, mc_diag_valid=1,
                    bp_mcsdk_telemetry=1, bp_vbus_valid=1)
    cfg = module.HvArmConfig(enabled=True, profile='lv', max_vdc=2, min_vdc=0)
    assert module.hv_arm_precheck(s, cfg, False)[0]
    negative = [(dict(s, fw_build=2026101409), cfg),
                (dict(s, mc_fw_build=2026101408), cfg),
                (dict(s, vdc=2.01), cfg), (dict(s, freq_cmd=5.01), cfg),
                (dict(s, bp_status=0x81), cfg), (dict(s, bp_fault=1), cfg),
                (dict(s, bp_rsp_age_ms=module.CMD_GUARD_MAX_AGE_MS+1,
                      last_rx_age_s=module.CMD_GUARD_MAX_AGE_MS/1000+1), cfg),
                (s, module.HvArmConfig(enabled=True, profile='hv')),
                (s, module.HvArmConfig(enabled=True, profile='lv', max_vdc=10, min_vdc=0))]
    for data, config in negative:
        result = module.hv_arm_precheck(data, config, True)
        assert not result[0], result
    report['cases']['fixture_hmi_guards'] = {'pass':True, 'negative_cases':len(negative)}
    report['stop_source_matches_production'] = True
    report['pass'] = True
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
