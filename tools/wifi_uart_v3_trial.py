"""Separate prepare, powered-idle observation and one authorized Wi-Fi V/f trial."""
import argparse
import json
import math
from pathlib import Path
import time

from collect_wifi_telemetry import read_token
from run_wifi_nucleo_pwm_bench import WifiHmi, wait_status
from verify_wifi_command_path import get_wifi_logs
from wifi_bench_scenarios import operator_keepalive, outputs_off


PAIR = (2026101007, 2026101006)
SENDER_PAIR = (2026101008, 2026101006)
STOP_OBSERVATION_WINDOW_S = 4.0


def expected_undervoltage(s):
    return ((s.get("fw_build"), s.get("mc_fw_build")) in (PAIR, SENDER_PAIR) and outputs_off(s)
        and s.get("bp_fault") == 5 and s.get("mc_fault_reason") == 8
        and s.get("mc_fault_current_mask") == 4 and s.get("mc_fault_occurred_mask") == 4
        and all(s.get(k) == 0 for k in ("mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence",
            "mc_uart_error_flags", "mc_last_uart_error_flags", "uno_tx_short_writes", "bp_transport_fault")))


def active_clean(s, allow_stopped_zero=False):
    try:
        return ((s.get("fw_build"), s.get("mc_fw_build")) in (PAIR, SENDER_PAIR)
            and s.get("hmi_vbus_hv_calibrated") == 1 and s.get("estop") == 0
            and s.get("bp_fault") == 0 and s.get("bp_temp_valid") == 1 and s.get("bp_temp_fault") == 0
            and s.get("mode") == "VF" and (0 < float(s["freq_cmd"]) <= 10
                or (allow_stopped_zero and float(s["freq_cmd"]) == 0 and outputs_off(s)))
            and all(math.isfinite(float(s[k])) and 250 <= float(s[k]) <= 360 for k in ("vdc", "bp_vdc"))
            and all(math.isfinite(float(s[k])) and 0 <= float(s[k]) < 300
                    for k in ("mc_age_ms", "bp_age_ms", "bp_vbus_age_ms", "bp_temp_age_ms"))
            and all(s.get(k) == 0 for k in ("mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence",
                "mc_uart_error_flags", "mc_last_uart_error_flags", "uno_tx_short_writes", "bp_transport_fault")))
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def expected_trial_stop(elapsed_s, seen_active, s):
    return math.isfinite(elapsed_s) and 2.5 <= elapsed_s <= 12 and seen_active and outputs_off(s)


def expected_runlimit_estop(elapsed_since_ack, seen_active, s):
    """Recognize the pinned timer's terminal signature, not a uniquely proven cause.

    Never clears the latch or changes live HMI guards. This classification is
    only for one bounded test after clean RUN samples, near its known deadline.
    """
    if (not math.isfinite(elapsed_since_ack) or not 2.5 <= elapsed_since_ack <= 4.5
            or not seen_active or (s.get("fw_build"), s.get("mc_fw_build")) != SENDER_PAIR
            or not outputs_off(s) or s.get("freq_cmd") != 0):
        return False
    expected = dict(estop=1, bp_fault=1, bp_status=13, mc_fault_reason=4,
        mc_diag_valid=1, mc_fault_current_mask=0, mc_fault_occurred_mask=0,
        mc_last_bad_reason=0, hmi_powered_trial_used=1,
        precharge=0, pfc=0, brake=0, bp_ext=0)
    if any(type(s.get(k)) is not int or s[k] != v for k, v in expected.items()):
        return False
    # Check every other transport/measurement condition against an ephemeral
    # view. Retain the actual ESTOP and fault unchanged in samples and reports.
    return active_clean(dict(s, estop=0, bp_fault=0), allow_stopped_zero=True)


