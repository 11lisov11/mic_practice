"""Load supervisor. Never starts, arms, clears, resets or flashes the AIR drive."""
from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import uuid

from .control import (Interlock, Limits, LoadControl, bench_problem, number,
                      parameter_mismatches, readiness, requested_load)
from .protocol import Rtu, open_identified_serial, parameter_snapshot, telemetry
from .watchdog import Watchdog


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


class BenchHttp:
    def __init__(self, url, timeout=.18):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def status(self):
        request = urllib.request.Request(self.url+"/api/status", headers={"Cache-Control": "no-cache"})
        with self.opener.open(request, timeout=self.timeout) as response:
            value = json.load(response)
        if value.get("ok") is not True or not isinstance(value.get("data"), dict):
            raise Interlock("invalid_bench_envelope")
        return value["data"]

    def stop(self):
        request = urllib.request.Request(self.url+"/api/stop-sequence",
            data=b'{"emergency":true}', headers={"Content-Type": "application/json"}, method="POST")
        with self.opener.open(request, timeout=.4) as response:
            result = json.load(response)
        if result.get("ok") is not True:
            raise Interlock("AIR_stop_not_acknowledged")
        return result


def source_hashes():
    folder = Path(__file__).parent
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob("*.py")}


def check_running_sample(s, servo, config, run_key=None):
    why = bench_problem(s, config["expected_firmware_pair"], run_key)
    if why:
        raise Interlock(why)
    if s.get("algorithm_selected") != config["expected_algorithm"]:
        raise Interlock("algorithm_changed")
    if s.get("algorithm_fault") != 0:
        raise Interlock("native_algorithm_fault_or_missing")
    if config.get("require_observer_valid", True) and s.get("rpm_est_valid") != 1:
        raise Interlock("native_observer_invalid")
    if servo["alarm"] != 0:
        raise Interlock("T3D_alarm")
    bit = config["qualification"]["di_conducting_bit"]
    if (servo["di_raw"] & 1) != bit:
        raise Interlock("external_SON_not_active")
    if ((servo["di_raw"] >> 2) & 1) != bit:
        raise Interlock("external_stop_chain_open")
    do_on=config["qualification"]["do_conducting_bit"]
    if any(((servo["do_raw"] >> n)&1)!=do_on for n in (0,1,3)):
        raise Interlock("servo_not_ready_alarm_or_brake_not_released")


