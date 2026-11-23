"""One-shot 30 s / 50 Hz coast permission, entirely mocked and offline."""
import copy
import json
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

from web_hmi_command_guard_selftest import load_server_module, safe_status
from wifi_vf_coast30 import profile_identity,monitor_coast


def main():
    root=Path(__file__).resolve().parents[1]; mod=load_server_module(root)
    now=time.time(); cases=0
    proof=dict(schema="mic_ai.powered_trial.coast30.v1",pair=list(mod.UART_V3_SENDER_TRIAL_PAIR),
        images=dict(mod.UART_V3_SENDER_TRIAL_IMAGES),scope="unchanged_nucleo_pwm_plus_sender_delta",
        pwm_evidence_pair=list(mod.UART_V3_TRIAL_PAIR),pwm_evidence_images=dict(mod.UART_V3_TRIAL_IMAGES),
        sender_delta_verified=True,sender_flash_verified=True,fresh_idle_wifi_pass=True,
        new_pair_active_pwm_measured=False,cases={k:True for k in mod.UART_V3_TRIAL_CASES},
        normal_restore_verified=True,offline_pass=True,offline_suites=44,idle_wifi_pass=True,
        physical_idle_pass=True,hv_release_approved=False,issued_at=now-1,expires_at=now+3599,
        evidence_sha256={k:"a"*64 for k in ("pwm","offline","idle_wifi","physical_idle",
            "sender_delta","sender_install","coast_profile","powered_review")},
        profile=mod.COAST30_PROFILE,coast_only=True,native_coast_profile_pass=True,
        prior_rotation_operator_confirmed=True,prior_active_health_clean=True,
        prior_stop_cause_uniquely_verified=False,current_telemetry_qualified=False,dc_capacitance_uf=370)
    assert mod.validate_powered_trial_qualification(proof)[0];cases+=1
    for key,value in (("profile","ramp"),("coast_only",False),("dc_capacitance_uf",0),
        ("dc_capacitance_uf",True),("dc_capacitance_uf",float("nan")),("offline_suites",43),
        ("native_coast_profile_pass",False),("prior_rotation_operator_confirmed",False),
        ("prior_active_health_clean",False),("current_telemetry_qualified",True),
        ("prior_stop_cause_uniquely_verified",True),("schema","mic_ai.powered_trial.sender_delta.v1")):
        assert not mod.validate_powered_trial_qualification(dict(proof,**{key:value}))[0],key;cases+=1
    for key in ("coast_profile","powered_review"):
        bad=copy.deepcopy(proof);bad["evidence_sha256"].pop(key)
        assert not mod.validate_powered_trial_qualification(bad)[0];cases+=1
    s=safe_status(fw_build=2026101008,mc_fw_build=2026101006,mc_diag_valid=1,mc_age_ms=20,bp_age_ms=20,
        bp_good=100,mc_bad_cnt=0,mc_bad_integrity=0,mc_bad_sequence=0,mc_uart_error_flags=0,
        mc_last_uart_error_flags=0,uno_tx_short_writes=0,bp_transport_fault=0,mc_last_bad_reason=0,
        bp_bad=0,bp_bad_cnt=0,bp_mcsdk_telemetry=1,bp_vbus_valid=1,bp_softstart_ready=1,
        mode="VF",freq_cmd=50,vdc=325.,bp_vdc=325.,bp_vbus_raw=3250,hmi_vbus_hv_calibrated=1)
    assert not mod.PoweredTrialGate.live_check(s)[0];cases+=1
    def live(data):
        return mod.PoweredTrialGate.live_check(data,idle=True,pair=mod.UART_V3_SENDER_TRIAL_PAIR,
                                               profile=mod.COAST30_PROFILE)[0]
    assert live(s);cases+=1
    live_s=dict(s,hmi_powered_trial_profile=mod.COAST30_PROFILE,hmi_powered_trial_enabled=1,
        hmi_powered_trial_max_run_s=33,hmi_powered_trial_stop_after_s=30,hmi_powered_trial_max_freq_hz=50)
    assert profile_identity(live_s);cases+=1
    timer=[1.0]
    class TimedHmi:
        def __init__(self,stop=30.1,fault=None):self.stop=stop;self.fault=fault
        def status(self):
            timer[0]+=.1
            status=dict(live_s,state="VF_RUN",pwm=1,bp_status=99)
            if self.fault is not None and timer[0]>=self.fault:status.update(mc_bad_cnt=1)
            elif timer[0]>=self.stop:status.update(state="SAFE",pwm=0,bp_status=1,freq_cmd=0)
            return status
    trace={"samples":[]}
    assert monitor_coast(TimedHmi(),{"errors":[]},trace,mod,0,1,
                         clock=lambda:timer[0],sleep=lambda delay:timer.__setitem__(0,timer[0]+delay));cases+=1
    assert trace["stop_kind"]=="PWM_off_coast" and trace["observed_stop_since_ack_s"]>=28.5;cases+=1
    for stop,fault,errors in ((3,None,[]),(100,None,[]),(30,5,[]),(30,None,["lost"])):
        timer[0]=1;trace={"samples":[]}
        try:monitor_coast(TimedHmi(stop,fault),{"errors":errors},trace,mod,0,1,
            clock=lambda:timer[0],sleep=lambda delay:timer.__setitem__(0,timer[0]+delay))
        except RuntimeError:cases+=1
        else:raise AssertionError("unhealthy or missing coast stop accepted")
    for key,value in (("freq_cmd",20),("freq_cmd",.1),("freq_cmd",51),("mc_bad_cnt",1),
        ("vdc",361),("bp_fault",1),("mc_age_ms",300),("estop",1),("precharge",1)):
        assert not live(dict(s,**{key:value}));cases+=1
    try:mod.PoweredTrialGate(profile=mod.COAST30_PROFILE)
    except ValueError:cases+=1
    else:raise AssertionError("old Uno cannot get coast permission")

    class Rpc:
        def __init__(self):self.state=dict(s,vdc=0.,bp_vdc=0.,bp_vbus_raw=0);self.commands=[]
        def get(self):return True,dict(self.state),""
        def cmd(self,command):
            self.commands.append(command)
            if command=="START":self.state.update(state="VF_RUN",state_code=1,pwm=1,bp_status=99)
            if command in ("STOP","ESTOP"):
                self.state.update(state="SAFE",state_code=0,pwm=0,bp_status=1,freq_cmd=0,
                                  estop=int(command=="ESTOP"),bp_fault=int(command=="ESTOP"))
            return True,""
    class Calibration:
        def is_valid(self,status=None):return True
        def snapshot(self,status=None):return dict(valid=True,reason="mock",zero_captured=True,
            high_captured=True,zero_meter_vdc=0,zero_mc_vdc=0,high_meter_vdc=325,high_mc_vdc=325)
    clock=[100.]
    with tempfile.TemporaryDirectory() as folder:
        token=Path(folder)/"token";token.write_text("mock-only-control-token")
        def app():return mod.AppState(Rpc(),mod.LogStore(100000,None,0),3600,
            command_guard=mod.CommandGuardConfig(max_vdc=60,allow_hv=True,local_bench_gate=True),
            hv_arm=mod.HvArmState(mod.HvArmConfig(enabled=True)),
            control_access=mod.ControlAccessConfig(str(token)),vbus_calibration=Calibration())
        a=app()
        assert not a.prepare_powered_trial(proof,"PREPARE UARTV3 TRIAL 3S")[0];cases+=1
        assert a.prepare_powered_trial(proof,"PREPARE UARTV3 COAST30 50HZ")[0];cases+=1
        assert a.hv_arm.cfg.ttl_sec==45 and a.start_runlimit_sec==33;cases+=1
        assert not a.rpc.commands;cases+=1
        for cmd in ("SET FREQ 20","SET FREQ .1","SET FREQ 51","SET RUNLIMIT 30","SET RUNLIMIT 34","PFC ON"):
            assert not a.trial_command_check(cmd)[0];cases+=1
        for cmd in ("SET FREQ 50","SET FREQ 0","SET RUNLIMIT 33","STOP","ESTOP"):
            assert a.trial_command_check(cmd)[0];cases+=1
        assert not a.start_sequence(runlimit_sec=30)[0] and not a.rpc.commands;cases+=1
        assert not a.start_sequence()[0] and not a.rpc.commands;cases+=1
        with patch.object(mod.time,"monotonic",lambda:clock[0]):
            gate=a.hv_arm.cfg.trial_gate;gate.created=100;gate.expires_at=3700
            for step in range(61):
                clock[0]=100+step*.5;a.rpc.state.update(s,bp_good=100+step*5)
                a.arm_snapshot(a.rpc.state)
            a.mark_operator_heartbeat()
            assert a.hv_arm.arm("ARM UARTV3 COAST30 50HZ",a.rpc.state)[0];cases+=1
            assert a.start_sequence(runlimit_sec=33,run_timeout_sec=0,poll_sec=0)[0];cases+=1
            assert a.rpc.commands==["SET RUNLIMIT 33.000","START"];cases+=1
            assert not a.trial_command_check("SET RUNLIMIT 33")[0];cases+=1
            clock[0]+=29.9;a.mark_operator_heartbeat()
            assert mod.hv_runtime_check(a.rpc.state,a.hv_arm.cfg,vbus_calibrated=True)[0];cases+=1
            clock[0]+=.1;a.mark_operator_heartbeat()
            class OneTick:
                count=0
                def wait(self,interval):self.count+=1;return self.count>1
            a._watchdog_stop=OneTick();a._safety_watchdog_loop()
            assert a.rpc.commands==["SET RUNLIMIT 33.000","START","STOP"],a.rpc.commands;cases+=1
            assert a.rpc.state["estop"]==0 and a.rpc.state["freq_cmd"]==0;cases+=1
            assert not a.start_sequence()[0];cases+=1
            assert a.cancel_powered_trial()[0] and a.start_runlimit_sec==15;cases+=1
            assert not a.prepare_powered_trial(proof,"PREPARE UARTV3 COAST30 50HZ")[0];cases+=1
    print(json.dumps(dict(pass_=True,cases=cases,hardware_commands=0)))


if __name__=="__main__":main()
