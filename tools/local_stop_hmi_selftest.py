"""Exercise LOCAL STOP through the real GET status route with a non-actuating RPC."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import threading
from urllib.request import ProxyHandler, build_opener

from ipm_break_wifi_selftest import load_module
from prepare_local_stop_hmi_fix import BASE, ROOT


FIRST_FIELDS = ("mc_fault_reason", "mc_uart_error_flags", "mc_fault_current_mask",
                "mc_fault_occurred_mask", "mc_fault_motor_state", "mc_fault_sequence",
                "mc_fault_tx_status")


def status():
    return dict(fw_build=2026101205, mc_fw_build=2026101204, state="SAFE", state_code=0,
                mode="VF", pwm=0, estop=0, freq=0.0, speed=0.0, vdc=0.0,
                bp_status=9, bp_fault=5, bp_age_ms=20, bp_good=100, bp_bad_cnt=0,
                mc_diag_valid=1, mc_fault_reason=8, mc_uart_error_flags=0,
                mc_fault_current_mask=4, mc_fault_occurred_mask=4,
                mc_fault_motor_state=10, mc_fault_sequence=227, mc_fault_tx_status=0,
                mc_last_bad_valid=1, mc_last_bad_reason=0,
                mc_last_uart_error_flags=0, mc_last_tx_status=0)


class Rpc:
    def __init__(self, module):
        self.module = module
        self.data = status()
        self.reads = 0
        self.commands = []

    def get(self):
        self.reads += 1
        return True, self.module.with_motor_controller_aliases(copy.deepcopy(self.data)), ""

    def cmd(self, command):
        self.commands.append(command)
        raise AssertionError("Observational test issued a hardware command")


class Logs:
    def __init__(self):
        self.lines = []

    def add(self, line):
        self.lines.append(line)


def run_api(module, samples):
    rpc, logs = Rpc(module), Logs()
    app = module.AppState(rpc, logs, status_log_interval=0)
    server = module.ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    server.app = app
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    results = []
    opener = build_opener(ProxyHandler({}))
    try:
        for sample in samples:
            rpc.data = sample
            with opener.open(f"http://127.0.0.1:{server.server_port}/api/status", timeout=5) as response:
                payload = json.load(response)
            assert payload["ok"] is True
            results.append((payload["data"], list(logs.lines)))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert not rpc.commands
    assert app._operator_heartbeat_ts == 0
    assert rpc.reads == len(samples)
    return results


def events(lines):
    return [json.loads(line.split(" ", 1)[1]) for line in lines
            if line.startswith("MC_FAULT_CONTEXT ")
            and json.loads(line.split(" ", 1)[1])["phase"] == "fault"]


def verify(module, check):
    before = status()
    stopped = dict(before, bp_status=141, bp_fault=1)
    first = {key: before[key] for key in FIRST_FIELDS}
    rows = run_api(module, [before, stopped, stopped])
    baseline, baseline_logs = rows[0]
    current, current_logs = rows[1]
    repeat, repeat_logs = rows[2]
    check(baseline["hmi_local_stop_latched"] == 0, "unlatched API state")
    check(current["hmi_local_stop_latched"] == 1, "0x8D real API latch")
    check(current["bp_status"] == current["mc_status"] == 141, "raw status preserved")
    check(current["bp_fault"] == current["mc_fault"] == 1, "current ESTOP preserved")
    check({key: current[key] for key in FIRST_FIELDS} == first, "first fault fields preserved")
    check(current["mc_fault_detail"].startswith("current=LOCAL_STOP_PC13; first=MCSDK_FAULT"),
          "detail separates current STOP and first fault")
    check("MC_UNDER_VOLT" in current["mc_fault_detail"], "first mask text preserved")
    check("LOCAL_STOP_PC13" in current["hmi_last_fault_summary"], "flight recorder summary")
    old_event, new_event = events(baseline_logs)[-1], events(current_logs)[-1]
    check(new_event["event_id"] != old_event["event_id"], "STOP transition observed with unchanged first fault")
    check(new_event["before"][-1]["hmi_local_stop_latched"] == 0, "pre-STOP context")
    check(new_event["at"]["hmi_local_stop_latched"] == 1, "at-STOP context")
    check({key: new_event["at"][key] for key in FIRST_FIELDS} == first, "recorder preserves first fault")
    check(new_event["physical_source_identified"] is False, "no fabricated driver source")
    check(new_event["controller_masks_are_first_fault_snapshot"] is True, "snapshot provenance retained")
    check(new_event["time_basis"] == "Linux observation, not exact MCU interrupt timestamp", "timing limitation retained")
    check(any(line.startswith("MC_FAULT_DIAG code=1 ") and "LOCAL_STOP_PC13" in line
              for line in current_logs), "diagnostic transition logged")
    check(any(line.startswith("STAT ") and "hmi_local_stop_latched=1" in line
              for line in current_logs), "periodic status consistent")
    check(len(events(repeat_logs)) == len(events(current_logs)), "same STOP deduplicated")
    check(repeat["mc_fault_detail"].count("LOCAL_STOP_PC13") == 1, "no duplicate detail prefix")
    check(stopped == dict(before, bp_status=141, bp_fault=1), "RPC source unmodified")
    check(module.AppState(Rpc(module), Logs(), 1).arm_snapshot(None)["hmi_local_stop_latched"] == 0,
          "missing telemetry does not invent latch")
    variants = [dict(stopped, mc_diag_valid=0),
                {**stopped, "mc_status":141, "bp_status":9},
                {**stopped, "mc_status":9, "bp_status":141},
                {key:value for key,value in {**stopped,"mc_status":141,"mc_fault":1}.items()
                 if key not in ("bp_status", "bp_fault")},
                dict(before, hmi_local_stop_latched=1)]
    for index, (data, _) in enumerate(run_api(module, variants)):
        expected = (1, 1, 0, 1, 0)[index]
        check(data["hmi_local_stop_latched"] == expected, f"telemetry variant {index}")
        check(("LOCAL_STOP_PC13" in data["mc_fault_detail"]) == bool(expected), f"variant detail {index}")
    data = {**before, "bp_status":141, "bp_fault":5}
    recorder = module.MotorFaultRecorder()
    recorder.observe(before, now=0)
    event = events(recorder.observe(data, now=.01))[-1]
    check(event["at"]["hmi_local_stop_latched"] == 1, "latch-only change logged even if current fault unchanged")
    recorder = module.MotorFaultRecorder()
    recorder.observe(before, now=0)
    changed = events(recorder.observe(dict(before, bp_fault=1), now=.01))
    check(bool(changed), "current fault change logged independently of latch")


def verify_ui(path, check):
    program = r'''
const fs = require('fs');
const vm = require('vm');
const text = fs.readFileSync(process.argv[1], 'utf8');
const context = {};
vm.createContext(context);
for (const name of ['mcField', 'mcFaultName', 'mcLocalStopLatched', 'mcFaultSummary']) {
  const start = text.indexOf('function ' + name + '(');
  const end = text.indexOf('\nfunction ', start + 1);
  vm.runInContext(text.slice(start, end), context);
}
const cases = [
  [{bp_status:141, mc_diag_valid:1, mc_fault_reason:8}, 1, true],
  [{mc_status:141, bp_status:9}, 5, true],
  [{bp_status:141}, 0, true],
  [{bp_status:9}, 1, false],
  [{mc_status:9, bp_status:141}, 1, false],
  [{bp_status:141, mc_diag_valid:0}, 5, true]
];
for (const [data, code, expected] of cases) {
  if (context.mcFaultSummary(data, code).includes('PC13') !== expected) throw Error('UI STOP mismatch');
}
process.stdout.write(JSON.stringify({pass:true, cases:cases.length}));
'''
    result = subprocess.run(["node", "-e", program, str(path)], capture_output=True, text=True,
                            encoding="utf-8", timeout=15)
    check(result.returncode == 0, "UI functions executed: " + result.stderr)
    check(json.loads(result.stdout)["cases"] == 6, "six UI status cases")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    checks = []

    def check(ok, label):
        checks.append(label)
        assert ok, label

    broken = run_api(load_module(BASE), [dict(status(), bp_status=141, bp_fault=1)])[0][0]
    check(broken["hmi_local_stop_latched"] == 0 and "LOCAL_STOP_PC13" not in broken["mc_fault_detail"],
          "installed baseline bug reproduced as negative control")
    candidate = args.candidate.resolve() / "web_hmi/server.py"
    verify(load_module(candidate), check)
    verify(load_module(ROOT / "web_hmi/server.py"), check)
    verify_ui(args.candidate.resolve() / "web_hmi/static/app.js", check)
    from prepare_trial_wait_fix import BASE as recipe_base, server
    check(server(recipe_base.read_text(encoding="utf-8")) == candidate.read_text(encoding="utf-8"),
          "main generator reproduces fixed installed candidate")
    report = dict(schema="mic_ai.local_stop_hmi_selftest.v1", **{"pass":True},
                  checks=len(checks), cases=checks, negative_control_reproduced=True,
                  hardware_commands=0, first_fault_snapshot_preserved=True,
                  active_pwm_stop_timing_measured=False)
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key:value for key,value in report.items() if key != "cases"}, indent=2))


if __name__ == "__main__":
    main()
