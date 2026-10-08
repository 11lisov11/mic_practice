"""Test the loaded logic-only MCSDK image with both board USB data links absent."""
from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
import subprocess
import sys
import time

from prepare_mcsdk_logic_bench import BENCH_BUILD
from run_mcsdk_logic_bench import PROGRAMMER, SERIAL, DEVICE, waveform, off_tail
from run_wifi_nucleo_pwm_bench import WifiHmi, capture, analyze_static, wait_status, run_logged
from verify_wifi_command_path import get_wifi_logs
from wifi_bench_scenarios import operator_keepalive, outputs_off


def usb_inventory():
    st=subprocess.run([PROGRAMMER,"-l","stlink"],capture_output=True,text=True,timeout=10)
    adb=subprocess.run(["adb","devices","-l"],capture_output=True,text=True,timeout=10)
    if st.returncode or adb.returncode:
        raise RuntimeError("Cannot independently verify board USB absence")
    return {"nucleo_STLink_present":SERIAL in st.stdout,
            "UNO_Q_ADB_present":any(line.split() and line.split()[0]=="3880458060" for line in adb.stdout.splitlines()),
            "stlink_listing":st.stdout,"adb_listing":adb.stdout}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase",choices=("test","restore"),required=True)
    parser.add_argument("--outdir",type=Path,required=True)
    parser.add_argument("--confirm-isolated-zero-bus",action="store_true")
    parser.add_argument("--token-interactive",action="store_true",help="Read a credential with terminal echo disabled")
    args=parser.parse_args()
    if not args.confirm_isolated_zero_bus:
        parser.error("Disconnected mains/J1, J4 and motor; measured zero bus required")
    token=(getpass.getpass("Control credential (not echoed): ") if args.token_interactive else sys.stdin.readline()).strip()
    if len(token)<16: raise RuntimeError("Control token required on stdin; never in arguments or logs")
    out=args.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    hmi=WifiHmi("http://192.168.1.138:8080",token,[],via_wsl=True)
    report={"pass":False,"phase":args.phase,"commands":hmi.commands,
            "scope":"Wi-Fi only motor commands, physical Saleae, isolated logic-only fixture",
            "hardware_validated":False,"production_restore_required":True}
    rate=24_000_000

    def clean():
        hmi.fail_safe_stop()
        wait_status(hmi,lambda s:outputs_off(s) and s.get("mc_fw_build")==BENCH_BUILD and
                    s.get("bp_softstart_ready")==1 and float(s.get("vdc",999))<=2,
                    15,"autonomous fixture settled")
        hmi.command("CLEAR")
        return wait_status(hmi,lambda s:outputs_off(s) and s.get("bp_fault")==0 and
                           s.get("bp_bad_cnt")==0 and s.get("bp_bad")==0 and s.get("estop")==0,
                           8,"autonomous clean SAFE")

    try:
        report["before"]=wait_status(hmi,lambda s:True,20,"Wi-Fi RPC available")
        if report["before"].get("state")!="SAFE" or not outputs_off(report["before"]) or report["before"].get("hmi_hv_armed")!=0:
            raise RuntimeError("Expected disarmed SAFE before the test")
        if args.phase=="restore":
            if report["before"].get("mc_fw_build")==BENCH_BUILD:
                clean()
                hmi.post("/api/arm-profile",{"profile":"hv"},"restore production profile")
            root=Path(__file__).resolve().parents[1]
            image=root/"firmware/ready_to_flash/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex"
            run_logged([PROGRAMMER,"-c","port=SWD","mode=UR","reset=HWrst","sn="+SERIAL,
                        "-w",str(image),"-v","-rst"],out/"restore.log",timeout=60)
            readback=out/"readback.bin"
            binary=image.with_suffix(".bin")
            run_logged([PROGRAMMER,"-c","port=SWD","mode=HOTPLUG","sn="+SERIAL,
                        "-u","0x08000000",str(binary.stat().st_size),str(readback)],out/"readback.log")
            report["flash_matches_production"]=readback.read_bytes()==binary.read_bytes()
            run_logged([PROGRAMMER,"-c","port=SWD","mode=HOTPLUG","sn="+SERIAL,"-rst"],out/"reset.log")
            report["after"]=wait_status(hmi,lambda s:s.get("mc_fw_build")==2026100601 and outputs_off(s)
                                       and float(s.get("vdc",999))<=2,20,"restored production")
            hmi.command("CLEAR"); hmi.fail_safe_stop()
            report["pass"]=report["flash_matches_production"] and report["after"].get("hmi_arm_profile")=="hv"
            report["production_restore_required"]=not report["pass"]
        else:
            from saleae import automation
            report["usb_before"]=usb_inventory()
            if report["usb_before"]["nucleo_STLink_present"] or report["usb_before"]["UNO_Q_ADB_present"]:
                raise RuntimeError("Both board USB data links must be removed before autonomous START")
            if report["before"].get("mc_fw_build")!=BENCH_BUILD:
                raise RuntimeError("Validated logic-only MCSDK fixture is not loaded")
            clean()
            hmi.post("/api/arm-profile",{"profile":"lv"},"autonomous LV profile")
            with automation.Manager.connect(port=10430) as manager, operator_keepalive(hmi) as keepalive:
                if not any(d.device_id==DEVICE and not d.is_simulation for d in manager.get_devices()):
                    raise RuntimeError("Physical analyzer missing")
                for frequency,delay in ((5,6),(20,12)):
                    clean()
                    hmi.post("/api/hv-arm",{"action":"arm","confirm":"ARM LV HV OFF"},"autonomous ARM")
                    hmi.command("MODE VF");hmi.command("SET FREQ 5")
                    hmi.command("START");hmi.command("SET RUNLIMIT 14")
                    wait_status(hmi,lambda s:s.get("pwm")==1 and int(s.get("bp_status",0))&0x20,3,"autonomous MCSDK RUN")
                    if frequency==20: hmi.command("SET FREQ 20")
                    time.sleep(delay)
                    csv=capture(manager,DEVICE,out/f"PWM_{frequency}",.12,rate)
                    result=waveform(csv,rate,16000,1.35e-6)
                    result["status"]=hmi.status()
                    report[f"pwm_{frequency}hz"]=result
                    if not result["pass"]: raise RuntimeError("Autonomous PWM waveform failed")
                    hmi.fail_safe_stop();wait_status(hmi,outputs_off,3,"autonomous STOP")
                for cycle,emergency in enumerate((False,True),1):
                    clean()
                    hmi.post("/api/hv-arm",{"action":"arm","confirm":"ARM LV HV OFF"},"autonomous transition ARM")
                    hmi.command("SET FREQ 5")
                    capture(manager,DEVICE,out/f"flush_{cycle}",.1,rate)
                    folder=out/f"transition_{cycle}";folder.mkdir()
                    event_rate=4_000_000
                    with manager.start_capture(device_id=DEVICE,
                            device_configuration=automation.LogicDeviceConfiguration(
                                enabled_digital_channels=list(range(7)),digital_sample_rate=event_rate),
                            capture_configuration=automation.CaptureConfiguration(
                                capture_mode=automation.TimedCaptureMode(duration_seconds=2.6))) as session:
                        time.sleep(.35);hmi.command("START")
                        wait_status(hmi,lambda s:s.get("pwm")==1 and int(s.get("bp_status",0))&0x20,2,"autonomous transition RUN")
                        time.sleep(.4)
                        hmi.post("/api/stop-sequence",{"emergency":emergency},"autonomous ESTOP" if emergency else "autonomous STOP")
                        wait_status(hmi,outputs_off,3,"autonomous transition off")
                        session.wait();session.save_capture(str(folder/"capture.sal"))
                        session.export_raw_data_csv(directory=str(folder/"csv"),digital_channels=list(range(7)))
                    csv=folder/"csv/digital.csv"
                    result=waveform(csv,event_rate,16000,1.35e-6,settled=False)
                    result["off_tail"]=off_tail(csv,event_rate)
                    result["pass"]=result["pass"] and result["off_tail"]["pass"]
                    report[f"transition_{cycle}"]=result
                    if not result["pass"]: raise RuntimeError("Autonomous continuous transition failed")
                report["stopped_waveform"]=analyze_static(capture(manager,DEVICE,out/"stopped",.1,rate),
                                                        settle_s=.002,sample_rate_hz=rate)
                report["keepalive"]=keepalive
            report["usb_after"]=usb_inventory()
            report["pass"]=all(report[k]["pass"] for k in ("pwm_5hz","pwm_20hz","transition_1","transition_2","stopped_waveform"))
            report["pass"]=report["pass"] and not any(report["usb_after"][k] for k in ("nucleo_STLink_present","UNO_Q_ADB_present"))
    except Exception as exc:
        report["error"]=f"{type(exc).__name__}: {exc}"
    finally:
        code,response=hmi.fail_safe_stop()
        report["final_stop"]={"http":code,"ok":response.get("ok")}
        try:
            report["after_final_stop"]=hmi.status()
        except Exception as exc:
            report["final_status_error"]=f"{type(exc).__name__}: {exc}"
            report["pass"]=False
        report["pass"]=report["pass"] and code==200 and response.get("ok") is True and outputs_off(report["after_final_stop"])
        try:
            (out/"wifi_logs.txt").write_text(get_wifi_logs(hmi,token),encoding="utf-8")
        except Exception as exc:
            report["log_error"]=str(exc);report["pass"]=False
        hmi.close();token=""
        (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:str(report[k])[:300] if isinstance(report.get(k),str) else report.get(k)
                      for k in ("pass","phase","production_restore_required","error")},indent=2),flush=True)
    return 0 if report["pass"] else 1


if __name__=="__main__":
    raise SystemExit(main())
