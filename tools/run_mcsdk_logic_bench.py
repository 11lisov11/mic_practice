"""Measure the production-derived MCSDK PWM on the isolated fixture, then restore."""
from __future__ import annotations

import argparse
import csv as csv_module
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import time

from nucleo_logic_capture import capture_checks
from prepare_mcsdk_logic_bench import BENCH_BUILD, function_span
from run_wifi_nucleo_pwm_bench import (
    WifiHmi, analyze_static, capture, read_control_token, run_logged, sha256,
    verify_unpowered_preflash, wait_status, analyze_external_break,
)
from saleae_pwm_analyze import analyze_csv, load_csv, transitions
from verify_wifi_command_path import get_wifi_logs
from wifi_bench_scenarios import operator_keepalive, outputs_off
from wifi_stop_tail_probe import parse_registers, TIM1, GPIOA

PROGRAMMER = "C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe"
GNU = Path("C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins/"
           "com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.14.3.rel1.win32_1.0.100.202602081740/tools/bin")
SERIAL = "003A002C3335510933383531"
DEVICE = "A7D1BB81883C0092"


def waveform(csv: Path, rate: int, frequency: float, deadtime_s: float,
             settled: bool = True, require_sd_high: bool = True) -> dict:
    raw_analysis = analyze_csv(csv, expect_pwm=True, selected_sample_rate_hz=rate,
                           max_sample_period_ns=1e9/rate)
    times, values = load_csv(csv, list(range(7)))
    analysis = raw_analysis
    # Stable-running measurements exclude the known stale 2048-sample acquisition
    # prefix. Continuous START tests instead use their complete uninterrupted CSV.
    quarantine_s = 4096/rate if settled else 0.0
    if settled:
        cut = times[0]+quarantine_s
        previous = max(i for i,t in enumerate(times) if t<=cut)
        qualified = csv.parent/"settled_digital.csv"
        with qualified.open("w",newline="") as stream:
            writer=csv_module.writer(stream)
            writer.writerow(["Time [s]",*[f"Channel {ch}" for ch in range(7)]])
            writer.writerow([cut,*[values[ch][previous] for ch in range(7)]])
            writer.writerows([t,*[values[ch][i] for ch in range(7)]]
                            for i,t in enumerate(times) if t>cut)
        analysis=analyze_csv(qualified,expect_pwm=True,selected_sample_rate_hz=rate,
                             max_sample_period_ns=1e9/rate)
    checks = capture_checks(analysis, True)["checks"]
    checks["raw_capture_no_overlap"]=raw_analysis["no_overlap_pass"]
    checks["production_carrier"] = all(abs(c["freq_hz_from_rising"]-frequency) < frequency*0.01
                                       for c in analysis["channels"].values())
    checks["production_deadtime"] = all(p["min_gap_s"] is not None and
        abs(p["min_gap_s"]-deadtime_s) <= 2.0/rate + 1e-8 for p in analysis["pairs"].values())
    if require_sd_high:
        checks["SD_remains_HIGH"] = all(values[6])
    return {"pass": all(checks.values()), "checks": checks, "analysis": analysis,
            "raw_analysis":raw_analysis,"acquisition_prefix_quarantined_s":quarantine_s,
            "SD_HIGH_required":require_sd_high,
            "expected_carrier_hz": frequency, "expected_deadtime_s": deadtime_s}


def off_tail(csv: Path, rate: int) -> dict:
    times, values = load_csv(csv, list(range(7)))
    edges = {ch: transitions(times, values[ch]) for ch in range(6)}
    last = max((e[-1]["time"] for e in edges.values() if e), default=times[0])
    tail = [i for i, t in enumerate(times) if t >= last]
    checks = {
        "sustained_PWM_before_stop": all(len(e)>100 for e in edges.values()),
        "LOW_tail_at_least_100ms": times[-1]-last >= 0.1,
        "six_outputs_remain_LOW": bool(tail) and all(values[ch][i]==0 for ch in range(6) for i in tail),
        "SD_remains_HIGH": all(values[6]),
    }
    return {"pass": all(checks.values()), "checks": checks, "last_edge_s": last,
            "low_tail_s": times[-1]-last, "sample_period_s": 1/rate}


