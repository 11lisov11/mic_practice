"""Offline fault-flight-recorder tests; no stand access or control commands."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import time

from web_hmi_command_guard_selftest import load_server_module, safe_status


def main():
    root = Path(__file__).resolve().parents[1]
    mod = load_server_module(root)
    checks = 0

    def check(ok, message):
        nonlocal checks
        checks += 1
        assert ok, message

    def parsed(lines):
        return [json.loads(line.split(" ", 1)[1]) for line in lines]

    healthy = dict(mc_diag_valid=1, mc_fault_reason=0, mc_fault=0, mc_bad_cnt=0,
                   mc_last_bad_valid=1, mc_last_bad_reason=0, mc_last_uart_error_flags=0,
                   mc_uart_error_flags=0, mc_fault_current_mask=0, mc_fault_occurred_mask=0,
                   state="VF_RUN", pwm=1, vdc=324., enc_errors=0, mc_fw_build=2026100707,
                   mc_good_cnt=100, mc_age_ms=20)
    noise = dict(healthy, state="SAFE", pwm=0, mc_fault=5, mc_bad_cnt=1,
                 mc_fault_reason=12, mc_uart_error_flags=4, mc_last_bad_reason=12,
                 mc_last_uart_error_flags=4, enc_errors=5, mc_fault_sequence=80,
                 mc_fault_motor_state=6, enc_io_error=-5)
    recorder = mod.MotorFaultRecorder()
    for i in range(21):
        check(not recorder.observe(healthy, now=i * .2), "healthy prehistory has no fault logs")
    event = parsed(recorder.observe(dict(noise, control_token="must-not-appear"), now=4.2))[0]
    check(event["phase"] == "fault" and event["history_samples"] == 21, "full before history")
    check(event["before"][-1]["pwm"] == 1 and event["at"]["pwm"] == 0, "transition captured")
    check(event["at"]["enc_errors"] == 5 and event["at"]["mc_fault_sequence"] == 80, "I2C and sequence captured")
    check("NE" in event["summary"] and not event["physical_source_identified"], "noise evidence, not guessed physical cause")
    check("must-not-appear" not in json.dumps(event), "only allowlisted measurements")
    original_id = event["event_id"]
    check(not recorder.observe(noise, now=4.3), "no duplicate fault or excessive sample")
    after = parsed(recorder.observe(dict(noise, mc_fault=1), now=4.4))
    check(len(after) == 1 and after[0]["phase"] == "after" and after[0]["event_id"] == original_id,
          "ESTOP preserves first event")
    same_newer = dict(noise, mc_bad_cnt=2, mc_last_uart_error_flags=8)
    newer = parsed(recorder.observe(same_newer, now=4.6))[0]
    check(newer["event_id"] != original_id and "ORE" in newer["summary"] and "UART=NE" in newer["detail"],
          "new bad cause and original first cause both retained")
    check(not recorder.observe(same_newer, now=11), "post history stops for unchanged event")
    recorder.observe(healthy, now=12)
    refault = parsed(recorder.observe(noise, now=12.2))[0]
    check(refault["event_id"] != original_id, "same fault after CLEAR is a new event")
    check(not recorder.observe(noise, now=20), "post history stops after bounded window")
    snapshot = recorder.snapshot()
    check(snapshot["hmi_last_fault_event_id"] == refault["event_id"], "last event exposed for log lookup")

    fast = mod.MotorFaultRecorder()
    fast.observe(dict(healthy, state="SAFE", pwm=0), now=0)
    fast.observe(healthy, now=.01)
    fast_event = parsed(fast.observe(noise, now=.02))[0]
    check(any(s["pwm"] == 1 for s in fast_event["before"]),
          "brief RUN transition is retained inside sampling interval")
    fast.observe(dict(noise, enc_errors=6), now=.03)
    check(fast._history[-1]["enc_errors"] == 6,
          "brief sensor-error transition is retained inside sampling interval")

    old = mod.MotorFaultRecorder()
    legacy = parsed(old.observe({"bp_fault": 5, "vdc": float("nan")}, now=0))[0]
    check(legacy["at"]["vdc"] is None and "UNAVAILABLE" in legacy["summary"], "unknown legacy cause and finite JSON")
    bounded = mod.MotorFaultRecorder()
    for i in range(1000):
        bounded.observe(healthy, now=i * .2)
    check(len(bounded._history) == 64, "memory bounded")
    recent = parsed(bounded.observe(noise, now=200))[0]
    check(all(0 <= 200 - s["observed_monotonic_s"] <= 5 for s in recent["before"]), "before window bounded")

    concurrent = mod.MotorFaultRecorder()
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: concurrent.observe(noise, now=1), range(64)))
    check(sum(e["phase"] == "fault" for batch in results for e in parsed(batch)) == 1,
          "parallel status requests produce one event")

    # Replay saved observations of the real failed trial, without hardware.
    trial = json.loads((root / "artifacts/current_pwm_20261007/production_trial_707_r1/report.json").read_text())
    replay = mod.MotorFaultRecorder()
    replay.observe(trial["before"], now=0)
    rows = []
    for item in trial["samples"]:
        rows.extend(parsed(replay.observe(item["status"], now=1 + item["since_start_s"])))
    replay_fault = [e for e in rows if e["phase"] == "fault"]
    check(len(replay_fault) == 1 and "UART_RX_ERROR; UART=NE" in replay_fault[0]["summary"], "real run classified")
    check(replay_fault[0]["at"]["enc_errors"] == 5, "real cross-interface failure retained")
    check(any(s["pwm"] == 1 for s in replay_fault[0]["before"]), "real run before-context retained")
    with tempfile.TemporaryDirectory() as tmp:
        logs = mod.LogStore(1_000_000, str(Path(tmp) / "logs.txt"), 1_000_000)
        for item in rows:
            logs.add("MC_FAULT_CONTEXT " + json.dumps(item, allow_nan=False))
        exported = logs.dump_since(0)
        restored = [json.loads(line.split("MC_FAULT_CONTEXT ", 1)[1]) for line in exported]
        check(restored == rows, "persistent export survives JSON roundtrip")
    class Rpc:
        def __init__(self):
            self.polls = []
        def get(self):
            self.polls.append(time.monotonic())
            return True, dict(healthy, state="SAFE", pwm=0), None
        def cmd(self, *_):
            raise AssertionError("idle recorder must not issue control commands")
    class Logs:
        def add(self, _):
            pass
    rpc = Rpc()
    app = mod.AppState(rpc, Logs(), status_log_interval=60)
    app.start_safety_watchdog()
    try:
        time.sleep(2.5)
    finally:
        app.stop_safety_watchdog()
    check(1 <= len(rpc.polls) <= 4, "idle recorder polls with no browser and no commands")
    check(all(b-a >= .9 for a, b in zip(rpc.polls, rpc.polls[1:])), "idle polling limited to one Hz")

    class StartRpc:
        def __init__(self):
            self.commands = []
            self.polls = 0
        def cmd(self, command):
            self.commands.append(command)
            return True, None
        def get(self):
            self.polls += 1
            return True, dict(safe_status(), **dict(healthy, vdc=0, bp_status=0x21, bp_fault=0,
                              bp_mcsdk_telemetry=0, bp_bad_cnt=0,
                              bp_age_ms=10, precharge=0, bp_ext=0)), None
    start_rpc = StartRpc()
    start_app = mod.AppState(start_rpc, Logs(), status_log_interval=60,
                            command_guard=mod.CommandGuardConfig(max_vdc=10, local_bench_gate=True))
    start_app._fault_recorder.observe(dict(healthy, state="SAFE", pwm=0))
    ok, message, status = start_app._start_without_precharge(
        dict(healthy, state="SAFE", pwm=0, bp_mcsdk_telemetry=0), 1, 0)
    check(ok and status["pwm"] == 1, f"mock START confirms running state: {message}")
    check(start_rpc.polls == 1 and start_rpc.commands == [
        f"SET RUNLIMIT {start_app.start_runlimit_sec:.3f}", "START"],
          "logging adds no RPC requests or control commands")
    check(start_app._fault_recorder._history[-1]["pwm"] == 1,
          "START feedback is saved without waiting for watchdog")
    print(json.dumps({"pass": True, "checks": checks, "observed_trial_replayed": True,
                      "hardware_commands": 0, "physical_noise_source_proven": False}))


if __name__ == "__main__":
    main()
