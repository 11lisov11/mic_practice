"""Exercise the installed sender over Wi-Fi with discharged bus, never ARM/START."""
import argparse
import json
from pathlib import Path
import time

from collect_wifi_telemetry import read_token
from install_vbus_hmi_fix_remote import precheck
from run_wifi_nucleo_pwm_bench import WifiHmi
from verify_wifi_command_path import get_wifi_logs


def idle_check(s):
    if (s.get("fw_build"), s.get("mc_fw_build")) != (2026101008, 2026101006):
        return False, "wrong sender/controller identity"
    ok, reason = precheck(s, 10)
    if not ok or s.get("hmi_vbus_hv_calibrated") != 1:
        return False, reason if not ok else "saved calibration invalid"
    for k in ("mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence", "mc_uart_error_flags",
              "mc_last_uart_error_flags", "uno_tx_short_writes", "bp_transport_fault"):
        if type(s.get(k)) is not int or s[k] != 0:
            return False, "idle transport error: " + k
    return True, "ok"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--token-file", type=Path, required=True)
    p.add_argument("--outdir", type=Path, required=True)
    args = p.parse_args()
    out = args.outdir.resolve(); out.mkdir(parents=True, exist_ok=False)
    rep = dict(pass_=False, commands=[], samples=[], arm_commands=0, start_commands=0,
               hardware_active_pwm_measured=False, general_hv_release=False)
    h = WifiHmi("http://192.168.1.138:8080", read_token(str(args.token_file)), rep["commands"], via_wsl=False)
    try:
        rep["before"] = s = h.status()
        ok, reason = idle_check(s)
        if not ok:
            raise RuntimeError(reason)
        rep["first_builds"] = {k: s[k] for k in ("fw_build", "mc_fw_build")}
        h.command("MODE VF")
        for freq in (5, 20, 0):
            h.command("SET FREQ " + str(freq))
            time.sleep(.5)
            s = h.status(); rep["samples"].append(s)
            ok, reason = idle_check(s)
            if not ok or s.get("freq_cmd") != freq:
                raise RuntimeError(reason if not ok else "frequency target not acknowledged")
        h.command("STOP")
        began = time.monotonic()
        first = h.status()
        while time.monotonic() - began < 30:
            s = h.status(); rep["samples"].append(s)
            ok, reason = idle_check(s)
            if not ok:
                raise RuntimeError(reason)
            time.sleep(.5)
        rep["after"] = s
        rep["observation_sec"] = time.monotonic() - began
        rep["new_good_frames"] = s["bp_good"] - first["bp_good"]
        if rep["new_good_frames"] < 100:
            raise RuntimeError("too few new UART replies")
        rep["pass_"] = True
    except Exception as exc:
        rep["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            (out / "wifi_logs.txt").write_text(get_wifi_logs(h, h.token), encoding="utf-8")
        except Exception as exc:
            rep["log_error"] = str(exc)
        h.close(); rep["pass"] = rep.pop("pass_")
        (out / "report.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: rep.get(k) for k in ("pass", "new_good_frames", "observation_sec", "error")}))
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
