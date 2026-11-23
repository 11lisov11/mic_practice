"""Scope retained evidence to one operator-selected 30 s / 50 Hz coast trial; no hardware."""
import argparse
import json
from pathlib import Path

from install_uart_v3_sender_fix import sha
from prepare_uart_v3_sender_trial import sender_qualification
from prepare_vf_30s_profile import plan
from web_hmi_command_guard_selftest import load_server_module
from wifi_uart_v3_trial import active_clean, expected_runlimit_estop


def coast_qualification(root, args):
    proof=sender_qualification(root,args.pwm,args.offline,args.old_idle,args.physical,
                               args.snapshot,args.install,args.idle)
    mod=load_server_module(root)
    native=json.loads(args.native.read_text(encoding="utf-8-sig"))
    if (native.get("pass") is not True or native.get("profile")!=plan(50,"coast")
            or native.get("hardware_commands")!=0 or native.get("hv_release_approved") is not False
            or native.get("regeneration_envelope",{}).get("entered_capacitance_uf")!=args.capacitance_uf
            or native.get("regeneration_envelope",{}).get("applies_to_chosen_stop_mode") is not False
            or not all(native.get("native_ramp",{}).get("checks",{}).values())):
        raise ValueError("native coast-only profile evidence missing")
    for relative,expected in native["native_ramp"]["source_sha256"].items():
        if sha(root/relative)!=expected:raise ValueError("native ramp source changed")
    review=json.loads(args.review.read_text(encoding="utf-8-sig"))
    previous=json.loads(args.previous.read_text(encoding="utf-8-sig"))
    rows=[a for a in previous.get("samples",[]) if a.get("phase")=="run"]
    active=[a for a in rows if a["status"].get("pwm")==1]
    if (review.get("motor_rotation_operator_confirmed") is not True
            or review.get("active_uart_and_bus_health_clean") is not True
            or review.get("active_mcsdk_masks_zero") is not True
            or review.get("stop_cause_uniquely_verified") is not False
            or previous.get("final_stop",{}).get("outputs_off_confirmed") is not True
            or not active or not all(active_clean(a["status"]) for a in active)
            or not rows or not expected_runlimit_estop(rows[-1].get("elapsed_since_ack_s",0),True,rows[-1]["status"])):
        raise ValueError("operator-confirmed clean short-run evidence missing")
    proof.update(schema="mic_ai.powered_trial.coast30.v1",profile=mod.COAST30_PROFILE,
        coast_only=True,native_coast_profile_pass=True,prior_rotation_operator_confirmed=True,
        prior_active_health_clean=True,prior_stop_cause_uniquely_verified=False,
        current_telemetry_qualified=False,dc_capacitance_uf=args.capacitance_uf)
    proof["evidence_sha256"].update(coast_profile=sha(args.native),powered_review=sha(args.review))
    proof["prior_powered_report_sha256"]=sha(args.previous)
    if not mod.validate_powered_trial_qualification(proof)[0]:
        raise ValueError("server rejected scoped coast qualification")
    return proof


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("pwm","offline","old-idle","physical","snapshot","install","idle","native","review","previous","out"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--capacitance-uf",type=float,required=True)
    a=p.parse_args()
    result=coast_qualification(Path(__file__).resolve().parents[1],a)
    with a.out.open("x",encoding="utf-8") as stream:json.dump(result,stream,indent=2);stream.write("\n")
    print(json.dumps(dict(prepared=True,profile=result["profile"],hardware_commands=0,
                         general_hv_release=False,expires_at=result["expires_at"])))


if __name__=="__main__":main()