def supervise(rtu, watchdog, bench, config, profile, out, *, clock=time.monotonic,
              sleep=time.sleep, cancel=lambda: False, simulation=False):
    """Resources are injected so fault paths are exercised without any hardware."""
    missing = readiness(config)
    if missing:
        raise Interlock("commissioning_missing:"+",".join(missing))
    limits = Limits(**config["limits"])
    control = LoadControl(limits)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    seed = config.get("profile_seed", 20261122)
    manifest = dict(schema="mic.t3d.load.v1", run_id=uuid.uuid4().hex,
        started_utc=datetime.now(timezone.utc).isoformat(), completed=False,
        hardware_validated=False, hardware_session=not simulation, simulation=simulation, profile=profile, seed=seed,
        limits=asdict(limits), configuration=config, source_sha256=source_hashes(),
        commands_to_air_start=0, torque_source="volatile_P145_integer_percent",
        torque_ground_truth=False, encoder_reference_source="T3D_FC04_rpm",
        time_alignment="host_poll_intervals_only_not_synchronized_MCU_samples",
        nonzero_commands=0, stop_results={}, failure=None)
    manifest["permit_controller"]="red_board"
    manifest["permit_backend"]=config["red_board"]["backend"]
    manifest["autonomous_host_loss_shutdown"]=config["red_board"]["backend"]!="stock_hid"
    manifest["reported_permit_firmware_id"]=getattr(watchdog,"firmware_id",None)
    dump(out/"manifest.json", manifest)
    cap = min(25, int(limits.max_torque_nm / limits.rated_torque_nm*100))
    baseline_trace = len(getattr(rtu, "trace", []))
    try:
        parameters = parameter_snapshot(rtu)
        dump(out/"parameters_before.json", parameters)
        mismatch = parameter_mismatches(parameters, config)
        if mismatch:
            raise Interlock("T3D_parameter_mismatch:"+json.dumps(mismatch))
        if parameters.get("145") != 0:
            raise Interlock("P145_not_zero_at_admission")
        rtu.torque(0, cap)
        waiting_since = clock()
        active_since = None
        run_key = None
        previous = None
        previous_command = None
        feedback_nonzero = 0
        with (out/"samples.jsonl").open("x", encoding="utf-8") as log:
            while True:
                cycle_start = clock()
                if cancel():
                    raise Interlock("operator_stop")
                servo = telemetry(rtu)
                bench_read_start=clock()
                status = bench.status()
                acquired = clock()
                if acquired-cycle_start > limits.deadline_s:
                    raise Interlock("acquisition_deadline")
                if active_since is None and status.get("pwm") == 0:
                    # No heartbeat: CZERO stays active while the AIR is stopped.
                    if acquired-waiting_since > 30:
                        raise Interlock("waiting_for_AIR_start_timeout")
                    log.write(json.dumps(dict(kind="waiting",host_monotonic=acquired,
                        servo=servo,bench=status),allow_nan=False)+"\n")
                    log.flush()
                    sleep(max(0, limits.cycle_s-(clock()-cycle_start)))
                    continue
                check_running_sample(status, servo, config, run_key)
                if previous_command is not None:
                    conducting=config["qualification"]["di_conducting_bit"]
                    if ((servo["di_raw"]>>1)&1)!=conducting:
                        raise Interlock("watchdog_CZERO_input_not_confirmed")
                    if abs(servo["torque_command_percent"]-previous_command)>1:
                        raise Interlock("T3D_command_feedback_mismatch")
                feedback_nonzero+=int(abs(servo["torque_percent"])>=1)
                if active_since is None:
                    active_since = acquired
                    previous = acquired-limits.cycle_s
                    run_key = (status["run_id"], status["run_start_ms"])
                    manifest["native_run_key"] = [*config["expected_firmware_pair"], *run_key]
                t = acquired-active_since
                if t >= limits.duration_s:
                    break
                dt = acquired-previous
                previous = acquired
                requested = requested_load(profile, t, limits, seed)
                percent = control.update(requested, servo["rpm"], dt, servo["torque_percent"])
                if clock()-cycle_start > limits.deadline_s:
                    raise Interlock("decision_deadline")
                if cancel():
                    raise Interlock("operator_stop")
                rtu.torque(percent, cap)
                if clock()-cycle_start > limits.deadline_s:
                    raise Interlock("command_deadline")
                nonce = watchdog.renew()
                previous_command=percent
                elapsed = clock()-cycle_start
                if elapsed > limits.cycle_s:
                    raise Interlock("cycle_deadline")
                manifest["nonzero_commands"] += int(percent != 0)
                row = dict(kind="sample",t_s=t,host_monotonic=acquired,cycle_s=elapsed,
                    requested_load_nm=requested,command_percent=percent,
                    servo_command_nm=percent*limits.rated_torque_nm/100,
                    servo_reported_torque_nm=servo["torque_percent"]*limits.rated_torque_nm/100,
                    shaft_torque_ground_truth_nm=None,energy_budget_used_j=control.energy_j,
                    permit_ack_sequence=nonce,servo=servo,bench=status,
                    bench_read_start_monotonic=bench_read_start,bench_read_end_monotonic=acquired)
                log.write(json.dumps(row,allow_nan=False)+"\n")
                log.flush()
                sleep(max(0,limits.cycle_s-(clock()-cycle_start)))
        manifest["completed"] = True
        manifest["excitation_commanded"] = manifest["nonzero_commands"] > 0
        manifest["drive_torque_feedback_nonzero_samples"] = feedback_nonzero
    except BaseException as exc:
        manifest["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        # CZERO first. Keep SON/brake sequencing under its independent hardware
        # circuit; do not drop SON into a rotating holding brake from Python.
        for name, action in (("watchdog_disarm", watchdog.disarm),
                             ("zero_torque_readback", lambda: rtu.torque(0,cap)),
                             ("AIR_stop", bench.stop)):
            try:
                action()
                manifest["stop_results"][name] = {"acknowledged": True}
            except BaseException as exc:
                manifest["stop_results"][name] = {"acknowledged": False, "error": str(exc)}
        if not all(x["acknowledged"] for x in manifest["stop_results"].values()):
            manifest["completed"] = False
            manifest["failure"] = manifest["failure"] or "Stop path not fully acknowledged"
        manifest["energy_budget_used_j"] = control.energy_j
        dump(out/"rtu_trace.json",getattr(rtu,"trace",[])[baseline_trace:])
        dump(out/"permit_trace.json",getattr(watchdog,"trace",[]))
        dump(out/"manifest.json",manifest)
        outputs = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
        dump(out/"sha256.json", outputs)
    if not manifest["completed"]:
        raise Interlock(manifest["failure"])
    return manifest


def probe(config):
    modbus = config["modbus"]
    stream = open_identified_serial(config["servo_usb"],modbus["baud"],modbus["parity"],.12)
    try:
        rtu=Rtu(stream,modbus["unit"],modbus["baud"])
        p=parameter_snapshot(rtu)
        return dict(parameters=p,telemetry=telemetry(rtu),parameter_mismatches=parameter_mismatches(p,config),
                    write_commands=0,commissioning_missing=readiness(config),rtu_trace=rtu.trace)
    finally:
        stream.close()


def probe_red_controller(config):
    red=config["red_board"]
    if red.get("backend")=="stock_hid":
        from .red_board import passive_probe
        return passive_probe(red["stock_identity"])
    stream=open_identified_serial(red["runtime_usb"],115200,"N",.15)
    try:
        watchdog=Watchdog(stream)
        image=watchdog.identify(red["expected_firmware_id"])
        watchdog.disarm()
        return dict(controller="red_board",firmware_id=image,permit_enable_commands=0,
                    disarm_acknowledged=True,trace=watchdog.trace,electrical_output_measured=False)
    finally:stream.close()


def run_live(config,profile,out,cancel=lambda:False):
    if config.get("fixture_only"):
        raise Interlock("Simulation qualification cannot be used on real hardware")
    missing=readiness(config)
    if missing:
        raise Interlock("No ports opened; commissioning incomplete: "+", ".join(missing))
    red=config["red_board"]
    if red["backend"]=="stock_hid":
        from .red_board import RedBoard
        from .stock_permit import StockPermit
        with RedBoard(red["stock_identity"],write_enabled=True) as board:
            permit=StockPermit(board)
            try:
                modbus=config["modbus"]
                servo_stream=open_identified_serial(config["servo_usb"],modbus["baud"],modbus["parity"],.12)
                try:
                    return supervise(Rtu(servo_stream,modbus["unit"],modbus["baud"]),permit,
                        BenchHttp(config["bench_url"]),config,profile,out,cancel=cancel)
                finally:servo_stream.close()
            finally:permit.disarm()
    if config["servo_usb"].get("port")==red["runtime_usb"].get("port"):
        raise Interlock("Servo and independent watchdog cannot share one serial port")
    modbus=config["modbus"]
    servo_stream=open_identified_serial(config["servo_usb"],modbus["baud"],modbus["parity"],.12)
    try:
        wd_stream=open_identified_serial(red["runtime_usb"],115200,"N",.15)
        try:
            watchdog=Watchdog(wd_stream)
            watchdog.identify(red["expected_firmware_id"])
            return supervise(Rtu(servo_stream,modbus["unit"],modbus["baud"]),watchdog,
                BenchHttp(config["bench_url"]),config,profile,out,cancel=cancel)
        finally:
            wd_stream.close()
    finally:
        servo_stream.close()