def compare_code_sections(production: Path, bench: Path, out: Path) -> dict:
    sections = {
        "Application/User/stm32g4xx_mc_it.o": ["TIM1_BRK_TIM15_IRQHandler", "TIM1_UP_TIM16_IRQHandler"],
        "Middlewares/MotorControl/pwm.o": ["PWM_SwitchOnPWM", "PWM_SwitchOffPWM", "PWM_SetPhasePWMOutputs"],
        "Application/User/pwm_curr_fdbk.o": ["PWMC_DP_Handler"],
    }
    out.mkdir()
    evidence = {}
    timer_sources = []
    for build in (production, bench):
        text = (build.parents[1]/"Src/main.c").read_text(encoding="utf-8-sig")
        begin, end = function_span(text, "MX_TIM1_Init")
        timer_sources.append(text[begin:end])
    timer_equal = timer_sources[0] == timer_sources[1]
    for file, functions in sections.items():
        for func in functions:
            binaries=[]
            for tag, build in (("production",production),("bench",bench)):
                path=out/(func+"_"+tag+".bin")
                run_logged([str(GNU/"arm-none-eabi-objcopy.exe"), "--dump-section",
                            ".text."+func+"="+str(path), str(build/file)], out/(func+"_"+tag+".log"))
                if not path.is_file() or path.stat().st_size==0:
                    raise RuntimeError("Missing code section " + func)
                binaries.append(path.read_bytes())
            evidence[func]={"equal":binaries[0]==binaries[1], "bytes":len(binaries[0]),
                            "sha256":hashlib.sha256(binaries[0]).hexdigest()}
    return {"pass":timer_equal and all(e["equal"] for e in evidence.values()),"functions":evidence,
            "timer_initializer_source_identical": timer_equal,
            "scope":"unlinked function machine-code sections; linker relocation addresses excluded"}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-isolated-zero-bus",action="store_true")
    parser.add_argument("--fixture",type=Path,required=True)
    parser.add_argument("--outdir",type=Path,required=True)
    parser.add_argument("--reuse-steady-evidence",type=Path,
                        help="Reuse passed 5/20 Hz subchecks only for the identical fixture and production hashes")
    parser.add_argument("--input-break-test",action="store_true",
                        help="Temporarily invert external BKIN input polarity; keep the locked GPIO unchanged")
    args=parser.parse_args()
    if not args.confirm_isolated_zero_bus:
        parser.error("J1, motor and J4 disconnected; measured zero DC bus required")
    from saleae import automation
    root=Path(__file__).resolve().parents[1]
    fixture=args.fixture.resolve()
    out=args.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    logs=out/"logs"; logs.mkdir()
    production_project=root/"mcsdk_reference/AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV"
    production_build=production_project/"STM32CubeIDE/Debug"
    bench_build=fixture/"project/STM32CubeIDE/Debug"
    name="ACIM-NUCLEOG431RB-IPM15B-VF_OL"
    production=root/"firmware/ready_to_flash/nucleo"/(name+".hex")
    production_bin=production.with_suffix(".bin")
    bench=bench_build/(name+".hex")
    report={"pass":False,"hardware_validated":False,"production_image_active_PWM_tested":False,
            "scope":"MCSDK-derived isolated logic fixture, not powered inverter qualification",
            "commands":[],"restored":False,"images":{"production":sha256(production),"bench":sha256(bench)}}
    token=read_control_token("adb","3880458060","/home/arduino/.config/mic-ai/control_token")
    hmi=WifiHmi("http://192.168.1.138:8080",token,report["commands"],via_wsl=True)
    modified=False
    diagnostic_addresses=[]

    def cli(extra, log, reset_mode=False):
        run_logged([PROGRAMMER,"-c","port=SWD","mode="+("UR" if reset_mode else "HOTPLUG"),
                    *( ["reset=HWrst"] if reset_mode else [] ),"sn="+SERIAL,*extra],logs/log,timeout=60)
        return parse_registers((logs/log).read_text(encoding="utf-8-sig"))

    def clean_bench():
        hmi.fail_safe_stop()
        wait_status(hmi,lambda s:outputs_off(s) and s.get("mc_fw_build")==BENCH_BUILD and
                    s.get("bp_softstart_ready")==1 and float(s.get("vdc",999))<=2,
                    12,"fixture ADC settled before CLEAR")
        hmi.command("CLEAR")
        return wait_status(hmi,lambda s: outputs_off(s) and s.get("bp_fault")==0 and
            s.get("estop")==0 and s.get("bp_bad_cnt")==0 and s.get("bp_bad")==0 and
            s.get("mc_fw_build")==BENCH_BUILD,8,"MCSDK bench SAFE")

    def arm():
        clean_bench()
        hmi.post("/api/hv-arm",{"action":"arm","confirm":"ARM LV HV OFF"},"isolated ARM LV")
        hmi.command("MODE VF"); hmi.command("SET FREQ 5")

    def event_capture(manager, folder, duration, rate, action):
        folder.mkdir()
        with manager.start_capture(device_id=DEVICE,
                device_configuration=automation.LogicDeviceConfiguration(
                    enabled_digital_channels=list(range(7)),digital_sample_rate=rate),
                capture_configuration=automation.CaptureConfiguration(
                    capture_mode=automation.TimedCaptureMode(duration_seconds=duration))) as session:
            # Actions cannot run until the API has actually started this acquisition.
            action()
            session.wait()
            session.save_capture(str(folder/"capture.sal"))
            session.export_raw_data_csv(directory=str(folder/"csv"),digital_channels=list(range(7)))
        return folder/"csv/digital.csv"

    try:
        report["code_equivalence"]=compare_code_sections(production_build,bench_build,out/"code_equivalence")
        if not report["code_equivalence"]["pass"]:
            raise RuntimeError("Critical machine code differs")
        report["before"]=hmi.status(); verify_unpowered_preflash(report["before"])
        if report["before"].get("mc_fw_build")!=2026100601:
            raise RuntimeError("Expected current production image")
        gdb_cmd=[str(GNU/"arm-none-eabi-gdb.exe"),"-batch","-ex","file "+(bench_build/(name+".elf")).as_posix()]
        expressions=["ACIM_VF_Component_M1.fFlux_Freq_Hz", "mic_bench_adc_raw_last", "mic_bench_adc_raw_max",
                     "mic_bench_interlock_reason", "mic_bench_adc_samples", "mic_bench_last_adc_ms",
                     "Mci[0].CurrentFaults", "Mci[0].PastFaults", "mic_bench_raw_sum",
                     "BusVoltageSensor_M1._Super.ConversionFactor"]
        for expression in expressions: gdb_cmd.extend(["-ex","p/x &"+expression])
        gdb=subprocess.run(gdb_cmd,capture_output=True,text=True,check=True)
        addr=int(re.search(r"\$1 = (0x[0-9a-f]+)",gdb.stdout)[1],16)
        diagnostic_addresses=[int(a,16) for a in re.findall(r"\$\d+ = (0x[0-9a-f]+)",gdb.stdout)][1:]
        (logs/"frequency_address.log").write_text(gdb.stdout)
        if not 0x20000000<=addr<0x20008000: raise RuntimeError("Invalid frequency address")
        with automation.Manager.connect(port=10430) as manager:
            if not any(d.device_id==DEVICE and not d.is_simulation for d in manager.get_devices()):
                raise RuntimeError("Physical Saleae missing")
            hmi.fail_safe_stop()
            modified=True
            cli(["-w",str(bench),"-v","-rst"],"flash_fixture.log",True)
            wait_status(hmi,lambda s:s.get("mc_fw_build")==BENCH_BUILD and outputs_off(s),8,"fixture identity")
            report["bench_safe"]=clean_bench()
            hmi.post("/api/arm-profile",{"profile":"lv"},"isolated LV profile")
            rate=24_000_000
            expected_hz=16000.0; expected_dead=1.35e-6
            with operator_keepalive(hmi) as keepalive:
                steady_cases=((5,6.0),(20,12.0))
                if args.reuse_steady_evidence:
                    path=args.reuse_steady_evidence.resolve()
                    previous=json.loads(path.read_text())
                    if previous.get("images")!=report["images"] or not all(
                            previous.get(f"pwm_{freq}hz",{}).get("pass") is True for freq in (5,20)):
                        raise RuntimeError("Reused steady-state evidence is not passed or hash-matched")
                    report["steady_reuse"]={"path":str(path),"sha256":sha256(path),
                                            "scope":"passed subchecks only; prior overall failure is preserved"}
                    for freq in (5,20): report[f"pwm_{freq}hz"]=previous[f"pwm_{freq}hz"]
                    steady_cases=()
                for freq, delay in steady_cases:
                    arm(); hmi.command("START"); hmi.command("SET RUNLIMIT 14")
                    report["active_status"]=wait_status(hmi,lambda s:s.get("pwm")==1 and int(s.get("bp_status",0))&0x20,
                                                        3,"real MCSDK RUN")
                    if freq==20: hmi.command("SET FREQ 20")
                    time.sleep(delay)
                    words=cli(["-r32",hex(addr),"4"],f"vf_frequency_{freq}.log")
                    observed=struct.unpack("<f",struct.pack("<I",words[addr]))[0]
                    csv=capture(manager,DEVICE,out/f"pwm_{freq}hz",0.12,rate)
                    entry=waveform(csv,rate,expected_hz,expected_dead)
                    entry["vf_frequency_observed_hz"]=observed
                    entry["vf_frequency_close_to_command"]=abs(observed-freq)<0.5
                    entry["pass"]=entry["pass"] and entry["vf_frequency_close_to_command"]
                    entry["status"]=hmi.status(); report[f"pwm_{freq}hz"]=entry
                    if not entry["pass"]: raise RuntimeError(f"MCSDK {freq} Hz measurement failed")
                    report[f"normal_stop_{freq}"]=hmi.fail_safe_stop()[1]
                    wait_status(hmi,outputs_off,3,"normal STOP")
                report["after_normal_stop"]=analyze_static(capture(manager,DEVICE,out/"after_normal_stop",0.1,rate),
                    settle_s=0.002,sample_rate_hz=rate)
                # Start within a single already-running capture, never at a buffer boundary.
                for cycle, emergency in enumerate((False,True),1):
                    arm()
                    capture(manager,DEVICE,out/f"flush_before_transition_{cycle}",0.1,rate)
                    event_rate=4_000_000
                    def transition_action():
                        time.sleep(0.35)
                        hmi.command("START")
                        wait_status(hmi,lambda s:s.get("pwm")==1 and int(s.get("bp_status",0))&0x20,
                                    2,"continuous MCSDK START")
                        time.sleep(0.4)
                        hmi.post("/api/stop-sequence",{"emergency":emergency},"continuous ESTOP" if emergency else "continuous STOP")
                        wait_status(hmi,outputs_off,3,"continuous outputs off")
                    transition_csv=event_capture(manager,out/f"continuous_transition_{cycle}",2.6,event_rate,transition_action)
                    entry=waveform(transition_csv,event_rate,expected_hz,expected_dead,settled=False)
                    entry["off_tail"]=off_tail(transition_csv,event_rate)
                    entry["pass"]=entry["pass"] and entry["off_tail"]["pass"]
                    report[f"transition_{cycle}"]=entry
                    if not entry["pass"]: raise RuntimeError("Continuous MCSDK START/STOP failed")
                # Same unchanged production IRQ, stimulated while the MCSDK PWM is active.
                arm(); hmi.command("START")
                def break_action():
                    time.sleep(0.7)
                    cli(["-w32",hex(TIM1+0x14),"0x80","-nv"],"active_BG.log")
                    report["break_status"]=wait_status(hmi,lambda s:outputs_off(s) and s.get("bp_fault")!=0,
                                                       3,"active MCSDK break")
                break_csv=event_capture(manager,out/"active_BG",2.0,4_000_000,break_action)
                report["break_waveform"]=off_tail(break_csv,4_000_000)
                code,body=hmi.request("POST","/api/start-sequence",{})
                report["restart_rejected"]={"http":code,"pass":code==409 and body.get("ok") is False}
                if args.input_break_test:
                    arm()
                    words=cli(["-r32",hex(TIM1),"104","-r32",hex(GPIOA),"36"],"input_before.log")
                    original_af1=words[TIM1+0x60]
                    if not original_af1&1 or not original_af1&(1<<9) or not words[GPIOA+0x10]&(1<<6):
                        raise RuntimeError("Expected enabled active-LOW external BKIN with PA6 HIGH")
                    hmi.command("START")
                    def input_action():
                        time.sleep(0.6)
                        try:
                            cli(["-w32",hex(TIM1+0x60),hex(original_af1&~(1<<9))],"assert_BKIN_input_polarity.log")
                            time.sleep(0.15)
                        finally:
                            cli(["-w32",hex(TIM1+0x60),hex(original_af1)],"restore_BKIN_input_polarity.log")
                        report["input_break_status"]=wait_status(hmi,lambda s:outputs_off(s) and
                            s.get("bp_fault")!=0,3,"external BKIN input chain tripped")
                    input_csv=event_capture(manager,out/"BKIN_input_chain",2.8,4_000_000,input_action)
                    checks=off_tail(input_csv,4_000_000)["checks"]
                    actual_wave=waveform(input_csv,4_000_000,expected_hz,expected_dead)
                    checks["MCSDK_waveform_valid"]=actual_wave["pass"]
                    restored_words=cli(["-r32",hex(TIM1),"104","-r32",hex(GPIOA),"36"],"input_after.log")
                    checks["GPIO_configuration_unchanged"]=all(restored_words[GPIOA+offset]==words[GPIOA+offset]
                        for offset in (0,4,0x0C,0x20))
                    checks["BKIN_polarity_restored"]=restored_words[TIM1+0x60]==original_af1
                    report["BKIN_input_chain"]={"pass":all(checks.values()),"checks":checks,"waveform":actual_wave,
                        "scope":"external BKIN input-chain stimulus by inversion; PA6 HIGH, no IPM OC/UVLO qualification"}
                    if not report["BKIN_input_chain"]["pass"]:
                        raise RuntimeError("External BKIN input-chain stimulus failed")
                report["keepalive"]=keepalive
            report["pass"]=all(report[k].get("pass") is True for k in
                ("code_equivalence","pwm_5hz","pwm_20hz","after_normal_stop","transition_1","transition_2",
                 "break_waveform","restart_rejected"))
            if args.input_break_test:
                report["pass"]=report["pass"] and report["BKIN_input_chain"]["pass"]
            report["fixture_active_PWM_validated"]=report["pass"]
    except BaseException as exc:
        report["error"]=f"{type(exc).__name__}: {exc}"
    finally:
        try:
            report["stop_before_restore"]=hmi.fail_safe_stop()[0]
            if modified:
                for index, address in enumerate(diagnostic_addresses):
                    cli(["-r32",hex(address & ~3),"4"],f"fixture_diagnostic_{index}.log")
                # Return profile while fixture CLEAR can still acknowledge faults.
                cli(["-rst"],"reset_fixture_for_profile_restore.log")
                wait_status(hmi,lambda s:s.get("mc_fw_build")==BENCH_BUILD and outputs_off(s) and
                            s.get("bp_softstart_ready")==1,15,"reset fixture zero-bus readiness")
                clean_bench()
                hmi.post("/api/arm-profile",{"profile":"hv"},"restore production HV profile")
        except Exception as exc:
            report["profile_restore_error"]=str(exc)
        try:
            if modified:
                cli(["-w",str(production),"-v","-rst"],"restore_production.log",True)
                readback=out/"production_readback.bin"
                cli(["-u","0x08000000",str(production_bin.stat().st_size),str(readback)],"readback.log")
                report["restored"]=readback.read_bytes()==production_bin.read_bytes()
                cli(["-rst"],"production_reset_after_readback.log")
            else:
                report["restored"]=True
            report["final_status"]=wait_status(hmi,lambda s:s.get("mc_fw_build")==2026100601 and
                outputs_off(s) and s.get("state")=="SAFE" and float(s.get("vdc",999))<=2,
                20,"restored production SAFE with settled bus filter")
            hmi.command("CLEAR"); hmi.fail_safe_stop()
            wait_status(hmi,lambda s:s.get("bp_bad")==0 and s.get("bp_bad_cnt")==0,8,"clean UART after restore")
            if report["final_status"].get("hmi_arm_profile")!="hv":
                raise RuntimeError("Production HMI profile not restored")
            (out/"wifi_logs.txt").write_text(get_wifi_logs(hmi,token),encoding="utf-8")
        except Exception as exc:
            report["restore_error"]=str(exc); report["restored"]=False
        report["pass"]=report["pass"] and report["restored"] and "profile_restore_error" not in report
        hmi.close()
        (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:str(report[k])[:350] if isinstance(report.get(k),str) else report.get(k)
                     for k in ("pass","restored","error","restore_error","profile_restore_error")},indent=2))
    return 0 if report["pass"] else 1


if __name__=="__main__":
    raise SystemExit(main())
