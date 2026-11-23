"""Behavioral tests for torque direction, faults, protocol and independent lease."""
import copy
import json
from pathlib import Path
import struct

import pytest

from load_bench.control import (Interlock, Limits, LoadControl, PROFILES,
    bench_problem, expected_parameters, parameter_mismatches, readiness, requested_load)
from load_bench.protocol import (ProtocolError,Rtu,crc16,frame,i16,i32,parse_reply,
    read_request,torque_request)
from load_bench.runner import supervise,run_live,check_running_sample
from load_bench.simulation import (Clock,EmulatedDrive,EmulatedWatchdog,
    EmulatedBench,fixture_config,simulate)
from load_bench.watchdog import Watchdog,parse_line,wire_line

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def config():
    return json.loads((ROOT/"load_bench/config.template.json").read_text())


def test_independent_standard_crc_vectors():
    assert crc16(b"123456789")==0x4B37
    assert frame(bytes.fromhex("01030000000a")).hex()=="01030000000ac5cd"


@pytest.mark.parametrize("unit,fn,start,count",[(0,3,0,1),(33,4,0,1),(1,4,0,9),(1,6,0,1),(1,3,65535,2)])
def test_broadcast_and_unbounded_reads_are_rejected(unit,fn,start,count):
    with pytest.raises(ValueError):read_request(unit,fn,start,count)


def test_signed_percent_and_decimal_parameter_address():
    request=torque_request(1,-7,25)
    assert request[:6]==bytes.fromhex("01060091fff9")
    assert i16(0xfff9)==-7
    assert i32(0xffff,0xffff)==-1
    assert parse_reply(request,request)==[]
    with pytest.raises(ValueError):torque_request(1,26,25)


def test_reply_crc_identity_length_echo_and_exceptions():
    request=read_request(1,4,0,1)
    assert parse_reply(request,frame(bytes.fromhex("010402fff9")))==[65529]
    for reply in [frame(bytes.fromhex("0204020001")),frame(bytes.fromhex("0103020001")),
                  frame(bytes.fromhex("01040400010002")),b"\x01\x04\x02\x00\x01\x00\x00",
                  frame(bytes.fromhex("018402"))]:
        with pytest.raises(ProtocolError):parse_reply(request,reply)
    with pytest.raises(ProtocolError):
        parse_reply(torque_request(1,-7,25),torque_request(1,-6,25))


@pytest.mark.parametrize("rpm",[80,150,350,-80,-150,-350])
def test_torque_always_opposes_rotation_and_obeys_limits(rpm):
    limits=Limits(max_power_w=2)
    controller=LoadControl(limits)
    for _ in range(4):
        command=controller.update(.2,rpm,.5)
        torque=command*limits.rated_torque_nm/100
        assert torque*rpm<=0
        assert abs(torque)<=limits.max_torque_nm
        assert abs(torque*rpm*3.141592653589793/30)<=limits.max_power_w+1e-12


def test_slew_and_integer_rounding_never_raise_requested_torque():
    c=LoadControl()
    first=c.update(.12,200,.5)
    assert abs(first)*1.27/100<=.06
    second=c.update(.12,200,.5)
    assert abs(second)*1.27/100<=abs(first)*1.27/100+.06
    assert c.update(0,200,.5)==0


@pytest.mark.parametrize("fault",["nan","overspeed","stall","reverse","gap","energy","nis","motoring","torque"])
def test_fault_latches_and_cannot_recover_by_next_good_sample(fault):
    c=LoadControl();c.update(.12,200,.5)
    args=dict(requested_nm=.12,rpm=200,dt=.5)
    if fault=="nan":args["rpm"]=float("nan")
    elif fault=="overspeed":args["rpm"]=351
    elif fault=="stall":args["rpm"]=0
    elif fault=="reverse":args["rpm"]=-200
    elif fault=="gap":args["dt"]=.8
    elif fault=="energy":c.energy_j=15
    elif fault=="nis":args["nis"]=25
    elif fault=="motoring":args["measured_torque_percent"]=3
    elif fault=="torque":args["measured_torque_percent"]=-28
    with pytest.raises(Interlock):c.update(**args)
    with pytest.raises(Interlock,match="latched"):c.update(0,200,.5)


def test_no_standstill_torque_and_zero_tails():
    c=LoadControl()
    assert c.update(.12,0,.5)==0
    for profile in PROFILES:
        values=[requested_load(profile,t,Limits()) for t in [0,.5,1,1.5,2,2.5,3,3.5]]
        assert min(values)>=0 and max(values)<=.12
        assert values[:2]==[0,0] and values[-2:]==[0,0]
        assert values==[requested_load(profile,t,Limits()) for t in [0,.5,1,1.5,2,2.5,3,3.5]]
        if profile=="prbs":assert set(values[2:6]) <= {.03,.12}


