"""No stand access: one-shot gate, bounded START and authenticated HTTP routes."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from web_hmi_command_guard_selftest import load_server_module, safe_status
from web_hmi_control_access_selftest import request
from wifi_uart_v3_trial import active_clean, expected_undervoltage, expected_trial_stop, observe_trial_stop, finalize_trial, expected_runlimit_estop


def main():
    mod = load_server_module(Path(__file__).resolve().parents[1])
    cases = 0
    now = time.time()
    proof = dict(schema="mic_ai.powered_trial.v1", pair=list(mod.UART_V3_TRIAL_PAIR),
        images=dict(mod.UART_V3_TRIAL_IMAGES), cases={k: True for k in mod.UART_V3_TRIAL_CASES},
        normal_restore_verified=True, offline_pass=True, offline_suites=40,
        idle_wifi_pass=True, physical_idle_pass=True, hv_release_approved=False,
        evidence_sha256={k: "a"*64 for k in ("pwm", "offline", "idle_wifi", "physical_idle")},
        issued_at=now-1, expires_at=now+100)
    assert mod.validate_powered_trial_qualification(proof)[0]; cases += 1
    sender_proof = copy.deepcopy(proof)
    sender_proof.update(schema="mic_ai.powered_trial.sender_delta.v1",
        pair=list(mod.UART_V3_SENDER_TRIAL_PAIR), images=dict(mod.UART_V3_SENDER_TRIAL_IMAGES),
        scope="unchanged_nucleo_pwm_plus_sender_delta", pwm_evidence_pair=list(mod.UART_V3_TRIAL_PAIR),
        pwm_evidence_images=dict(mod.UART_V3_TRIAL_IMAGES), sender_delta_verified=True,
        sender_flash_verified=True, fresh_idle_wifi_pass=True, new_pair_active_pwm_measured=False,
        offline_suites=41)
    sender_proof["evidence_sha256"].update(sender_delta="b"*64, sender_install="c"*64)
    assert mod.validate_powered_trial_qualification(sender_proof)[0]; cases += 1
    for key, value in (("scope", "whole_new_pair_measured"), ("pwm_evidence_pair", []),
                       ("pwm_evidence_images", {}), ("sender_delta_verified", False),
                       ("sender_flash_verified", False), ("fresh_idle_wifi_pass", 1),
                       ("new_pair_active_pwm_measured", True), ("offline_suites", 40),
                       ("images", mod.UART_V3_TRIAL_IMAGES), ("schema", "mic_ai.powered_trial.v1")):
        assert not mod.validate_powered_trial_qualification(dict(sender_proof, **{key: value}))[0], key
        cases += 1
    for key in ("sender_delta", "sender_install"):
        missing = copy.deepcopy(sender_proof); missing["evidence_sha256"].pop(key)
        assert not mod.validate_powered_trial_qualification(missing)[0]; cases += 1
    for key, value in (("pair", [2026101100, 2026101099]), ("images", {}), ("cases", {}),
                       ("normal_restore_verified", False), ("offline_pass", 1), ("offline_suites", 39),
                       ("offline_suites", True), ("physical_idle_pass", False), ("idle_wifi_pass", False),
                       ("issued_at", now+10), ("expires_at", now-2), ("issued_at", float("nan")),
                       ("expires_at", float("inf")), ("hv_release_approved", True), ("evidence_sha256", {})):
        assert not mod.validate_powered_trial_qualification(dict(proof, **{key: value}))[0], key
        cases += 1
    bad = copy.deepcopy(proof); bad["cases"]["STOP"] = 1
    assert not mod.validate_powered_trial_qualification(bad)[0]; cases += 1
    s = safe_status(fw_build=2026101007, mc_fw_build=2026101006, mc_diag_valid=1,
        mc_age_ms=20, bp_age_ms=20, bp_good=100, mc_bad_cnt=0, mc_bad_integrity=0,
        mc_bad_sequence=0, mc_uart_error_flags=0, mc_last_uart_error_flags=0,
        uno_tx_short_writes=0, bp_transport_fault=0, mc_last_bad_reason=0, bp_bad=0,
        bp_mcsdk_telemetry=1, bp_vbus_valid=1, bp_softstart_ready=1, mode="VF", freq_cmd=5,
        vdc=320.0, bp_vdc=320.0, bp_vbus_raw=3200, hmi_vbus_hv_calibrated=1)
    cfg = mod.HvArmConfig(enabled=True)
    assert not mod.hv_arm_precheck(s, cfg, True)[0]; cases += 1
    assert not mod.hv_arm_precheck(dict(s,fw_build=2026101008),cfg,True)[0]; cases+=1
    assert active_clean(s); cases += 1
    new_s = dict(s, fw_build=2026101008)
    assert active_clean(new_s); cases += 1
    stopped_zero = dict(new_s, freq_cmd=0)
    assert not active_clean(stopped_zero); cases += 1
    assert active_clean(stopped_zero, allow_stopped_zero=True); cases += 1
    assert not active_clean(dict(stopped_zero, pwm=1, state="VF_RUN", bp_status=99),
                            allow_stopped_zero=True); cases += 1
    assert not mod.PoweredTrialGate.live_check(stopped_zero, idle=True,
        pair=mod.UART_V3_SENDER_TRIAL_PAIR, allow_stopped_zero=True)[0]; cases += 1
    assert mod.PoweredTrialGate.live_check(stopped_zero,
        pair=mod.UART_V3_SENDER_TRIAL_PAIR, allow_stopped_zero=True)[0]; cases += 1
    assert not mod.PoweredTrialGate.live_check(dict(stopped_zero, state="VF_RUN", pwm=1, bp_status=99),
        pair=mod.UART_V3_SENDER_TRIAL_PAIR, allow_stopped_zero=True)[0]; cases += 1
    assert not mod.PoweredTrialGate.live_check(new_s, idle=True)[0]; cases += 1
    assert mod.PoweredTrialGate.live_check(new_s, idle=True, pair=mod.UART_V3_SENDER_TRIAL_PAIR)[0]; cases += 1
    assert not mod.PoweredTrialGate.live_check(s, idle=True, pair=mod.UART_V3_SENDER_TRIAL_PAIR)[0]; cases += 1
    timed_terminal = dict(new_s, freq_cmd=0, estop=1, bp_fault=1, bp_status=13,
        mc_fault_reason=4, mc_diag_valid=1, mc_fault_current_mask=0,
        mc_fault_occurred_mask=0, mc_last_bad_reason=0, hmi_powered_trial_used=1)
    assert expected_runlimit_estop(3.1, True, timed_terminal); cases += 1
    assert not active_clean(timed_terminal, allow_stopped_zero=True); cases += 1
    for elapsed, seen in ((1.,True),(4.6,True),(float("nan"),True),(3.,False)):
        assert not expected_runlimit_estop(elapsed, seen, timed_terminal); cases += 1
    for key,value in (("fw_build",2026101007),("mc_bad_cnt",1),("mc_bad_integrity",1),
        ("mc_fault_reason",12),("mc_fault_current_mask",4),("mc_fault_occurred_mask",0x400),
        ("mc_last_bad_reason",12),("mc_uart_error_flags",4),("bp_transport_fault",5),
        ("mc_age_ms",300),("bp_temp_fault",1),("pwm",1),("freq_cmd",5),
        ("precharge",1),("hmi_powered_trial_used",0),("bp_fault",True)):
        assert not expected_runlimit_estop(3.1,True,dict(timed_terminal,**{key:value})),key; cases+=1
    # Reproduce the physical run's 1.054 s HTTP setup and an automatic-stop
    # snapshot after the old 3.5 s request-based readback deadline.
    timer = [1.054]
    class TimedHmi:
        def __init__(self, stop_at=3.8, fault_at=None):
            self.stop_at, self.fault_at = stop_at, fault_at
        def status(self):
            timer[0] += .19
            state = dict(new_s, state="VF_RUN", pwm=1, bp_status=99)
            if self.fault_at is not None and timer[0] >= self.fault_at:
                state.update(mc_bad_cnt=1, bp_fault=1)
            elif timer[0] >= self.stop_at:
                state.update(state="SAFE", pwm=0, bp_status=1, freq_cmd=0)
            return state
    def pause(delay): timer[0] += delay
    trace = {"samples": []}
    assert observe_trial_stop(TimedHmi(), {"errors": []}, trace, 0, 1.054,
                              clock=lambda: timer[0], sleep=pause); cases += 1
    assert trace["observed_stop_elapsed_s"] > 3.5; cases += 1
    assert trace["observed_stop_since_ack_s"] < 4; cases += 1
    class LatchedTimedHmi(TimedHmi):
        def status(self):
            status=super().status()
            if status["pwm"] == 0: status.update(timed_terminal)
            return status
    timer[0]=1.054; trace={"samples":[]}
    assert observe_trial_stop(LatchedTimedHmi(4.0), {"errors":[]}, trace, 0, 1.054,
                              clock=lambda:timer[0], sleep=pause); cases+=1
    assert trace["stop_kind"]=="latched_estop_at_configured_runlimit" and trace["stop_cause_uniquely_verified"] is False; cases+=1
    for stop_at, fault_at, heartbeat in ((1.1,None,[]), (100,None,[]), (3.8,2.0,[]), (3.8,None,["lost"])):
        timer[0] = 1.054; trace = {"samples": []}
        try: observe_trial_stop(TimedHmi(stop_at, fault_at), {"errors": heartbeat}, trace, 0, 1.054,
                                clock=lambda: timer[0], sleep=pause)
        except RuntimeError: cases += 1
        else: raise AssertionError("bad, early or absent stop accepted")
    class FinalStopHmi:
        def __init__(self, fail_normal=False, unreachable=False):
            self.calls = []; self.fail_normal = fail_normal; self.unreachable = unreachable
            self.s = dict(new_s)
        def request(self, method, route, body):
            self.calls.append(body["emergency"])
            if self.unreachable: raise TimeoutError("unreachable")
            if self.fail_normal and not body["emergency"]:
                self.s.update(state="VF_RUN", pwm=1, bp_status=99)
                return 500, {"ok": False}
            self.s.update(state="SAFE", pwm=0, bp_status=1,
                          estop=int(body["emergency"]), bp_fault=int(body["emergency"]))
            return 200, {"ok": True}
        def status(self):
            if self.unreachable: raise TimeoutError("unreachable")
            return self.s
        def fail_safe_stop(self): return self.request("POST", "/api/stop-sequence", {"emergency": True})
    cleanup = FinalStopHmi(); rep = {"pass_": True}
    finalize_trial(cleanup, rep)
    assert rep["pass_"] and cleanup.calls == [False] and rep["final_status"]["bp_fault"] == 0; cases += 1
    cleanup = FinalStopHmi(); rep = {"pass_": False}
    finalize_trial(cleanup, rep)
    assert not rep["pass_"] and cleanup.calls == [True]; cases += 1
    cleanup = FinalStopHmi(fail_normal=True); rep = {"pass_": True}
    finalize_trial(cleanup, rep)
    assert not rep["pass_"] and cleanup.calls == [False, True] and rep["final_stop"]["outputs_off_confirmed"]; cases += 1
    cleanup = FinalStopHmi(unreachable=True); rep = {"pass_": True}
    finalize_trial(cleanup, rep)
    assert not rep["pass_"] and "emergency_fallback_error" in rep and cleanup.calls == [False, True]; cases += 1
    assert expected_trial_stop(3.0, True, s); cases += 1
    for elapsed, active, status in ((1.,True,s),(3.,False,s),(float("nan"),True,s),
                                   (3.,True,dict(s,pwm=1,bp_status=0x21))):
        assert not expected_trial_stop(elapsed,active,status); cases += 1
    for key, value in (("mc_bad_cnt", 1), ("mc_fw_build", 2026101099), ("mode", "FOC"),
                       ("freq_cmd", 11), ("freq_cmd", float("nan")), ("mc_age_ms", 300),
                       ("bp_vbus_age_ms", -1), ("bp_softstart_ready", 0), ("mc_diag_valid", 0),
                       ("vdc", float("nan")), ("bp_vdc", 322), ("bp_temp_fault", 1),
                       ("estop", 1), ("bp_fault", 5), ("precharge", 1), ("pwm", 1)):
        assert not mod.PoweredTrialGate.live_check(dict(s, **{key: value}), idle=True)[0], key
        cases += 1

    clock = [100.0]
    with patch.object(mod.time, "monotonic", lambda: clock[0]):
        bound = mod.PoweredTrialGate(pair=mod.UART_V3_SENDER_TRIAL_PAIR)
        for step in range(61):
            clock[0] = 100 + step*.5
            bound.observe(dict(new_s, bp_good=100+step*5), True)
        assert bound.ready(dict(new_s, bp_good=400), True)[0]; cases += 1
        assert not bound.ready(dict(s, bp_good=405), True)[0]; cases += 1
        clock[0] = 100.
        for invalid in (0, -1, 3601, float("inf"), float("nan"), True, "3600"):
            try: mod.PoweredTrialGate(invalid)
            except ValueError: cases += 1
            else: raise AssertionError("invalid preparation lifetime accepted")
        extended = mod.PoweredTrialGate(3600)
        for step in range(61):
            clock[0] = 700 + step*.5
            extended.observe(dict(s, bp_good=100+step*5), True)
        assert extended.ready(dict(s,bp_good=400),True)[0]; cases += 1
        assert extended.snapshot()["hmi_powered_trial_remaining_s"] > 2900; cases += 1
        clock[0] = extended.expires_at
        assert not extended.ready(dict(s,bp_good=405),True)[0]; cases += 1
        clock[0] = 100.
        gate = mod.PoweredTrialGate(); cfg.trial_gate = gate
        for step in range(61):
            clock[0] = 100+step*.5
            current = dict(s, bp_good=100+step*5)
            gate.observe(current, True)
            if step < 60:
                assert not gate.ready(current, True)[0]
                cases += 1
        assert gate.ready(current, True)[0]; cases += 1
        assert mod.hv_arm_precheck(current, cfg, True)[0]; cases += 1
        assert not mod.hv_arm_precheck(current, cfg, False)[0]; cases += 1
        assert not gate.ready(current, True)[0]; cases += 1

        def qualified_gate():
            g = mod.PoweredTrialGate()
            for step in range(61):
                clock[0] += .5
                g.observe(dict(s, bp_good=100+step*5), True)
            return g, dict(s, bp_good=400)

        g, current = qualified_gate(); assert g.ready(current, True)[0]
        clock[0] += 2.1
        assert not g.ready(current, True)[0]; cases += 1
        g, current = qualified_gate()
        assert not g.ready(dict(current, bp_good=10), True)[0]; cases += 1
        g, current = qualified_gate(); g.consume()
        assert not g.ready(current, True)[0]; cases += 1
        try: g.consume()
        except RuntimeError: cases += 1
        else: raise AssertionError("trial reused")
        cfg.trial_gate = g
        assert mod.hv_runtime_check(dict(current, state="VF_RUN", pwm=1, bp_status=0x21), cfg, vbus_calibrated=True)[0]
        cases += 1
        assert mod.hv_runtime_check(dict(current, freq_cmd=0), cfg, vbus_calibrated=True)[0]; cases += 1
        clock[0] += 3
        assert not mod.hv_runtime_check(current, cfg, vbus_calibrated=True)[0]; cases += 1
        ok, reason = mod.hv_runtime_check(dict(current, freq_cmd=0), cfg, vbus_calibrated=True)
        assert not ok and reason == "powered trial independent 3-second deadline reached"; cases += 1

    class Rpc:
        def __init__(self): self.state = dict(s, vdc=0., bp_vdc=0., bp_vbus_raw=0); self.commands=[]; self.fail_start=False
        def get(self): return True, dict(self.state), ""
        def cmd(self, command):
            self.commands.append(command)
            if command == "START":
                if self.fail_start: return False, "injected lost/rejected START reply"
                self.state.update(state="VF_RUN", state_code=1, pwm=1, bp_status=0x21)
            if command in ("STOP", "ESTOP"):
                self.state.update(state="SAFE", state_code=0, pwm=0, bp_status=1)
            return True, ""

    class Calibration:
        def is_valid(self, status=None): return True
        def snapshot(self, status=None):
            return dict(valid=True, reason="mock verified", zero_captured=True, high_captured=True,
                zero_meter_vdc=0, zero_mc_vdc=0, high_meter_vdc=320, high_mc_vdc=320)

    with tempfile.TemporaryDirectory() as folder:
        token="unit-test-control-token-not-a-real-credential"
        token_file=Path(folder)/"token"; token_file.write_text(token)
        def app():
            return mod.AppState(Rpc(), mod.LogStore(100000, None, 0), 3600,
                command_guard=mod.CommandGuardConfig(max_vdc=60, allow_hv=True, local_bench_gate=True),
                hv_arm=mod.HvArmState(mod.HvArmConfig(enabled=True)),
                control_access=mod.ControlAccessConfig(str(token_file)), vbus_calibration=Calibration())
        sender_app = app()
        sender_app.rpc.state.update(fw_build=2026101008)
        assert not sender_app.prepare_powered_trial(proof, "PREPARE UARTV3 TRIAL 3S")[0]; cases += 1
        assert sender_app.prepare_powered_trial(sender_proof, "PREPARE UARTV3 TRIAL 3S")[0]; cases += 1
        assert sender_app.hv_arm.cfg.trial_gate.pair == mod.UART_V3_SENDER_TRIAL_PAIR; cases += 1
        assert not sender_app.rpc.commands; cases += 1
        assert not app().prepare_powered_trial(sender_proof, "PREPARE UARTV3 TRIAL 3S")[0]; cases += 1
        historical=app()
        historical.rpc.state.update(bp_fault=5,mc_fault_reason=8,
            mc_fault_current_mask=4,mc_fault_occurred_mask=0x404)
        assert historical.prepare_powered_trial(proof,"PREPARE UARTV3 TRIAL 3S")[0]; cases+=1
        assert not historical.rpc.commands; cases+=1
        assert not historical.hv_arm.arm("ARM UARTV3 TRIAL 3S",historical.rpc.state)[0]; cases+=1
        assert not expected_undervoltage(historical.rpc.state); cases+=1
        unknown=app()
        unknown.rpc.state.update(bp_fault=5,mc_fault_reason=8,
            mc_fault_current_mask=0x400,mc_fault_occurred_mask=0x400)
        assert not unknown.prepare_powered_trial(proof,"PREPARE UARTV3 TRIAL 3S")[0]; cases+=1
        a=app()
        assert not a.prepare_powered_trial(proof, "wrong phrase")[0]; cases += 1
        a.rpc.state.update(vdc=320, bp_vdc=320, bp_vbus_raw=3200)
        assert not a.prepare_powered_trial(proof, "PREPARE UARTV3 TRIAL 3S")[0]; cases += 1
        a.rpc.state.update(vdc=0, bp_vdc=0, bp_vbus_raw=0)
        assert a.prepare_powered_trial(proof, "PREPARE UARTV3 TRIAL 3S")[0]
        assert not a.rpc.commands; cases += 2
        assert 0 < a.hv_arm.cfg.trial_gate.expires_at-a.hv_arm.cfg.trial_gate.created <= proof["expires_at"]-now
        cases += 1
        assert not a.prepare_powered_trial(proof, "PREPARE UARTV3 TRIAL 3S")[0]; cases += 1
        assert not a.switch_arm_profile("lv", a.rpc.state)[0]; cases += 1
        for cmd in ("SET RUNLIMIT 0", "SET RUNLIMIT 100", "SET RUNLIMIT nan", "SET RUNLIMIT inf",
                    "SET FREQ 11", "MODE FOC", "PFC ON", "BRAKE ON", "DUTY 0.5", "SET VFBOOST 100"):
            assert not a.trial_command_check(cmd)[0], cmd; cases += 1
        for cmd in ("STOP", "ESTOP", "CLEAR", "MODE VF", "SET FREQ 5", "SET FREQ 0", "SET RUNLIMIT 3"):
            assert a.trial_command_check(cmd)[0], cmd; cases += 1
        assert not a.start_sequence(runlimit_sec=4)[0] and not a.rpc.commands; cases += 1
        clock[0]=1000.
        with patch.object(mod.time, "monotonic", lambda: clock[0]):
            gate=a.hv_arm.cfg.trial_gate
            lifetime=gate.expires_at-gate.created
            gate.created=clock[0]; gate.expires_at=clock[0]+lifetime
            gate.reset_observation("test")
            for step in range(61):
                clock[0]+= .5; a.rpc.state.update(s, bp_good=100+step*5)
                a.arm_snapshot(a.rpc.state)
            a.mark_operator_heartbeat()
            assert a.hv_arm.arm("ARM UARTV3 TRIAL 3S", a.rpc.state)[0]; cases += 1
            ok, _, _=a.start_sequence(run_timeout_sec=0, poll_sec=0)
            assert ok and a.rpc.commands==["SET RUNLIMIT 3.000", "START"]; cases += 1
            assert a._powered_trial_spent and gate.consumed; cases += 1
            a.rpc.commands.clear()
            clock[0]+=3; a.mark_operator_heartbeat()
            class OneTick:
                count=0
                def wait(self, interval):
                    self.count+=1
                    return self.count>1
            a._watchdog_stop=OneTick()
            a._safety_watchdog_loop()
            assert a.rpc.commands==["STOP"], a.rpc.commands
            cases+=1
            assert not a.start_sequence()[0] and "START" not in a.rpc.commands; cases += 1
            assert a.cancel_powered_trial()[0]; cases += 1
            assert not a.prepare_powered_trial(proof, "PREPARE UARTV3 TRIAL 3S")[0]; cases += 1

            b=app(); assert b.prepare_powered_trial(proof, "PREPARE UARTV3 TRIAL 3S")[0]
            for step in range(61):
                clock[0]+=.5; b.rpc.state.update(s, bp_good=100+step*5); b.arm_snapshot(b.rpc.state)
            b.mark_operator_heartbeat(); b.rpc.fail_start=True
            assert b.hv_arm.arm("ARM UARTV3 TRIAL 3S", b.rpc.state)[0]
            assert not b.start_sequence()[0] and b._powered_trial_spent; cases += 1
            assert not b.hv_arm.arm("ARM UARTV3 TRIAL 3S", b.rpc.state)[0]; cases += 1
            idle_app=app()
            assert idle_app.prepare_powered_trial(proof,"PREPARE UARTV3 TRIAL 3S")[0]
            for step in range(31):
                clock[0]+=1
                idle_app.rpc.state.update(s,bp_good=100+step*5)
                idle_app._watchdog_stop=OneTick()
                idle_app._safety_watchdog_loop()
            idle_gate=idle_app.hv_arm.cfg.trial_gate
            assert idle_gate.ready(idle_app.rpc.state,True)[0]; cases+=1
            assert not idle_app.rpc.commands; cases+=1
            clock[0]+=1
            idle_app.rpc.state["mc_bad_cnt"]=1
            idle_app._watchdog_stop=OneTick()
            idle_app._safety_watchdog_loop()
            assert idle_gate.begin is None and not idle_app.rpc.commands; cases+=1

        # Real HTTP handler, mocked RPC: authentication and alternate command paths.
        c=app(); server=ThreadingHTTPServer(("127.0.0.1",0),mod.Handler); server.app=c
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        port=server.server_address[1]
        body=dict(action="prepare", confirm="PREPARE UARTV3 TRIAL 3S", qualification=proof)
        try:
            assert request(port,"POST","/api/powered-trial",body=body)[0]==401; cases += 1
            assert request(port,"POST","/api/powered-trial",token,body)[0]==200; cases += 1
            for cmd in ("SET RUNLIMIT 100", "SET FREQ 20", "MODE FOC", "PFC ON"):
                assert request(port,"POST","/api/cmd",token,{"cmd":cmd})[0]==409; cases += 1
            assert request(port,"POST","/api/start-sequence",token,{"runlimit_s":4})[0]==409; cases += 1
            assert "START" not in c.rpc.commands; cases += 1
            assert request(port,"POST","/api/stop-sequence",body={})[0]==200; cases += 1
            assert request(port,"POST","/api/powered-trial",token,{"action":"cancel"})[0]==200; cases += 1
            assert not mod.hv_arm_precheck(s,c.hv_arm.cfg,True)[0]; cases += 1
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)
    assert expected_undervoltage(dict(s, bp_fault=5, mc_fault_reason=8,
        mc_fault_current_mask=4, mc_fault_occurred_mask=4)); cases += 1
    assert not expected_undervoltage(dict(s, bp_fault=5, mc_fault_reason=8,
        mc_fault_current_mask=0x400, mc_fault_occurred_mask=0x400)); cases += 1
    print(json.dumps(dict(pass_=True, cases=cases, hardware_commands=0, mock_http_only=True)))


if __name__=="__main__": main()
