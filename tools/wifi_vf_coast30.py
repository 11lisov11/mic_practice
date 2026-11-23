"""Prepare/observe/execute one bounded 50 Hz coast test over Wi-Fi; never flash a board."""
import argparse
import json
from pathlib import Path
import time

from collect_wifi_telemetry import read_token
from run_wifi_nucleo_pwm_bench import WifiHmi,wait_status
from verify_wifi_command_path import get_wifi_logs
from web_hmi_command_guard_selftest import load_server_module
from wifi_bench_scenarios import operator_keepalive,outputs_off
from wifi_uart_v3_trial import expected_undervoltage,finalize_trial


def profile_identity(s):
    return (s.get("fw_build"),s.get("mc_fw_build"))==(2026101008,2026101006) and all(
        s.get(k)==v for k,v in dict(hmi_powered_trial_profile="vf_30s_50hz_coast",
            hmi_powered_trial_enabled=1,hmi_powered_trial_max_run_s=33,
            hmi_powered_trial_stop_after_s=30,hmi_powered_trial_max_freq_hz=50).items())


def monitor_coast(h,heartbeat,rep,mod,request_started,acknowledged_at,
                  clock=time.monotonic,sleep=time.sleep):
    seen_active=False
    while clock()-acknowledged_at<34:
        s=h.status();elapsed=clock()-acknowledged_at
        rep["samples"].append(dict(phase="run",elapsed_since_ack_s=elapsed,status=s))
        ok,reason=mod.PoweredTrialGate.live_check(s,pair=mod.UART_V3_SENDER_TRIAL_PAIR,
            profile=mod.COAST30_PROFILE,allow_stopped_zero=True)
        if not profile_identity(s) or not ok or heartbeat["errors"]:
            rep["abort_status"]=s
            raise RuntimeError("coast trial health failed: "+reason)
        if outputs_off(s):
            if not seen_active or elapsed<28.5:raise RuntimeError("unexpected early coast stop")
            rep["observed_stop_since_ack_s"]=elapsed
            rep["observed_stop_since_request_s"]=clock()-request_started
            rep["stop_kind"]="PWM_off_coast"
            return True
        if s.get("state")!="VF_RUN" or s.get("pwm")!=1 or not int(s.get("bp_status",0))&0x20:
            raise RuntimeError("inconsistent active coast state")
        seen_active=True;sleep(.25)
    raise RuntimeError("coast STOP not observed; operator must cut power")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase",choices=("prepare","observe","run","cancel"))
    p.add_argument("--qualification",type=Path)
    p.add_argument("--token-file",type=Path,required=True)
    p.add_argument("--outdir",type=Path,required=True)
    p.add_argument("--confirm-autonomous-ready",action="store_true")
    p.add_argument("--ack-undervoltage",action="store_true")
    a=p.parse_args()
    if a.phase=="run" and not a.confirm_autonomous_ready:p.error("attended secured stand with ALL PC wires removed required")
    if a.phase=="prepare" and a.qualification is None:p.error("retained coast qualification required")
    out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    mod=load_server_module(Path(__file__).resolve().parents[1])
    rep=dict(pass_=False,phase=a.phase,commands=[],samples=[],nominal_run_s=30,
             backup_runlimit_s=33,target_frequency_hz=50,stop_mode="coast",
             measured_rotor_speed_available=False,current_telemetry_qualified=False,general_hv_release=False)
    h=WifiHmi("http://192.168.1.138:8080",read_token(str(a.token_file)),rep["commands"],via_wsl=False)
    try:
        rep["before"]=s=h.status()
        if a.phase=="prepare":
            proof=json.loads(a.qualification.read_text())
            if (s.get("fw_build"),s.get("mc_fw_build"))!=mod.UART_V3_SENDER_TRIAL_PAIR or not outputs_off(s):
                raise RuntimeError("exact stopped pair required")
            if any(not 0<=s[k]<=2 for k in ("vdc","bp_vdc")):raise RuntimeError("discharged bus required")
            if not mod.validate_powered_trial_qualification(proof)[0] or proof.get("profile")!=mod.COAST30_PROFILE:
                raise RuntimeError("invalid coast proof")
            h.command("MODE VF");h.command("SET FREQ 50")
            h.post("/api/powered-trial",dict(action="prepare",confirm="PREPARE UARTV3 COAST30 50HZ",
                                           qualification=proof),"prepare coast30, NOT START")
            rep["pass_"]=profile_identity(h.status())
        elif a.phase=="cancel":
            h.post("/api/powered-trial",dict(action="cancel"),"cancel coast and STOP")
            rep["pass_"]=outputs_off(h.status())
        else:
            if not profile_identity(s):raise RuntimeError("coast profile is not prepared")
            with operator_keepalive(h) as heartbeat:
                if a.ack_undervoltage and expected_undervoltage(s):h.command("CLEAR")
                began=time.monotonic()
                while True:
                    s=h.status();rep["samples"].append(dict(phase="idle",status=s))
                    if not profile_identity(s) or not outputs_off(s) or heartbeat["errors"]:
                        raise RuntimeError("powered idle state/heartbeat failed")
                    if s.get("hmi_powered_trial_ready")==1:break
                    if s.get("hmi_powered_trial_remaining_s",0)<=0 or time.monotonic()-began>=45:
                        raise RuntimeError("powered idle not ready: "+str(s.get("hmi_powered_trial_reason")))
                    time.sleep(.5)
                if a.phase=="observe":rep["pass_"]=True
                else:
                    ok,reason=mod.PoweredTrialGate.live_check(s,idle=True,pair=mod.UART_V3_SENDER_TRIAL_PAIR,
                                                           profile=mod.COAST30_PROFILE)
                    if not ok:raise RuntimeError(reason)
                    h.post("/api/hv-arm",dict(action="arm",confirm="ARM UARTV3 COAST30 50HZ"),"one-shot coast ARM")
                    began=time.monotonic()
                    rep["start_response"]=h.post("/api/start-sequence",dict(runlimit_s=33),"single coast30 START")
                    acknowledged_at=time.monotonic();rep["start_request_elapsed_s"]=acknowledged_at-began
                    rep["pass_"]=monitor_coast(h,heartbeat,rep,mod,began,acknowledged_at)
                    h.post("/api/stop-sequence",dict(emergency=False),"coast STOP confirmation")
                    rep["after_stop"]=wait_status(h,outputs_off,3,"coast outputs off")
                rep["heartbeat"]=heartbeat
    except Exception as e:rep["error"]=f"{type(e).__name__}: {e}"
    finally:
        if a.phase=="run":
            finalize_trial(h,rep)
            if not rep["pass_"]:print("Coast trial failed: operator cut power; do not repeat START",flush=True)
        try:(out/"wifi_logs.txt").write_text(get_wifi_logs(h,h.token),encoding="utf-8")
        except Exception as e:rep["log_error"]=str(e)
        h.close();rep["pass"]=rep.pop("pass_")
        (out/"report.json").write_text(json.dumps(rep,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:rep.get(k) for k in ("pass","phase","error","observed_stop_since_ack_s","final_stop")}))
    return 0 if rep["pass"] else 1


if __name__=="__main__":raise SystemExit(main())