def observe_trial_stop(h, heartbeat, rep, request_started, acknowledged_at,
                       clock=time.monotonic, sleep=time.sleep):
    # This is only a readback window. MCU runlimit and the independent HMI
    # deadline remain 3 s; HTTP setup latency must not consume readback time.
    seen_active = False
    deadline = acknowledged_at + STOP_OBSERVATION_WINDOW_S
    while clock() < deadline:
        s = h.status()
        elapsed = clock() - request_started
        rep["samples"].append({"phase": "run", "status": s,
            "elapsed_since_request_s": elapsed,
            "elapsed_since_ack_s": clock() - acknowledged_at})
        if not heartbeat["errors"] and expected_runlimit_estop(clock()-acknowledged_at, seen_active, s):
            rep["observed_stop_elapsed_s"] = elapsed
            rep["observed_stop_since_ack_s"] = clock() - acknowledged_at
            rep["stop_kind"] = "latched_estop_at_configured_runlimit"
            rep["stop_cause_uniquely_verified"] = False
            rep["stop_cause_note"] = "Matches pinned firmware deadline behavior; no unique RUNLIMIT reason field"
            return seen_active
        if not active_clean(s, allow_stopped_zero=True) or heartbeat["errors"]:
            rep["abort_status"] = s
            raise RuntimeError("trial fault/link/bus check failed; see captured first-fault details")
        if s.get("pwm") == 1 and int(s.get("bp_status", 0)) & 0x20:
            seen_active = True
        elif outputs_off(s):
            if not expected_trial_stop(elapsed, seen_active, s):
                raise RuntimeError("unexpected early PWM stop")
            rep["observed_stop_elapsed_s"] = elapsed
            rep["observed_stop_since_ack_s"] = clock() - acknowledged_at
            return seen_active
        else:
            raise RuntimeError("inconsistent output state")
        sleep(.1)
    raise RuntimeError("bounded automatic stop was not observed; operator must cut power")


