"""Exercise actual candidate HMI with recorded current/SD data, offline only."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts/live_bench_20261025/as5600_i2c_diag_r1'
sys.path.insert(0, str(ROOT / 'tools'))
from prepare_as5600_i2c_diag import FIELDS, HANDLER


def main():
    spec = importlib.util.spec_from_file_location('candidate_i2c_hmi', OUT / 'web_hmi/server.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    checks = []
    # Negative and large diagnostic values must survive the real RPC parser.
    line = 'DATA state=SAFE mode=VF pwm=0 enc_source=uno_q_i2c2 enc_io_error=-5 '
    line += ' '.join(f'enc_diag_{f}={i + 1}' for i, f in enumerate(FIELDS))
    parsed = module.RpcBridge._parse_status_string(line)
    assert parsed['enc_io_error'] == -5 and parsed['pwm'] == 0
    assert all(parsed[f'enc_diag_{f}'] == i + 1 for i, f in enumerate(FIELDS))
    legacy = module.RpcBridge._parse_status_string('DATA state=SAFE mode=VF pwm=0')
    assert all(legacy[f'enc_diag_{f}'] == 0 for f in FIELDS)
    checks += ['RPC diagnostics round-trip', 'legacy safe defaults']
    recorded = json.loads((ROOT / 'artifacts/live_bench_20261025/as5600_manual_hold_r3/latest.json').read_text())
    assert recorded['fw_build'] == 2026102509 and recorded['mc_fw_build'] == 2026102510
    sd = recorded['mc_break_wave_hex']
    old = module.with_shunt_currents(copy.deepcopy(recorded))
    new = copy.deepcopy(recorded); new['fw_build'] = 2026102513
    new = module.with_shunt_currents(new)
    for key in ('mc_current_telemetry_valid', 'mc_current_rms_a', 'mc_current_zero_ready',
                'mc_current_coverage_pct', 'mc_current_raw_adc', 'mc_current_offsets_adc'):
        assert old[key] == new[key], key
    assert new['mc_current_telemetry_valid'] == 1
    assert new['mc_break_wave_hex'] == sd
    assert module.manual_scalar_supported(new)
    wrong = copy.deepcopy(new); wrong['fw_build'] = 2026102599
    assert not module.manual_scalar_supported(wrong)
    assert module.with_shunt_currents(wrong)['mc_current_telemetry_valid'] == 0
    wrong = copy.deepcopy(new); wrong['mc_current_packet_hex'] = '00'
    assert module.with_shunt_currents(wrong)['mc_current_telemetry_valid'] == 0
    checks += ['new/old pair real current telemetry equivalence',
               'SD snapshot not changed by decode', 'manual scalar pair admitted',
               'unknown pair rejected', 'malformed current record rejected']
    # Sensor teacher behavior is preserved exactly, except additive fields and
    # a counter seed for mode handover (verified separately by compile tests).
    before = (ROOT / 'artifacts/live_bench_20261024/current_adc_apex_fix_r1/UNOQ_MOTOR/as5600_teacher.h').read_text()
    after = (OUT / 'UNOQ_MOTOR/as5600_teacher.h').read_text()
    for f in FIELDS:
        after = after.replace(f'  uint32_t diag_{f} = 0;\n', '')
    after = after.replace('  void seed_counters(uint32_t reads, uint32_t errors) {\n'
                          '    sample_.reads = reads; sample_.errors = errors;\n  }\n\n', '')
    after = after.replace('\nbool as5600_diag_select(uint8_t mode);\nbool as5600_diag_ready();\n', '')
    after = after.replace('  float rpm = 0.0f;\n\n};', '  float rpm = 0.0f;\n};')
    assert after == before
    checks.append('angle/rpm invalidity and stale policy unchanged')
    # All companion headers/protocols/display mappings remain byte-identical.
    base = ROOT / 'artifacts/live_bench_20261024/current_adc_apex_fix_r1'
    except_files = {'as5600_teacher.cpp', 'as5600_teacher.h', 'UNOQ_MOTOR.ino'}
    for p in (base / 'UNOQ_MOTOR').iterdir():
        if p.is_file() and p.name not in except_files:
            assert p.read_bytes() == (OUT / 'UNOQ_MOTOR' / p.name).read_bytes(), p.name
    checks.append('all other UNO headers/protocols unchanged')
    # Reverse only the declared additions and require the whole motor sketch
    # to match the installed source, including all thresholds and UART paths.
    original = (base / 'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text()
    candidate = (OUT / 'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text()
    candidate = candidate.replace('FW_BUILD_ID = 2026102513U;', 'FW_BUILD_ID = 2026102509U;')
    candidate = candidate.replace(HANDLER, '')
    candidate = candidate.replace('  if (!as5600_diag_ready()) return "encoder bus handover pending";\n', '')
    for indent in ('    ', '  '):
        candidate = candidate.replace('\n' + indent + '} else if (starts_ci(cmd, "ENC BUS ")) {\n'
                                      + indent + '  handled = handle_encbus_command(cmd + 8);\n', '')
    for f in FIELDS:
        candidate = candidate.replace(f'\n    s += " enc_diag_{f}="; s += String((unsigned long)g_as5600.diag_{f});', '')
    assert candidate == original
    checks.append('whole installed motor sketch unchanged outside declared sensor additions')
    # Run the real command handler, mocking only transport. Config enabled is
    # not the same as currently armed; a disarmed powered bench must pass.
    sent = []; responses = []
    arm = module.HvArmState(module.HvArmConfig(enabled=True))
    app = SimpleNamespace(hv_arm=arm, command_guard=module.CommandGuardConfig(max_vdc=20),
                          trial_command_check=lambda cmd: (True, 'ok'),
                          logs=SimpleNamespace(add=lambda _: None),
                          rpc=SimpleNamespace(cmd=lambda cmd: (sent.append(cmd) is None, None)))
    handler = SimpleNamespace(server=SimpleNamespace(app=app),
                              _send_json=lambda data, code=200: responses.append((code, data)))
    module.Handler._handle_cmd_locked(handler, 'ENC BUS SW100')
    assert sent == ['ENC BUS SW100'] and responses[-1][0] == 200
    arm._expires_at = time.time() + 30
    module.Handler._handle_cmd_locked(handler, 'ENC BUS SW25')
    assert len(sent) == 1 and responses[-1][0] == 409
    arm._expires_at = 0; arm._started = True; arm._manual_session = True
    module.Handler._handle_cmd_locked(handler, 'ENC BUS HW100')
    assert len(sent) == 1 and responses[-1][0] == 409
    arm.disarm()
    module.Handler._handle_cmd_locked(handler, 'ENC BUS HW100')
    assert sent == ['ENC BUS SW100', 'ENC BUS HW100'] and responses[-1][0] == 200
    checks += ['disarmed diagnostic switch routed to MCU',
               'armed and continuous-session switch rejected', 'switch allowed after disarm']
    report = dict(passed=True, hardware_validated=False, installed=False,
                  firmware_commands=0, motor_starts=0, checks=checks)
    (OUT / 'offline-checks.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
