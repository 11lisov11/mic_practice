"""Wi-Fi PWM qualification on a zero-bus v3 fixture; always restore both peers."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import time

from collect_wifi_telemetry import read_token
from run_mcsdk_logic_bench import PROGRAMMER, SERIAL, compare_code_sections, waveform, off_tail, parse_registers
from run_wifi_nucleo_pwm_bench import WifiHmi, wait_status, run_logged, sha256, capture, analyze_static
from verify_wifi_command_path import get_wifi_logs
from wifi_bench_scenarios import operator_keepalive, outputs_off


DEVICE = "A7D1BB81883C0092"
PRODUCTION = (2026101007, 2026101006)
FIXTURE = (2026101100, 2026101099)


def basic(s, pair):
    if (s.get("fw_build"), s.get("mc_fw_build")) != pair:
        raise RuntimeError("unexpected firmware pair")
    for k in ("vdc", "bp_vdc"):
        value = float(s.get(k, math.nan))
        if not math.isfinite(value) or not 0 <= value <= 2:
            raise RuntimeError("zero-bus interlock failed")
    if not 0 <= s.get("bp_vbus_raw", 999) <= 20:
        raise RuntimeError("raw bus above fixture window")
    for k in ("mc_age_ms", "bp_vbus_age_ms", "bp_temp_age_ms"):
        age = float(s.get(k, math.nan))
        if not math.isfinite(age) or not 0 <= age < 300:
            raise RuntimeError("stale telemetry: " + k)
    if s.get("mc_diag_valid") != 1 or s.get("bp_vbus_valid") != 1 or s.get("bp_temp_valid") != 1:
        raise RuntimeError("invalid measurement/diagnostic contract")
    if any(s.get(k) != 0 for k in ("precharge", "pfc", "brake", "bp_ext", "uno_tx_short_writes")):
        raise RuntimeError("service output or short UART write")


def clean_transport(s, reply_baseline):
    return (s.get("mc_bad_cnt") == 0 and s.get("mc_uart_error_flags") == 0
            and s.get("mc_last_uart_error_flags") == 0 and s.get("bp_transport_fault") == 0
            and all(s.get(k) == reply_baseline[k] for k in reply_baseline))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-isolated", action="store_true")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--direct-wifi", action="store_true",
                        help="Use host LAN HTTP directly, without WSL or USB forwarding")
    parser.add_argument("--reuse-passed", type=Path,
                        help="Reuse only passed timing/stop subchecks of identical image hashes")
    args = parser.parse_args()
    if not args.confirm_isolated:
        parser.error("J1 and U/V/W disconnected, J4/mains off, discharged bus required")
    root = Path(__file__).resolve().parents[1]
    prod = root / "artifacts/live_bench_20261010/uart_v3_candidate/firmware_r6"
    fixture = args.fixture.resolve(strict=True)
    out = args.outdir.resolve(); out.mkdir(parents=True, exist_ok=False)
    logs = out / "logs"; logs.mkdir()
    nb = "ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin"
    pb = prod / "nucleo/STM32CubeIDE/Debug"
    fb = fixture / "nucleo/project/STM32CubeIDE/Debug"
    pu = prod / "uno_build/UNOQ_MOTOR.ino.elf-zsk.bin"
    fu = fixture / "uno_build/UNOQ_MOTOR.ino.elf-zsk.bin"
    if sha256(pb / nb) != "20530ef90893b8cdb074739e3b8fd02d0bb0c478016ab291e036192c4a784479":
        raise RuntimeError("wrong restoration Nucleo image")
    if sha256(pu) != "b521f692621f9374338b59805d0f0a233e086dfe802c6f9ec28e768b8e4a1e9b":
        raise RuntimeError("wrong restoration Uno image")
    for build, name in ((fixture / "uno_build", "unoq_mcsdk_scalar.build-manifest.json"),
                        (fb, "ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json")):
        manifest = json.loads((build / name).read_text(encoding="utf-8-sig"))
        for e in manifest["artifacts"]:
            if sha256(build / e["file"]) != e["sha256"].lower():
                raise RuntimeError("fixture artifact mismatch")
    rep = {"pass": False, "commands": [], "cases": {}, "restored": False,
           "hv_release_approved": False, "scope": "isolated zero-bus clone: actual timing, not powered motor qualification",
           "images": {"production_uno": sha256(pu), "production_nucleo": sha256(pb / nb),
                      "fixture_uno": sha256(fu), "fixture_nucleo": sha256(fb / nb)}}
    if args.reuse_passed:
        previous = json.loads(args.reuse_passed.read_text())
        if previous.get("images") != rep["images"]:
            raise RuntimeError("reuse requires identical fixture and production images")
        for name in ("carrier_5", "carrier_20", "STOP", "ESTOP", "FREQ_ZERO", "RUNLIMIT"):
            old = previous.get("cases", {}).get(name, {})
            if old.get("pass") is True:
                rep["cases"][name] = dict(old, evidence_reuse={
                    "report": str(args.reuse_passed.resolve()), "sha256": sha256(args.reuse_passed),
                    "previous_overall_pass": previous.get("pass"), "scope": "passed image-matched subcheck only"})
    rep["control_transport"] = "direct_wifi_http" if args.direct_wifi else "wsl_nat_wifi_http"
    h = WifiHmi("http://192.168.1.138:8080", read_token(args.token_file), rep["commands"],
                via_wsl=not args.direct_wifi)
    changed = False
    reply_baseline = {}

    def cli(extra, name, reset=False):
        run_logged([PROGRAMMER, "-c", "port=SWD", "sn=" + SERIAL,
                    "mode=" + ("UR" if reset else "HOTPLUG"),
                    *(["reset=HWrst"] if reset else []), *extra], logs / (name + ".log"), 90)

    def program_nuc(binary, name):
        cli(["-w", str(binary), "0x08000000", "-v", "-rst"], name, True)
        rb = out / (name + "_readback.bin")
        cli(["-u", "0x08000000", str(binary.stat().st_size), str(rb)], name + "_readback")
        if rb.read_bytes() != binary.read_bytes():
            raise RuntimeError("Nucleo byte verification failed")
        rep[name + "_byte_verified"] = True

    def program_uno(image, name):
        upload = ["arduino-cli", "upload", "-p", "COM10", "-b", "arduino:zephyr:unoq", "-i", str(image),
                  "--upload-property", "upload.artifacts.sketch=" + str(image),
                  "--upload-property", "upload.port.properties.serialNumber=3880458060"]
        run_logged(upload + ["--upload-property", "build.variant.path=" + str(root / "tools"),
                            "--upload-property", "openocd_cfg=flash_verify_unoq_sketch.cfg"],
                   logs / (name + ".log"), 180)
        rep[name + "_byte_verified"] = True

    def boundary(pair, name):
        s = wait_status(h, lambda x: (x.get("fw_build"), x.get("mc_fw_build")) == pair
                        and outputs_off(x), 45, name + " pair available")
        history = []
        for _ in range(6):
            s = h.status(); basic(s, pair); history.append(s); time.sleep(.2)
        rep[name + "_history"] = history
        if len({x["mc_bad_cnt"] for x in history}) != 1:
            raise RuntimeError("programming-boundary errors still increasing")
        if s.get("mc_uart_error_flags") != 0 or s.get("mc_last_uart_error_flags") != 0:
            raise RuntimeError("hardware UART error at programming boundary; not waived")
        if s.get("mc_last_bad_reason") not in (0, 1, 2, 13):
            raise RuntimeError("not an expected stopped protocol cutover")
        # Preserve, rather than reset, Uno's reply-history counters across Nucleo reset.
        nonlocal reply_baseline
        reply_baseline = {k: s[k] for k in ("mc_bad_integrity", "mc_bad_sequence")}
        if s["mc_bad_cnt"] or s.get("bp_transport_fault") or s.get("estop"):
            h.command("CLEAR"); time.sleep(.7)
        s = h.status(); basic(s, pair)
        if not clean_transport(s, reply_baseline):
            raise RuntimeError("boundary ACK failed")
        return s

    def clean():
        s = h.status(); basic(s, FIXTURE)
        if not outputs_off(s) or not clean_transport(s, reply_baseline):
            raise RuntimeError("unclean stopped fixture; no automatic error ACK")
        h.command("CLEAR")
        s = wait_status(h, lambda x: x.get("bp_fault") == 0 and x.get("estop") == 0
                        and outputs_off(x), 5, "fixture CLEAR")
        basic(s, FIXTURE)
        if not clean_transport(s, reply_baseline): raise RuntimeError("CLEAR changed UART history")

    def arm(freq):
        clean(); h.command("MODE VF"); h.command("SET FREQ " + str(freq))
        h.post("/api/hv-arm", {"action": "arm", "confirm": "ARM LV HV OFF"}, "isolated ARM")

    def start(limit=3):
        h.post("/api/start-sequence", {"runlimit_s": limit}, "bounded Wi-Fi START")
        s = wait_status(h, lambda x: x.get("pwm") == 1 and int(x.get("bp_status", 0)) & 0x20,
                        2, "physical fixture RUN")
        basic(s, FIXTURE)
        if not clean_transport(s, reply_baseline): raise RuntimeError("active UART fault")
        return s

    try:
        s = h.status(); basic(s, PRODUCTION); rep["before"] = s
        reply_baseline = {k: s[k] for k in ("mc_bad_integrity", "mc_bad_sequence")}
        if not outputs_off(s) or s.get("hmi_hv_armed") != 0 or not clean_transport(s, reply_baseline):
            raise RuntimeError("unsafe production baseline")
        rep["code_equivalence"] = compare_code_sections(pb, fb, out / "code_equivalence")
        if not rep["code_equivalence"]["pass"]: raise RuntimeError("PWM/break code differs")
        from saleae import automation
        with automation.Manager.connect(port=10430, connect_timeout_seconds=5) as manager:
            if not any(d.device_id == DEVICE and not d.is_simulation for d in manager.get_devices()):
                raise RuntimeError("physical analyzer absent")
            # Drain the previous acquisition before trusting the idle gate.
            first = capture(manager, DEVICE, out / "idle_drain", .06, 4_000_000)
            rep["idle_drain"] = analyze_static(first, sample_rate_hz=4_000_000)
            csv = capture(manager, DEVICE, out / "idle_before", .12, 4_000_000)
            rep["idle_before"] = analyze_static(csv, sample_rate_hz=4_000_000)
            if not rep["idle_before"]["pass"]: raise RuntimeError("outputs not LOW")
            changed = True
            program_nuc(fb / nb, "install_fixture_nucleo")
            program_uno(fu, "install_fixture_uno")
            boundary(FIXTURE, "fixture_boundary")
            clean()
            h.post("/api/arm-profile", {"profile": "lv"}, "select zero-bus LV profile")
            with operator_keepalive(h) as keepalive:
                for freq in (5, 20):
                    if rep["cases"].get(f"carrier_{freq}", {}).get("pass") is True: continue
                    arm(freq); rep["cases"][f"carrier_{freq}"] = {"commanded_frequency_hz": freq,
                        "electrical_frequency_independently_validated": False}
                    try:
                        rep["cases"][f"carrier_{freq}"]["active_status"] = start()
                        csv = capture(manager, DEVICE, out / f"carrier_{freq}", .10, 12_000_000)
                    finally:
                        h.fail_safe_stop()
                    # Established steady-state measurement rule: quarantine the
                    # acquisition prefix, but still require no raw overlap.
                    result = waveform(csv, 12_000_000, 16000, 1.35e-6, settled=True)
                    rep["cases"][f"carrier_{freq}"].update(result)
                    if not result["pass"]: raise RuntimeError("carrier/deadtime failed")
                for label in ("STOP", "ESTOP", "FREQ_ZERO", "RUNLIMIT", "ACTIVE_RPC", "TIM1_BREAK"):
                    if rep["cases"].get(label, {}).get("pass") is True: continue
                    arm(5)
                    folder = out / label; folder.mkdir()
                    entry = {"pass": False}; rep["cases"][label] = entry
                    drain = capture(manager, DEVICE, out / (label + "_idle_drain"), .06, 4_000_000)
                    entry["idle_drain"] = analyze_static(drain, sample_rate_hz=4_000_000)
                    idle = capture(manager, DEVICE, out / (label + "_idle_flush"), .06, 4_000_000)
                    entry["idle_flush"] = analyze_static(idle, sample_rate_hz=4_000_000)
                    if not entry["idle_flush"]["pass"]: raise RuntimeError("pre-START outputs not LOW")
                    try:
                        with manager.start_capture(device_id=DEVICE,
                            device_configuration=automation.LogicDeviceConfiguration(
                                enabled_digital_channels=list(range(7)), digital_sample_rate=4_000_000),
                            capture_configuration=automation.CaptureConfiguration(
                                capture_mode=automation.TimedCaptureMode(duration_seconds=6 if label == "ACTIVE_RPC" else 3.5))) as session:
                            time.sleep(.2); entry["active_status"] = start(.8 if label == "RUNLIMIT" else 3)
                            time.sleep(.3)
                            if label in ("STOP", "ESTOP"):
                                h.post("/api/stop-sequence", {"emergency": label == "ESTOP"}, label)
                            elif label == "FREQ_ZERO": h.command("SET FREQ 0")
                            elif label == "ACTIVE_RPC":
                                entry["active_samples"] = []
                                for target in (10, 20):
                                    h.command("SET FREQ " + str(target)); x = h.status(); basic(x, FIXTURE)
                                    if x.get("pwm") != 1 or not clean_transport(x, reply_baseline):
                                        raise RuntimeError("active RPC integrity or premature stop")
                                    entry["active_samples"].append(x)
                                h.fail_safe_stop()
                            elif label == "TIM1_BREAK":
                                cli(["-w32", "0x40012c14", "0x80", "-nv"], "software_TIM1_break")
                                entry["scope"] = "software TIM1 BG event, NOT physical PA6 or IPM fault stimulus"
                            entry["off_status"] = wait_status(h, outputs_off, 3, label + " stopped")
                            session.wait(); session.save_capture(str(folder / "capture.sal"))
                            session.export_raw_data_csv(directory=str(folder / "csv"), digital_channels=list(range(7)))
                    finally: h.fail_safe_stop()
                    csv = folder / "csv/digital.csv"
                    entry["waveform"] = waveform(csv, 4_000_000, 16000, 1.35e-6, settled=False)
                    entry["off_tail"] = off_tail(csv, 4_000_000)
                    entry["pass"] = entry["waveform"]["pass"] and entry["off_tail"]["pass"]
                    if not clean_transport(entry["off_status"], reply_baseline): entry["pass"] = False
                    if not entry["pass"]: raise RuntimeError("captured transition failed: " + label)
                    if label == "TIM1_BREAK":
                        code, payload = h.request("POST", "/api/start-sequence", {"runlimit_s": 1})
                        entry["restart_without_ack"] = {"http_status": code, "ok": payload.get("ok")}
                        if code == 200 or payload.get("ok") is True: raise RuntimeError("fault allowed restart")
                rep["operator_keepalive"] = keepalive
                if keepalive["errors"]: raise RuntimeError("operator heartbeat failed")
            rep["pass"] = all(x["pass"] for x in rep["cases"].values())
    except Exception as exc:
        rep["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if changed:
            try:
                h.fail_safe_stop()
                # Only our captured stop/software-break fault is acknowledged here;
                # an unexpected transport fault must not be cleared for a profile switch.
                s = h.status()
                if (s.get("fw_build"), s.get("mc_fw_build")) == FIXTURE and outputs_off(s) and clean_transport(s, reply_baseline):
                    h.command("CLEAR"); time.sleep(.5)
                    h.post("/api/arm-profile", {"profile": "hv"}, "restore disarmed HV profile")
            except Exception as exc:
                rep["profile_restore_error"] = f"{type(exc).__name__}: {exc}"
            # Flash restoration must never depend on RPC/status availability.
            try:
                program_nuc(pb / nb, "restore_nucleo")
                program_uno(pu, "restore_uno")
                s = boundary(PRODUCTION, "production_boundary")
                rep["final"] = s
                rep["restored"] = outputs_off(s) and s.get("hmi_arm_profile") == "hv"
                (out / "wifi_logs.txt").write_text(get_wifi_logs(h, h.token), encoding="utf-8")
            except Exception as exc:
                rep["restore_error"] = f"{type(exc).__name__}: {exc}"
        else: rep["restored"] = True
        rep["pass"] = rep["pass"] and rep["restored"]
        h.close(); (out / "report.json").write_text(json.dumps(rep, indent=2) + "\n")
    print(json.dumps({"pass": rep["pass"], "restored": rep["restored"], "error": rep.get("error"),
                      "restore_error": rep.get("restore_error"), "cases": {k: v.get("pass") for k, v in rep["cases"].items()}}, indent=2))
    return 0 if rep["pass"] else 1


if __name__ == "__main__": raise SystemExit(main())