def finalize_trial(h, rep):
    emergency = not rep["pass_"]
    try:
        code, response = h.request("POST", "/api/stop-sequence", {"emergency": emergency})
        s = h.status()
        confirmed = code == 200 and response.get("ok") is True and outputs_off(s)
        if not confirmed:
            rep["pass_"] = False
            emergency = True
            code, response = h.fail_safe_stop()
            s = h.status()
            confirmed = code == 200 and response.get("ok") is True and outputs_off(s)
        rep["final_status"] = s
        rep["final_stop"] = dict(http=code, ok=response.get("ok") is True,
                                 emergency=emergency, outputs_off_confirmed=confirmed)
        rep["pass_"] = rep["pass_"] and confirmed
    except Exception as exc:
        rep["pass_"] = False
        rep["final_stop_error"] = str(exc)
        try:
            code, response = h.fail_safe_stop()
            rep["emergency_fallback"] = dict(http=code, ok=response.get("ok") is True)
            rep["final_status"] = h.status()
        except Exception as fallback:
            rep["emergency_fallback_error"] = str(fallback)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=("prepare", "observe", "run", "cancel"))
    p.add_argument("--qualification", type=Path)
    p.add_argument("--token-file", type=Path, required=True)
    p.add_argument("--outdir", type=Path, required=True)
    p.add_argument("--confirm-autonomous-ready", action="store_true",
        help="Run only: operator present, motor secured, ALL PC USB/analyzer wires removed")
    p.add_argument("--ack-undervoltage", action="store_true",
        help="Observe/run only: acknowledge one specifically identified idle undervoltage")
    args = p.parse_args()
    if args.phase == "run" and not args.confirm_autonomous_ready:
        p.error("operator-ready confirmation is required for the single powered START")
    if args.phase == "prepare" and not args.qualification:
        p.error("prepare requires retained qualification attestation")
    out = args.outdir.resolve(); out.mkdir(parents=True, exist_ok=False)
    rep = dict(pass_=False, phase=args.phase, commands=[], samples=[], current_telemetry_qualified=False,
        physical_rotation_verified=False, max_run_s=3, requested_frequency_hz=5, general_hv_release=False)
    h = WifiHmi("http://192.168.1.138:8080", read_token(str(args.token_file)), rep["commands"], via_wsl=False)
    try:
        rep["before"] = s = h.status()
        if args.phase == "prepare":
            proof = json.loads(args.qualification.read_text())
            if ((s.get("fw_build"), s.get("mc_fw_build")) != tuple(proof.get("pair", []))
                    or tuple(proof.get("pair", [])) not in (PAIR, SENDER_PAIR) or not outputs_off(s)):
                raise RuntimeError("qualified stopped pair required")
            if any(not 0 <= float(s[k]) <= 2 for k in ("vdc", "bp_vdc")):
                raise RuntimeError("prepare requires discharged bus")
            h.command("MODE VF"); h.command("SET FREQ 5")
            h.post("/api/powered-trial", dict(action="prepare", confirm="PREPARE UARTV3 TRIAL 3S",
                qualification=proof), "prepare bounded trial, NOT START")
            rep["pass_"] = h.status().get("hmi_powered_trial_enabled") == 1
        elif args.phase == "cancel":
            h.post("/api/powered-trial", {"action": "cancel"}, "cancel trial and STOP")
            rep["pass_"] = outputs_off(h.status())
        else:
            if s.get("hmi_powered_trial_enabled") != 1:
                raise RuntimeError("prepare trial on discharged bus first; preparation does not survive HMI restart")
            with operator_keepalive(h) as heartbeat:
                if args.ack_undervoltage and expected_undervoltage(s):
                    h.command("CLEAR")
                began = time.monotonic()
                while True:
                    s = h.status(); rep["samples"].append({"phase": "idle", "status": s})
                    if s.get("hmi_powered_trial_remaining_s") == 0 or s.get("hmi_powered_trial_reason") == "powered trial preparation expired":
                        raise RuntimeError("powered trial preparation expired; no ARM or START sent")
                    if not outputs_off(s) or heartbeat["errors"]:
                        raise RuntimeError("powered idle/output/heartbeat check failed")
                    if s.get("hmi_powered_trial_ready") == 1:
                        break
                    if time.monotonic() - began >= 45:
                        raise RuntimeError("powered idle not qualified: " + str(s.get("hmi_powered_trial_reason")))
                    time.sleep(.5)
                if args.phase == "observe":
                    rep["pass_"] = True
                else:
                    if s.get("freq_cmd") != 5 or not active_clean(s):
                        raise RuntimeError("trial requires unchanged 5-Hz target and clean live telemetry")
                    h.post("/api/hv-arm", dict(action="arm", confirm="ARM UARTV3 TRIAL 3S"), "one-shot trial ARM")
                    began = time.monotonic()
                    response = h.post("/api/start-sequence", {"runlimit_s": 3}, "single bounded START")
                    acknowledged_at = time.monotonic()
                    rep["start_response"] = response
                    rep["start_request_elapsed_s"] = acknowledged_at - began
                    rep["stop_observation_window_s"] = STOP_OBSERVATION_WINDOW_S
                    seen_active = observe_trial_stop(h, heartbeat, rep, began, acknowledged_at)
                    h.post("/api/stop-sequence", {"emergency": False}, "trial STOP")
                    rep["after_stop"] = wait_status(h, outputs_off, 3, "confirmed stopped trial")
                    rep["pass_"] = seen_active
                rep["heartbeat"] = heartbeat
    except Exception as exc:
        rep["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if args.phase == "run":
            finalize_trial(h, rep)
            if not rep["pass_"]:
                print("Trial failed: operator must switch off power; do not repeat START", flush=True)
        try:
            (out/"wifi_logs.txt").write_text(get_wifi_logs(h, h.token), encoding="utf-8")
        except Exception as exc:
            rep["log_error"] = str(exc)
        h.close(); rep["pass"] = rep.pop("pass_")
        (out/"report.json").write_text(json.dumps(rep, indent=2)+"\n")
    print(json.dumps({k: rep.get(k) for k in ("pass", "phase", "error", "final_stop")}))
    return 0 if rep["pass"] else 1


if __name__ == "__main__": raise SystemExit(main())
