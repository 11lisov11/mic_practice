"""Protocol emulator and synthetic fixtures. Not a validated AIR/T3D motor model."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import struct

from .control import expected_parameters
from .protocol import Rtu, crc16, frame
from .runner import supervise


class Clock:
    def __init__(self):
        self.t = 100.
    def now(self):
        return self.t
    def sleep(self, seconds):
        self.t += seconds


def fixture_config(config):
    result=copy.deepcopy(config)
    result["fixture_only"]=True
    result["expected_algorithm"]=1
    result["qualification"]={k:True for k in result["qualification"]}
    result["qualification"].update(actual_rated_torque_nm=1.27,di_conducting_bit=0,do_conducting_bit=1,
        watchdog_measured_drop_s=.75,validated_regen_power_w=100.,validated_regen_energy_j=100.)
    return result


class EmulatedDrive:
    def __init__(self, config, clock):
        self.clock=clock
        self.parameters=expected_parameters(config)
        self.parameters[145]=0
        self.input=b""
        self.requests=[]
        self.permit=False
        self.rpm=200
        self.alarm=0
        self.corrupt_next=False
        self.force_czero=False
        self.bad_echo_nonzero=False
    def reset_input_buffer(self):
        self.input=b""
    def write(self, request):
        self.requests.append(request)
        if crc16(request[:-2])!=int.from_bytes(request[-2:],"little"):
            raise RuntimeError("Emulator received bad CRC")
        unit,fn,address,value=struct.unpack(">BBHH",request[:-2])
        if fn==6:
            if address!=145:
                raise RuntimeError("Unexpected actuator address")
            self.parameters[145]=value-65536 if value&32768 else value
            self.input=request
            if self.bad_echo_nonzero and value:
                self.input=frame(struct.pack(">BBHH",unit,fn,address,(value+1)&65535))
        elif fn in (3,4):
            if value>8:
                raise RuntimeError("Emulator read limit")
            torque=self.parameters[145] if self.permit and not self.force_czero else 0
            # Pure synthetic encoder/current readout; no motor plant accuracy claimed.
            di=0 if self.permit and not self.force_czero else 2
            state={0:self.rpm,5:0,6:0,9:torque,11:1,15:torque,18:di,19:15,
                   0x17:3,0x18:2,0x1A:self.alarm,0x1B:self.rpm*10}
            registers=[(self.parameters if fn==3 else state).get(i,0)&65535 for i in range(address,address+value)]
            self.input=frame(bytes((unit,fn,2*value))+struct.pack(">"+"H"*value,*registers))
        else:
            raise RuntimeError("Unexpected function")
        if self.corrupt_next:
            self.input=self.input[:-1]+bytes((self.input[-1]^1,))
            self.corrupt_next=False
        return len(request)
    def read(self,n):
        self.clock.t+=.001
        result,self.input=self.input[:n],self.input[n:]
        return result


class EmulatedWatchdog:
    def __init__(self,drive):self.drive,self.counter=drive,0
    def renew(self):
        self.drive.permit=True
        self.counter+=1
        return self.counter
    def disarm(self):self.drive.permit=False


class EmulatedBench:
    def __init__(self,config):self.config,self.stops,self.fault=config,0,None
    def status(self):
        s=dict(fw_build=self.config["expected_firmware_pair"][0],
               mc_fw_build=self.config["expected_firmware_pair"][1],
               mc_age_ms=1,mc_current_age_ms=1,mc_fault_current_mask=0,
               mc_fault_occurred_mask=0,estop=0,mc_current_zero_ready=1,
               mc_current_telemetry_valid=1,mc_current_frozen=0,freq_cmd=5.,pwm=1,
               run_id=42,run_start_ms=1234,algorithm_selected=1,algorithm_fault=0,
               rpm_est_valid=1,rpm_est=200.,mc_current_rms_a=[.2,.2,.2])
        if self.fault:s.update(self.fault)
        return s
    def stop(self):self.stops+=1;return {"ok":True}


def simulate(config, profile, out):
    fixture=fixture_config(config)
    clock=Clock()
    drive=EmulatedDrive(fixture,clock)
    rtu=Rtu(drive,clock=clock.now,sleep=clock.sleep)
    result=supervise(rtu,EmulatedWatchdog(drive),EmulatedBench(fixture),fixture,profile,out,
        clock=clock.now,sleep=clock.sleep,simulation=True)
    return result


def export_csv(folder):
    import csv
    folder=Path(folder)
    rows=[json.loads(x) for x in (folder/"samples.jsonl").read_text(encoding="utf-8").splitlines()]
    rows=[r for r in rows if r["kind"]=="sample"]
    path=folder/"samples.csv"
    with path.open("w",newline="",encoding="utf-8-sig") as output:
        writer=csv.writer(output)
        writer.writerow(["host_t_s","requested_load_Nm","servo_command_percent","servo_command_Nm",
                         "encoder_rpm_polled","servo_reported_torque_Nm","shaft_torque_ground_truth_Nm",
                         "energy_bound_J","native_run_id","algorithm_selected","rpm_est_valid","rpm_est"])
        for r in rows:
            writer.writerow([r["t_s"],r["requested_load_nm"],r["command_percent"],r["servo_command_nm"],
                r["servo"]["rpm"],r["servo_reported_torque_nm"],None,r["energy_budget_used_j"],
                r["bench"].get("run_id"),r["bench"].get("algorithm_selected"),
                r["bench"].get("rpm_est_valid"),r["bench"].get("rpm_est")])
    return path
