"""Replay the saved timed run and exercise the real HMI watchdog on the PC."""
import importlib.util
import json
import sys
from hashlib import sha256
from types import SimpleNamespace

from prepare_air56_hmi_bounded_stop import BASE, OUT, ROOT

RECORD = ROOT / 'artifacts/live_bench_20261123/lso_2306_5hz_125222_266755/trial.jsonl'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def replay_statuses():
    events = [json.loads(line) for line in RECORD.read_text(encoding='utf8').splitlines()]
    prepared = next(item['data'] for item in events if item['kind'] == 'status'
                    and item['data']['hmi_hv_armed'] == 1 and item['data']['run_id'] == 0)
    running = next(item['data']['status'] for item in events if item['kind'] == '/api/start-sequence')
    stopped = next(item['data'] for item in events if item['kind'] == 'status'
                   and item['data']['pwm'] == 0 and item['data']['run_reason'] == 1)
    return prepared, running, stopped


def run_watchdog(module, prepared, running, feedback, heartbeats):
    commands = []
    messages = []
    frames = iter([running, *feedback])
    heartbeats = iter(heartbeats)
    armed = module.HvArmState(module.HvArmConfig(enabled=True), lambda status: True)
    assert armed.arm(armed.cfg.confirm, prepared)[0]

    def cmd(command):
        commands.append(command)
        return True, ''

    def get():
        frame = next(frames, None)
        return (True, dict(frame), '') if frame else (False, None, 'status lost')

    def heartbeat_fresh():
        return next(heartbeats)

    def unexpected_stop(**kwargs):
        raise AssertionError(kwargs)

    app = SimpleNamespace(hv_arm=armed, rpc=SimpleNamespace(cmd=cmd, get=get),
                         logs=SimpleNamespace(add=messages.append), _manual_start_requested=False,
                         command_guard=module.CommandGuardConfig(max_vdc=armed.cfg.max_vdc),
                         vbus_calibration=SimpleNamespace(is_valid=lambda status: True),
                         maybe_log_fault_diagnostics=lambda status: None,
                         stop_sequence=unexpected_stop)
    ok, _, _ = module.AppState._start_without_precharge(app, prepared, 0.5, 0, 5.0)
    assert ok and armed.snapshot()['hmi_hv_started'] == 1
    del commands[:]
    app._watchdog_stop = SimpleNamespace(wait=lambda _: next(ticks))
    app._runtime_bad_monitor = module.HvRuntimeBadFrameMonitor()
    app._last_diag_idle_poll = float('inf')
    app.control_access = SimpleNamespace(enabled=True)
    app.operator_heartbeat_fresh = heartbeat_fresh
    app.operator_heartbeat_age = lambda: 3.6
    app._precharge_off = lambda: (True, '')
    ticks = iter((False, False, True))
    module.AppState._safety_watchdog_loop(app)
    return commands, messages, armed.snapshot()


def main():
    old = load('air56_original_bounded_stop', BASE / 'web_hmi/server.py')
    new = load('air56_fixed_bounded_stop', OUT / 'server.py')
    before, running, complete = replay_statuses()
    commands, messages, _ = run_watchdog(old, before, running, [complete], [True, False])
    assert commands == ['STOP', 'ESTOP'] and any('OPERATOR_HEARTBEAT_LOST' in line for line in messages)
    commands, messages, state = run_watchdog(new, before, running, [complete], [True, False])
    assert not commands and state['hmi_hv_armed'] == state['hmi_hv_started'] == 0
    assert any('WIFI_BOUNDED_COMPLETE' in line for line in messages)

    rejected = {
        'previous_run': dict(complete, run_id=before['run_id']),
        'other_start': dict(complete, run_start_ms=complete['run_start_ms'] + 1),
        'other_firmware': dict(complete, fw_build=2026112303, mc_fw_build=2026112304),
        'short_stop': dict(complete, run_reason=2),
        'pending_pwm': dict(complete, bp_status=complete['bp_status'] | 0x20),
        'stale_motor_status': dict(complete, mc_age_ms=300),
        'sd_low': dict(complete, mc_sd_live=dict(complete['mc_sd_live'], level='LOW')),
        'break_disabled': dict(complete, mc_sd_live=dict(complete['mc_sd_live'], break_irq_enabled=False)),
        'fault_mask': dict(complete, mc_fault_current_mask=64),
        'uart_lost': None,
    }
    for name, feedback in rejected.items():
        commands, messages, _ = run_watchdog(new, before, running, [feedback], [True, False])
        assert commands == ['STOP', 'ESTOP'], (name, messages)
        assert not any('WIFI_BOUNDED_COMPLETE' in line for line in messages), name
    commands, _, _ = run_watchdog(new, before, running, [running], [True, False])
    assert commands == ['STOP', 'ESTOP']
    report = dict(passed=True, deployed=False, hardware_commands=0, recorded_run_replayed=True,
                  heartbeat_loss_during_run_preserved=True, unsafe_completions_rejected=list(rejected),
                  record_sha256=sha256(RECORD.read_bytes()).hexdigest(),
                  server_sha256=sha256((OUT / 'server.py').read_bytes()).hexdigest())
    (OUT / 'verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
