"""Qualify isolated logic PWM via Wi-Fi and restore hash-checked production 801."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import threading
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


def isolated_idle(s, uno_identity):
    try:
        return (outputs_off(s) and s.get("state") == "SAFE"
                and s.get("fw_build") == uno_identity
                and s.get("hmi_hv_armed") == 0
                and math.isfinite(s["vdc"]) and 0 <= s["vdc"] <= 2
                and 0 <= s["bp_vbus_raw"] <= 20
                and s.get("bp_vbus_valid") == 1
                and 0 <= s["bp_age_ms"] < 300
                and 0 <= s["bp_vbus_age_ms"] < 300
                and not (s["bp_status"] & 0x22)
                and all(s.get(k) == 0 for k in ("precharge", "pfc", "brake", "bp_ext")))
    except (KeyError, ValueError, TypeError, OverflowError):
        return False


def transport_clean(s, reply_baseline=None, command_baseline=0):
    expected = reply_baseline or {}
    if set(expected) - {"mc_bad_integrity", "mc_bad_sequence"}:
        return False
    if type(command_baseline) is not int or command_baseline not in (0, 1):
        return False
    expected = dict(expected, mc_bad_cnt=command_baseline)
    return all(type(s.get(k)) is int and s[k] == expected.get(k, 0) for k in (
        "mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence",
        "mc_uart_error_flags", "mc_last_uart_error_flags", "uno_tx_short_writes"))


def reply_history(s):
    keys = ("mc_bad_integrity", "mc_bad_sequence")
    if any(type(s.get(k)) is not int or not 0 <= s[k] < 65535 for k in keys):
        raise RuntimeError("Missing or saturated reply history")
    return {k: s[k] for k in keys}


def expected_programming_frame_error(s, uno_identity, build):
    # Only a single FE on the just-restarted, stopped peer. CRC, noise,
    # overrun, active motor or other hardware faults remain disqualifying.
    return (isolated_idle(s, uno_identity) and s.get("mc_fw_build") == build
            and s.get("mc_diag_valid") == 1 and s.get("bp_fault") == 1
            and s.get("mc_bad_cnt") == 1 and s.get("mc_last_bad_reason") == 12
            and s.get("mc_last_uart_error_flags") == 2
            and s.get("mc_fault_reason") in (8, 12)
            and s.get("mc_uart_error_flags") in (0, 2)
            and s.get("mc_fault_motor_state") in (0, 10)
            and s.get("mc_fault_current_mask") in (0, 4)
            and s.get("mc_fault_occurred_mask") in (0, 4)
            and s.get("uno_tx_short_writes") == 0)


def expected_bench_estop(s, uno_identity, build):
    return (isolated_idle(s, uno_identity) and s.get("mc_fw_build") == build
            and s.get("estop") == 1 and s.get("mc_diag_valid") == 1
            and s.get("mc_fault_reason") == 4 and s.get("mc_last_bad_reason") == 0
            and s.get("mc_fault_current_mask") == 0 and s.get("mc_fault_occurred_mask") == 0
            and transport_clean(s))


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
    parser.add_argument("--carrier-sample-rate", type=int, choices=(4_000_000, 12_000_000, 24_000_000),
                        default=12_000_000)
    parser.add_argument("--uno-build", type=int,
                        choices=(2026100802, 2026100803, 2026100804, 2026101001, 2026101002), default=UNO)
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
            or manifest["bench_build"] != FIXTURE
            or manifest.get("fixture_mcsdk_filtered_voltage_limit_v") != 2):
        raise RuntimeError("Wrong fixture provenance")
    production_source = root / "mcsdk_reference/AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV"
    for relative, hashes in manifest["changed_files"].items():
        if (sha256(fixture / "project" / relative) != hashes["bench_sha256"]
                or sha256(production_source / relative) != hashes["production_sha256"]):
            raise RuntimeError("Fixture provenance hash changed: " + relative)
    for relative, digest in manifest["critical_sources_identical"].items():
        if (sha256(fixture / "project" / relative) != digest
                or sha256(production_source / relative) != digest):
            raise RuntimeError("Critical source differs: " + relative)
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
              "hv_release_approved": False,
              "uno_build": uno_identity,
              "carrier_sample_rate_hz": args.carrier_sample_rate,
              "commands": commands, "cases": {}, "restored": False,
              "images": {"production_hex": sha256(prod_hex), "production_bin": sha256(prod_bin),
                         "fixture_hex": sha256(bench_hex), "fixture_bin": sha256(bench_bin)}}
    modified = False
    reply_baseline = {}
    command_baseline = 0

    def link_clean(s):
        return transport_clean(s, reply_baseline, command_baseline)

    def acknowledge_programming_boundary(build, label):
        s = wait_status(h, lambda x: zero_status(x) and x.get("mc_fw_build") == build,
                        15, "stopped programming boundary")
        report[label + "_before_ack"] = s
        if expected_programming_frame_error(s, uno_identity, build):
            # Preserve the complete diagnosis before this bench-only ACK. A
            # subsequent runtime error is never allowed to move the baseline.
            stable = []
            for _ in range(5):
                x = h.status()
                stable.append(x)
                if not expected_programming_frame_error(x, uno_identity, build):
                    raise RuntimeError("Programming FE not stable; refusing ACK")
                time.sleep(.2)
            report[label + "_frame_error_samples"] = stable
            h.command("CLEAR")
            s = wait_status(h, lambda x: zero_status(x) and x.get("mc_fw_build") == build
                            and x.get("bp_fault") in (0, 5) and x.get("estop") == 0
                            and x.get("mc_clear_pending") == 0,
                            8, "idle programming FE acknowledged")
            if not transport_clean(s, reply_history(s), 1):
                raise RuntimeError("Programming FE ACK did not restore transport")
            report[label + "_frame_error_acknowledged"] = True
        report[label + "_after_ack"] = s
        return s
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
        return isolated_idle(s, uno_identity)

    def clean():
        h.fail_safe_stop()
        before_clear = wait_status(h, lambda s: zero_status(s) and s.get("mc_fw_build") == FIXTURE
                    and s.get("bp_softstart_ready") == 1, 15, "fixture settled zero bus")
        if not link_clean(before_clear):
            raise RuntimeError("Transport fault preserved; refusing automatic CLEAR")
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
        reply_baseline = reply_history(report["before"])
        report["initial_reply_history"] = dict(reply_baseline)
        ok, reason = precheck(report["before"])
        initial = report["before"]
        if (not ok and initial.get("bp_fault") == 2 and link_clean(initial)
                and initial.get("mc_diag_valid") == 1
                and initial.get("mc_last_bad_reason") == 0
                and precheck(dict(initial, bp_fault=5))[0]):
            # An MCU programming/reset interval can leave an idle transport latch.
            # Do not waive other guards or auto-start; observe real SAFE after CLEAR.
            h.command("CLEAR")
            report["idle_timeout_recovery"] = wait_status(h, lambda s: precheck(s)[0],
                                                          8, "idle CLEAR after peer reset")
            ok, reason = precheck(report["idle_timeout_recovery"])
        if not ok or report["before"].get("mc_fw_build") not in (2026100708, PRODUCTION):
            raise RuntimeError("Unsafe or unsupported baseline: " + reason)
        if not isolated_idle(h.status(), uno_identity) or not link_clean(h.status()):
            raise RuntimeError("Isolated idle, clean command channel and unchanged reply history required")
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
            idle_csv = capture(manager, DEVICE, out / "preflash_idle", .12, 4_000_000)
            report["preflash_idle"] = analyze_static(idle_csv, sample_rate_hz=4_000_000)
            if not report["preflash_idle"]["pass"]:
                raise RuntimeError("Preflash physical outputs not LOW")
            h.fail_safe_stop()
            modified = True
            program(bench_hex, bench_bin, "fixture")
            acknowledge_programming_boundary(FIXTURE, "fixture_boundary")
            boundary = wait_status(h, lambda s: zero_status(s) and s.get("mc_fw_build") == FIXTURE
                                  and s.get("bp_softstart_ready") == 1, 15, "post-programming idle")
            # Keep history across resets. Qualification measures NEW reply failures
            # after the programming interval, not a fictitious reset-to-zero count.
            reply_baseline = reply_history(boundary)
            command_baseline = 1 if report.get("fixture_boundary_frame_error_acknowledged") else 0
            report["post_programming_reply_baseline"] = dict(reply_baseline)
            report["post_programming_command_baseline"] = command_baseline
            report["programming_interval_status"] = boundary
            if not link_clean(boundary):
                raise RuntimeError("Controller/UART fault at programming boundary")
            report["post_programming_idle_samples"] = []
            for _ in range(5):
                sample = h.status()
                report["post_programming_idle_samples"].append(sample)
                if not zero_status(sample) or not link_clean(sample):
                    raise RuntimeError("Reply counters changed after programming boundary")
                time.sleep(.2)
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
                    if args.carrier_sample_rate > 4_000_000:
                        # A short steady acquisition avoids overloading the USB
                        # analyzer; begin capture only after the actual RUN ACK.
                        h.post("/api/start-sequence", {}, "bounded high-resolution START")
                        report["carrier_active_" + str(freq)] = wait_status(h,
                            lambda s: s.get("pwm") == 1 and s.get("mc_fw_build") == FIXTURE,
                            2, "high-resolution RUN")
                        csv = capture(manager, DEVICE, folder / "short_active", .10,
                                      args.carrier_sample_rate)
                        h.fail_safe_stop()
                    else:
                        with automation.Manager.start_capture(manager, device_id=DEVICE,
                                device_configuration=automation.LogicDeviceConfiguration(
                                    enabled_digital_channels=list(range(7)), digital_sample_rate=args.carrier_sample_rate),
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
                    entry = waveform(csv, args.carrier_sample_rate, 16000, 1.35e-6, settled=False)
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
                # Exercise the fixed RPC/loop ownership while actual outputs switch.
                clean()
                h.command("MODE VF")
                h.command("SET FREQ 5")
                h.post("/api/hv-arm", {"action": "arm", "confirm": "ARM LV HV OFF"}, "RPC stress ARM")
                folder = out / "ACTIVE_RPC_STRESS"
                folder.mkdir()
                samples, observer_errors = [], []
                observer_stop = threading.Event()
                observer_h = WifiHmi(h.base, "", [], via_wsl=True)

                def observe_active():
                    try:
                        while not observer_stop.is_set():
                            s = observer_h.status()
                            samples.append(s)
                            if (not link_clean(s) or s.get("mc_fw_build") != FIXTURE
                                    or not math.isfinite(s["vdc"]) or not 0 <= s["vdc"] <= 2):
                                raise RuntimeError("Active observer transport/bus gate failed")
                            observer_stop.wait(.1)
                    except Exception as exc:
                        observer_errors.append(str(exc))
                        observer_stop.set()

                observer = threading.Thread(target=observe_active)
                try:
                    with manager.start_capture(device_id=DEVICE,
                            device_configuration=automation.LogicDeviceConfiguration(
                                enabled_digital_channels=list(range(7)), digital_sample_rate=4_000_000),
                            capture_configuration=automation.CaptureConfiguration(
                                capture_mode=automation.TimedCaptureMode(duration_seconds=5))) as session:
                        observer.start()
                        time.sleep(.2)
                        h.post("/api/start-sequence", {}, "concurrent RPC START")
                        wait_status(h, lambda s: s.get("pwm") == 1, 2, "RPC stress RUN")
                        for frequency in (10, 20):
                            s = h.status()
                            if not link_clean(s) or s.get("pwm") != 1 or observer_errors:
                                raise RuntimeError("Active RPC window failed before setpoint")
                            h.command("SET FREQ " + str(frequency))
                        h.fail_safe_stop()
                        session.wait()
                        session.save_capture(str(folder / "capture.sal"))
                        session.export_raw_data_csv(directory=str(folder / "csv"), digital_channels=list(range(7)))
                finally:
                    h.fail_safe_stop()
                    observer_stop.set()
                    if observer.ident is not None:
                        observer.join()
                    observer_h.close()
                    report["active_rpc_samples"] = samples
                    report["active_rpc_errors"] = observer_errors
                csv = folder / "csv/digital.csv"
                entry = {"waveform": waveform(csv, 4_000_000, 16000, 1.35e-6, settled=False),
                         "off_tail": off_tail(csv, 4_000_000),
                         "status": h.status(), "observer_samples": len(samples)}
                entry["pass"] = (entry["waveform"]["pass"] and entry["off_tail"]["pass"]
                    and not observer_errors and any(s.get("pwm") == 1 for s in samples)
                    and all(link_clean(s) for s in samples) and link_clean(entry["status"]))
                report["cases"]["ACTIVE_RPC_STRESS"] = entry
                if not entry["pass"]:
                    raise RuntimeError("Concurrent RPC/PWM stress failed")
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
            report["transport_after_active"] = h.status()
            report["transport_clean_after_active"] = link_clean(report["transport_after_active"])
            report["new_active_reply_errors"] = {k: report["transport_after_active"][k] - v
                                                for k, v in reply_baseline.items()}
            report["new_active_command_errors"] = report["transport_after_active"]["mc_bad_cnt"] - command_baseline
            if not report["transport_clean_after_active"]:
                raise RuntimeError("Transport fault after active test")
            report["pass"] = all(e.get("pass") is True for e in report["cases"].values())
            report["active_checks_pass"] = report["pass"]
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
                if not zero_status(h.status()):
                    raise RuntimeError("Cannot switch profile before discharged SAFE")
                terminal = h.status()
                if (terminal.get("estop") == 1 and "error" not in report
                        and report["cases"].get("HEARTBEAT_TIMEOUT", {}).get("pass") is True
                        and link_clean(terminal)):
                    report["expected_test_estop_before_clear"] = terminal
                    clean()
                    report["expected_test_estop_acknowledged"] = True
                h.post("/api/arm-profile", {"profile": "hv"}, "restore HV profile")
            except Exception as exc:
                report["profile_restore_error"] = str(exc)
            try:
                program(prod_hex, prod_bin, "production")
                report["restored"] = True
                acknowledge_programming_boundary(PRODUCTION, "production_boundary")
                terminal = h.status()
                if expected_bench_estop(terminal, uno_identity, PRODUCTION):
                    report["restored_test_estop_before_clear"] = terminal
                    h.command("CLEAR")
                    wait_status(h, lambda s: zero_status(s) and s.get("estop") == 0
                                and s.get("mc_fw_build") == PRODUCTION and s.get("bp_fault") in (0, 5),
                                8, "restored idle ESTOP acknowledged")
                    report["restored_test_estop_acknowledged"] = True
                if zero_status(h.status()) and h.status().get("estop") == 0:
                    h.post("/api/arm-profile", {"profile": "hv"}, "final disarmed production profile")
                report["final_status"] = wait_status(h, lambda s: zero_status(s)
                    and s.get("mc_fw_build") == PRODUCTION and s.get("hmi_hv_armed") == 0,
                    25, "production 801 restored SAFE")
                report["calibration_preserved"] = report["final_status"].get("hmi_vbus_hv_calibrated") == 1
                report["hv_profile_restored"] = report["final_status"].get("hmi_arm_profile") == "hv"
                if not report["hv_profile_restored"]:
                    report["pass"] = False
                final = report["final_status"]
                if (final.get("estop") != 0 or final.get("bp_fault") not in (0, 5)
                        or not transport_clean(final, reply_history(final), final.get("mc_bad_cnt", -1))):
                    raise RuntimeError("Restored production transport unhealthy")
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
