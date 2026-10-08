"""Qualify isolated logic PWM via Wi-Fi and restore hash-checked production 801."""
import argparse
import json
from pathlib import Path
import subprocess
import time

from install_vbus_hmi_fix_remote import precheck
from package_uart_guard_update import verify_archive
from run_mcsdk_logic_bench import PROGRAMMER, SERIAL, DEVICE, waveform, off_tail, compare_code_sections
from run_wifi_nucleo_pwm_bench import WifiHmi, capture, analyze_static, read_control_token, run_logged, sha256, wait_status
from verify_wifi_command_path import get_wifi_logs
from wifi_bench_scenarios import operator_keepalive, outputs_off

PRODUCTION = 2026100801
FIXTURE = 2026100899
UNO = 2026100802


def verified_images(folder, expected):
    manifests = list(folder.glob("*.build-manifest.json"))
    if len(manifests) != 1:
        raise RuntimeError("One build manifest required")
    m = json.loads(manifests[0].read_text(encoding="utf-8-sig"))
    if (m.get("firmware_build_id") != expected or m.get("build_exit_code") != 0
            or m.get("build_errors") != 0 or m.get("build_warnings") != 0):
        raise RuntimeError("Build identity or compiler qualification mismatch")
    for entry in m["artifacts"]:
        p = folder / entry["file"]
        if p.stat().st_size != entry["bytes"] or sha256(p) != entry["sha256"].lower():
            raise RuntimeError("Image checksum mismatch: " + p.name)
    stem = "ACIM-NUCLEOG431RB-IPM15B-VF_OL"
    return folder / (stem + ".hex"), folder / (stem + ".bin")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-power-off", action="store_true")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--reuse-high-resolution", type=Path)
    parser.add_argument("--uno-build", type=int, choices=(2026100802, 2026100803, 2026100804), default=UNO)
    args = parser.parse_args()
    uno_identity = args.uno_build
    if not args.confirm_power_off:
        parser.error("Operator-confirmed mains/J4 off and isolated zero-bus setup required")
    root = Path(__file__).resolve().parents[1]
    fixture = args.fixture.resolve(strict=True)
    package = args.package.resolve(strict=True)
    verify_archive(package.with_suffix(".zip"))
    prod_hex, prod_bin = verified_images(package / "nucleo", PRODUCTION)
    bench_build = fixture / "project/STM32CubeIDE/Debug"
    bench_hex, bench_bin = verified_images(bench_build, FIXTURE)
    manifest = json.loads((fixture / "fixture_manifest.json").read_text())
    if (manifest.get("pass") is not True or manifest["production_build"] != PRODUCTION
            or manifest["bench_build"] != FIXTURE):
        raise RuntimeError("Wrong fixture provenance")
    interlock = json.loads((fixture.parent / "host_interlock/report.json").read_text())
    if interlock.get("pass") is not True:
        raise RuntimeError("Fixture interlock host test required")
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    logs = out / "logs"
    logs.mkdir()
    commands = []
    h = WifiHmi("http://192.168.1.138:8080", read_control_token(
        "adb", "3880458060", "/home/arduino/.config/mic-ai/control_token"), commands, via_wsl=True)
    report = {"pass": False, "scope": "isolated 899 derived from 801; not energized inverter qualification",
              "production_image_active_pwm_tested": False, "hardware_acceptance": False,
              "updated_uno_decoder_installed": True,
              "uno_build": uno_identity,
              "commands": commands, "cases": {}, "restored": False,
              "images": {"production_hex": sha256(prod_hex), "production_bin": sha256(prod_bin),
                         "fixture_hex": sha256(bench_hex), "fixture_bin": sha256(bench_bin)}}
    modified = False
    if args.reuse_high_resolution:
        prior = json.loads(args.reuse_high_resolution.read_text())
        evidence = prior.get("cases", {}).get("steady_5hz", {})
        if prior.get("images") != report["images"] or evidence.get("pass") is not True:
            raise RuntimeError("High-resolution subcheck is not passed and image-hash matched")
        report["high_resolution"] = evidence
        report["high_resolution_reuse"] = {"path": str(args.reuse_high_resolution.resolve()),
            "sha256": sha256(args.reuse_high_resolution), "prior_overall_pass": prior.get("pass"),
            "origin_uno_build": 2026100709, "current_uno_build": uno_identity,
            "scope": "passed carrier/deadtime subcheck of identical Nucleo image; Uno diagnostic decoder changed; prior overall failure preserved"}

    def cli(extra, label):
        run_logged([PROGRAMMER, "-c", "port=SWD", "mode=UR", "reset=HWrst", "sn=" + SERIAL,
                    *extra], logs / label, timeout=60)

    def program(image, binary, label):
        cli(["-w", str(image), "-v", "-rst"], label + "_flash.log")
        rb = out / (label + "_readback.bin")
        try:
            cli(["-u", "0x08000000", str(binary.stat().st_size), str(rb)], label + "_readback.log")
            if rb.read_bytes() != binary.read_bytes():
                raise RuntimeError("Flash byte readback mismatch: " + label)
        finally:
            cli(["-rst"], label + "_reset.log")
        report[label + "_readback_match"] = True

    def zero_status(s):
        return (outputs_off(s) and s.get("fw_build") == uno_identity and s.get("vdc") == 0
                and s.get("bp_vbus_valid") == 1 and 0 <= s.get("bp_vbus_age_ms", 999999) < 300)

    def clean():
        h.fail_safe_stop()
        wait_status(h, lambda s: zero_status(s) and s.get("mc_fw_build") == FIXTURE
                    and s.get("bp_softstart_ready") == 1, 15, "fixture settled zero bus")
        h.command("CLEAR")
        return wait_status(h, lambda s: zero_status(s) and s.get("bp_fault") == 0
                           and s.get("estop") == 0 and s.get("bp_bad_cnt") == 0
                           and s.get("bp_clear_pending") == 0, 8, "clean fixture SAFE")

    def start(freq=5):
        clean()
        h.command("MODE VF")
        h.command("SET FREQ " + str(freq))
        h.post("/api/hv-arm", {"action": "arm", "confirm": "ARM LV HV OFF"}, "isolated zero-bus ARM")
        h.post("/api/start-sequence", {}, "Wi-Fi START")
        h.command("SET RUNLIMIT 14")
        return wait_status(h, lambda s: s.get("mc_fw_build") == FIXTURE and s.get("pwm") == 1
                           and int(s.get("bp_status", 0)) & 0x20 and s.get("vdc") == 0,
                           3, "fixture PWM active")

    try:
        report["before"] = h.status()
        ok, reason = precheck(report["before"])
        initial = report["before"]
        if (not ok and initial.get("bp_fault") == 2 and initial.get("mc_bad_cnt") == 0
                and precheck(dict(initial, bp_fault=5))[0]):
            # An MCU programming/reset interval can leave an idle transport latch.
            # Do not waive other guards or auto-start; observe real SAFE after CLEAR.
            h.command("CLEAR")
            report["idle_timeout_recovery"] = wait_status(h, lambda s: precheck(s)[0],
                                                          8, "idle CLEAR after peer reset")
            ok, reason = precheck(report["idle_timeout_recovery"])
        if not ok or report["before"].get("mc_fw_build") not in (2026100708, PRODUCTION):
            raise RuntimeError("Unsafe or unsupported baseline: " + reason)
        production_build = root / "mcsdk_reference/AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV/STM32CubeIDE/Debug"
        if sha256(production_build / prod_hex.name) != sha256(prod_hex):
            raise RuntimeError("Code equivalence build is not packaged production")
        report["code_equivalence"] = compare_code_sections(production_build, bench_build, out / "code_equivalence")
        if not report["code_equivalence"]["pass"]:
            raise RuntimeError("Critical PWM code differs")
        from saleae import automation
        with automation.Manager.connect(
                port=10430, connect_timeout_seconds=5) as manager:
            if not any(d.device_id == DEVICE and not d.is_simulation for d in manager.get_devices()):
                raise RuntimeError("Physical analyzer absent")
            h.fail_safe_stop()
            modified = True
            program(bench_hex, bench_bin, "fixture")
            clean()
            h.post("/api/arm-profile", {"profile": "lv"}, "isolated LV profile")
            with operator_keepalive(h) as heartbeat:
                for freq in (5, 20):
                    clean()
                    h.command("MODE VF")
                    h.command("SET FREQ " + str(freq))
                    h.post("/api/hv-arm", {"action": "arm", "confirm": "ARM LV HV OFF"}, "bounded ramp ARM")
                    folder = out / f"steady_{freq}hz"
                    folder.mkdir()
                    with automation.Manager.start_capture(manager, device_id=DEVICE,
                            device_configuration=automation.LogicDeviceConfiguration(
                                enabled_digital_channels=list(range(7)), digital_sample_rate=4_000_000),
                            capture_configuration=automation.CaptureConfiguration(
                                capture_mode=automation.TimedCaptureMode(duration_seconds=3))) as session:
                        time.sleep(.15)
                        h.post("/api/start-sequence", {}, "captured bounded ramp START")
                        wait_status(h, lambda s: s.get("pwm") == 1, 2, "bounded ramp RUN")
                        time.sleep(.5)
                        h.fail_safe_stop()
                        session.wait()
                        session.save_capture(str(folder / "capture.sal"))
                        session.export_raw_data_csv(directory=str(folder / "csv"), digital_channels=list(range(7)))
                    csv = folder / "csv/digital.csv"
                    entry = waveform(csv, 4_000_000, 16000, 1.35e-6, settled=False)
                    entry["status"] = h.status()
                    entry["commanded_frequency_hz"] = freq
                    entry["scope"] = "carrier/deadtime during bounded ramp, not steady target-frequency qualification"
                    entry["electrical_frequency_independently_validated"] = False
                    report["cases"][f"steady_{freq}hz"] = entry
                    h.fail_safe_stop()
                    if not entry["pass"]:
                        raise RuntimeError("Carrier/deadtime check failed: " + str(freq))
                from saleae import automation
                for label in ("STOP", "ESTOP", "FREQ_ZERO", "RUNLIMIT"):
                    clean()
                    h.command("MODE VF")
                    h.command("SET FREQ 5")
                    h.post("/api/hv-arm", {"action": "arm", "confirm": "ARM LV HV OFF"}, "transition ARM")
                    folder = out / label
                    folder.mkdir()
                    entry = {}
                    report["cases"][label] = entry
                    capture(manager, DEVICE, out / (label + "_flush"), .06, 4_000_000)
                    with manager.start_capture(device_id=DEVICE,
                            device_configuration=automation.LogicDeviceConfiguration(
                                enabled_digital_channels=list(range(7)), digital_sample_rate=4_000_000),
                            capture_configuration=automation.CaptureConfiguration(
                                capture_mode=automation.TimedCaptureMode(duration_seconds=4))) as session:
                        time.sleep(.25)
                        h.post("/api/start-sequence", {}, "captured Wi-Fi START " + label)
                        wait_status(h, lambda s: s.get("pwm") == 1 and s.get("vdc") == 0, 2, "captured RUN")
                        time.sleep(.5)
                        if label in ("STOP", "ESTOP"):
                            h.post("/api/stop-sequence", {"emergency": label == "ESTOP"}, "captured " + label)
                        elif label == "FREQ_ZERO":
                            h.command("SET FREQ 0")
                        else:
                            h.command("SET RUNLIMIT 0.1")
                        entry["off_status"] = wait_status(h, outputs_off, 3, "outputs off " + label)
                        session.wait()
                        session.save_capture(str(folder / "capture.sal"))
                        session.export_raw_data_csv(directory=str(folder / "csv"), digital_channels=list(range(7)))
                    csv = folder / "csv/digital.csv"
                    entry["waveform"] = waveform(csv, 4_000_000, 16000, 1.35e-6, settled=False)
                    entry["off_tail"] = off_tail(csv, 4_000_000)
                    entry["pass"] = entry["waveform"]["pass"] and entry["off_tail"]["pass"]
                    if not entry["pass"]:
                        raise RuntimeError("Captured transition failed: " + label)
                clean()
                h.command("SET FREQ 5")
                h.post("/api/hv-arm", {"action": "arm", "confirm": "ARM LV HV OFF"}, "software break ARM")
                folder = out / "BKIN_SOFTWARE_EVENT"
                folder.mkdir()
                with manager.start_capture(device_id=DEVICE,
                        device_configuration=automation.LogicDeviceConfiguration(
                            enabled_digital_channels=list(range(7)), digital_sample_rate=4_000_000),
                        capture_configuration=automation.CaptureConfiguration(
                            capture_mode=automation.TimedCaptureMode(duration_seconds=4))) as session:
                    time.sleep(.2)
                    h.post("/api/start-sequence", {}, "software break START")
                    wait_status(h, lambda s: s.get("pwm") == 1, 2, "break-test RUN")
                    time.sleep(.3)
                    run_logged([PROGRAMMER, "-c", "port=SWD", "mode=HOTPLUG", "sn=" + SERIAL,
                                "-w32", "0x40012c14", "0x80", "-nv"], logs / "software_break_event.log", timeout=15)
                    report["software_break_off"] = wait_status(h, outputs_off, 2, "software TIM1 break")
                    session.wait()
                    session.save_capture(str(folder / "capture.sal"))
                    session.export_raw_data_csv(directory=str(folder / "csv"), digital_channels=list(range(7)))
                report["cases"]["BKIN_SOFTWARE_EVENT"] = off_tail(folder / "csv/digital.csv", 4_000_000)
                report["cases"]["BKIN_SOFTWARE_EVENT"]["scope"] = "TIM1 BG event and IRQ only, not physical PA6 or IPM protection qualification"
                code, body = h.request("POST", "/api/start-sequence", {})
                report["cases"]["BREAK_RESTART_REJECTED"] = {"pass": code == 409 and body.get("ok") is False,
                                                              "http_status": code, "response": body}
                report["keepalive"] = heartbeat
            # Stop operator heartbeat intentionally, leaving UART physically intact.
            clean()
            h.command("MODE VF")
            h.command("SET FREQ 5")
            h.post("/api/operator-heartbeat", {}, "last heartbeat before intentional loss")
            time.sleep(1)
            h.post("/api/hv-arm", {"action": "arm", "confirm": "ARM LV HV OFF"}, "heartbeat loss ARM")
            h.post("/api/start-sequence", {}, "heartbeat loss START")
            report["heartbeat_active"] = wait_status(h, lambda s: s.get("pwm") == 1, 2, "heartbeat loss RUN")
            report["heartbeat_off"] = wait_status(h, outputs_off, 5, "operator heartbeat timeout")
            idle = capture(manager, DEVICE, out / "heartbeat_timeout_low", .12, 4_000_000)
            report["cases"]["HEARTBEAT_TIMEOUT"] = analyze_static(idle, sample_rate_hz=4_000_000)
            report["cases"]["HEARTBEAT_TIMEOUT"]["scope"] = "off tail after HMI operator timeout; not UART cable-loss timing"
            report["operator_heartbeat_independently_validated"] = False
            report["pass"] = all(e.get("pass") is True for e in report["cases"].values())
    except BaseException as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        try:
            report["failure_status_before_restore"] = h.status()
        except Exception as status_error:
            report["failure_status_error"] = str(status_error)
    finally:
        try:
            report["final_stop"] = h.fail_safe_stop()[0]
        except Exception as exc:
            report["stop_error"] = str(exc)
        if modified:
            try:
                cli(["-rst"], "fixture_reset_before_restore.log")
                clean()
                h.post("/api/arm-profile", {"profile": "hv"}, "restore HV profile")
            except Exception as exc:
                report["profile_restore_error"] = str(exc)
            try:
                program(prod_hex, prod_bin, "production")
                report["restored"] = True
                report["final_status"] = wait_status(h, lambda s: zero_status(s)
                    and s.get("mc_fw_build") == PRODUCTION and s.get("hmi_hv_armed") == 0,
                    25, "production 801 restored SAFE")
                report["calibration_preserved"] = report["final_status"].get("hmi_vbus_hv_calibrated") == 1
                report["hv_profile_restored"] = report["final_status"].get("hmi_arm_profile") == "hv"
                if not report["hv_profile_restored"]:
                    report["pass"] = False
            except Exception as exc:
                report["restore_error"] = str(exc)
                report["restored"] = False
        try:
            log_text = get_wifi_logs(h, h.token)
            (out / "wifi_logs.txt").write_text(log_text, encoding="utf-8")
            if "HEARTBEAT_TIMEOUT" in report["cases"]:
                reason_logged = any("OPERATOR_HEARTBEAT_LOST" in line
                                    for line in log_text.splitlines())
                report["cases"]["HEARTBEAT_TIMEOUT"]["operator_timeout_reason_logged"] = reason_logged
                report["operator_heartbeat_independently_validated"] = False
        except Exception as exc:
            report["logs_error"] = str(exc)
        h.close()
        report["pass"] = (report["pass"] and report["restored"]
            and report.get("calibration_preserved") is True and report.get("hv_profile_restored") is True)
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in ("pass", "error", "restored", "restore_error",
                     "profile_restore_error", "calibration_preserved")}, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