def test_template_is_not_a_motor_start_qualification(config,monkeypatch,tmp_path):
    assert len(readiness(config))>=10
    monkeypatch.setattr("load_bench.runner.open_identified_serial",lambda *a:pytest.fail("Must not open a port"))
    with pytest.raises(Interlock,match="No ports opened"):run_live(config,"step",tmp_path/"run")
    good=fixture_config(config)
    assert readiness(good)==[]
    with pytest.raises(Interlock,match="Simulation"):run_live(good,"step",tmp_path/"run2")
    good["qualification"]["validated_regen_energy_j"]=20
    # Stock I/O does not guarantee a bounded dropout time; continuous thermal
    # capability, not a fictitious finite fault-energy allowance, is required.
    good["qualification"]["regen_power_rating_is_continuous"]=False
    assert "regen_power_rating_is_continuous" in readiness(good)


def test_parameter_recipe_preserves_external_enable_and_zero_permit(config):
    p=expected_parameters(config)
    assert p[4]==2 and p[26]==1 and p[98]==0
    assert p[101]==p[102]==-8
    assert [p[k] for k in range(120,125)]==[0]*5
    s={str(k):v for k,v in p.items()}
    assert parameter_mismatches(s,config)=={}
    s["98"]=1
    assert "98" in parameter_mismatches(s,config)


def test_fresh_native_run_and_faults_are_mandatory(config):
    c=fixture_config(config);s=EmulatedBench(c).status()
    assert bench_problem(s,c["expected_firmware_pair"]) is None
    for field,value in [("mc_age_ms",300),("estop",1),("mc_current_frozen",1),
                        ("pwm",0),("run_id",None),("freq_cmd",5.1),("mc_fault_occurred_mask",4)]:
        bad=dict(s);bad[field]=value
        assert bench_problem(bad,c["expected_firmware_pair"])
    assert bench_problem(s,c["expected_firmware_pair"],(43,1234))=="air_run_changed"


@pytest.mark.parametrize("profile",PROFILES)
def test_end_to_end_real_rtu_codec_with_synthetic_controller(profile,config,tmp_path):
    folder=tmp_path/profile
    result=simulate(config,profile,folder)
    assert result["completed"] and result["simulation"]
    assert not result["hardware_validated"]
    assert result["commands_to_air_start"]==0
    assert all(r["acknowledged"] for r in result["stop_results"].values())
    trace=json.loads((folder/"rtu_trace.json").read_text())
    writes=[bytes.fromhex(x["request"]) for x in trace if x["request"][2:4]=="06"]
    assert writes and all(w[2:4]==b"\x00\x91" for w in writes)
    assert writes[-1][4:6]==b"\x00\x00"
    assert all((int.from_bytes(w[4:6],"big") in (0,) or int.from_bytes(w[4:6],"big")>=65511) for w in writes)
    if profile!="zero":assert result["nonzero_commands"]>0


@pytest.mark.parametrize("fault",["crc","alarm","AIR_fault","cancel","CZERO_wire","wrong_echo"])
def test_runtime_failures_take_all_stop_paths(config,tmp_path,fault):
    cfg=fixture_config(config);clock=Clock();drive=EmulatedDrive(cfg,clock)
    rtu=Rtu(drive,clock=clock.now,sleep=clock.sleep)
    wd=EmulatedWatchdog(drive);bench=EmulatedBench(cfg)
    count=[0]
    original=bench.status
    def status():
        count[0]+=1
        if count[0]==4:
            if fault=="crc":drive.corrupt_next=True
            elif fault=="alarm":drive.alarm=2
            elif fault=="AIR_fault":bench.fault={"mc_fault_current_mask":4}
            elif fault=="CZERO_wire":drive.force_czero=True
            elif fault=="wrong_echo":drive.bad_echo_nonzero=True
        return original()
    bench.status=status
    with pytest.raises((Interlock,ProtocolError)):
        supervise(rtu,wd,bench,cfg,"step",tmp_path/fault,clock=clock.now,sleep=clock.sleep,
                  cancel=lambda:fault=="cancel" and count[0]>=4,simulation=True)
    manifest=json.loads((tmp_path/fault/"manifest.json").read_text())
    assert not manifest["completed"]
    assert bench.stops==1 and not drive.permit and drive.parameters[145]==0
    assert manifest["stop_results"]["AIR_stop"]["acknowledged"]


def test_watchdog_frame_is_checked_and_not_any_serial_text():
    for kind in ("Q","ACK","OK","OFF"):
        assert parse_line(wire_line(f"{kind} 0000002A"))==(kind,42)
    for line in (b"Q 0000002A 0000\n",b"HB 42\n",b"OK 2a\n",b"x"*65):
        with pytest.raises(ValueError):parse_line(line)


@pytest.mark.parametrize("fault",[None,"partial_write","no_ack","bad_crc"])
def test_watchdog_stop_requires_acknowledged_low_output(fault):
    clock=Clock()
    class Stream:
        def reset_input_buffer(self):pass
        def write(self,data):
            assert data==b"STOP\n"
            return 0 if fault=="partial_write" else len(data)
        def readline(self,n):
            clock.sleep(.15)
            if fault=="no_ack":return wire_line("Q 0000002A")
            if fault=="bad_crc":return b"OFF 00000000 0000\n"
            return wire_line("OFF 00000000")
    wd=Watchdog(Stream(),clock=clock.now)
    if fault:
        with pytest.raises((RuntimeError,ValueError)):wd.disarm()
    else:wd.disarm()
