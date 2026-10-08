"""Additional real HTTP/capture scenarios for the isolated logic-only bench."""
from __future__ import annotations

import time
import threading
from contextlib import contextmanager
from pathlib import Path


def transition_checks(times, values):
    """Require one sustained PWM burst, with LOW before and after it."""
    from saleae_pwm_analyze import transitions

    checks = {}
    evidence = {}
    for channel in range(6):
        edges = transitions(times, values[channel])
        first = edges[0]["time"] if edges else None
        last = edges[-1]["time"] if edges else None
        gaps = [b["time"] - a["time"] for a, b in zip(edges, edges[1:])]
        checks[str(channel)] = bool(
            len(edges) > 100 and values[channel][0] == 0 and values[channel][-1] == 0
            and first - times[0] >= 0.1 and times[-1] - last >= 0.5
            and last - first >= 0.1 and max(gaps, default=1) < 0.001
        )
        evidence[str(channel)] = {"first_edge_s": first, "last_edge_s": last,
                                  "edges": len(edges), "max_internal_gap_s": max(gaps, default=None)}
    return {"pass": all(checks.values()), "checks": checks, "channels": evidence,
            "scope": "single uninterrupted burst with LOW margins; host and capture clocks not synchronized"}


def run_transitions(hmi, manager, device, out, report):
    from saleae import automation
    from run_wifi_nucleo_pwm_bench import wait_status
    from saleae_pwm_analyze import load_csv, analyze_csv
    from nucleo_logic_capture import capture_checks

    records = report.setdefault("transitions", [])
    for cycle, emergency in enumerate((False, True, False), 1):
        hmi.post("/api/stop-sequence", {"emergency": False}, "transition prepare STOP")
        hmi.command("CLEAR")
        wait_status(hmi, lambda s: outputs_off(s) and s.get("estop") == 0
                    and s.get("bp_fault") == 0, 4, "transition SAFE")
        hmi.post("/api/hv-arm", {"action": "arm", "confirm": "ARM LV HV OFF"}, "transition ARM")
        hmi.command("DIAG ON")
        folder = out / f"transition_{cycle}"
        folder.mkdir()
        entry = {"cycle": cycle, "emergency": emergency, "pass": False,
                 "sample_rate_hz": 2_000_000}
        records.append(entry)
        with manager.start_capture(
            device_id=device,
            device_configuration=automation.LogicDeviceConfiguration(
                enabled_digital_channels=list(range(7)), digital_sample_rate=2_000_000),
            capture_configuration=automation.CaptureConfiguration(
                capture_mode=automation.TimedCaptureMode(duration_seconds=4)),
        ) as session:
            began = time.monotonic()
            try:
                time.sleep(0.4)
                entry["start_sent_host_s"] = time.monotonic() - began
                hmi.post("/api/start-sequence", {}, "continuous capture START")
                wait_status(hmi, lambda s: s.get("pwm") == 1 and
                            bool(int(s.get("bp_status", 0)) & 0x20), 1, "PWM active")
                time.sleep(0.35)
                entry["stop_sent_host_s"] = time.monotonic() - began
                hmi.post("/api/stop-sequence", {"emergency": emergency}, "continuous capture STOP")
                entry["stop_response_host_s"] = time.monotonic() - began
                wait_status(hmi, outputs_off, 2, "PWM stopped")
            finally:
                hmi.fail_safe_stop()
            session.wait()
            session.save_capture(str(folder / "capture.sal"))
            session.export_raw_data_csv(directory=str(folder / "csv"), digital_channels=list(range(7)))
        csv = folder / "csv" / "digital.csv"
        times, values = load_csv(csv, list(range(6)))
        entry["transition"] = transition_checks(times, values)
        analysis = analyze_csv(csv, expect_pwm=True, selected_sample_rate_hz=2_000_000,
                               max_sample_period_ns=500)
        waveform = capture_checks(analysis, True)
        waveform["checks"]["carrier_10khz"] = all(
            abs(ch["freq_hz_from_rising"] - 10_000) <= 100 for ch in analysis["channels"].values())
        waveform["pass"] = all(waveform["checks"].values())
        entry["waveform"] = {**waveform, "analysis": analysis}
        entry["pass"] = entry["transition"]["pass"] and entry["waveform"]["pass"]
        if not entry["pass"]:
            raise RuntimeError(f"Continuous START/STOP capture {cycle} failed; inspect preserved waveform")


def outputs_off(status: dict) -> bool:
    return (status.get("pwm") == 0
            and not (int(status.get("bp_status", 0x20)) & 0x20)
            and float(status.get("bp_age_ms", 999999)) < 300)


@contextmanager
def operator_keepalive(hmi):
    from run_wifi_nucleo_pwm_bench import WifiHmi
    client = WifiHmi(hmi.base, hmi.token, hmi.commands, via_wsl=hmi.via_wsl)
    stop = threading.Event()
    evidence = {"errors": [], "sent": 0}

    def worker():
        while not stop.is_set():
            try:
                client.post("/api/operator-heartbeat", {}, "isolated timer heartbeat")
                evidence["sent"] += 1
            except Exception as exc:
                evidence["errors"].append(str(exc))
                return
            stop.wait(0.25)

    thread = threading.Thread(target=worker)
    thread.start()
    try:
        yield evidence
    finally:
        stop.set()
        thread.join()
        client.close()


def run_scenarios(hmi, manager, device, out: Path, report: dict) -> None:
    from run_wifi_nucleo_pwm_bench import (
        WifiHmi, analyze_active, analyze_static, capture, wait_status,
    )

    scenarios = report.setdefault("scenarios", [])
    scenario_rate = 2_000_000
    report["scenario_sample_rate_hz"] = scenario_rate

    def record(name, passed, **evidence):
        scenarios.append({"name": name, "pass": bool(passed), **evidence})
        if not passed:
            raise RuntimeError(f"Wi-Fi scenario failed: {name}")

    def idle_capture(name):
        wait_status(hmi, outputs_off, 3, name)
        result = analyze_static(capture(manager, device, out / name, 0.1, scenario_rate),
                                sample_rate_hz=scenario_rate)
        if not result["pass"]:
            # Preserve the first capture; a new all-LOW capture establishes
            # steady off state only, never a glitch-free STOP transition.
            report.setdefault("capture_observations", []).append({
                "scenario": name, "first_capture": result,
                "limitation": "STOP transition timing/glitches unresolved",
            })
            time.sleep(0.2)
            followup = analyze_static(capture(manager, device, out / (name + "_confirmation"), 0.1, scenario_rate),
                                      sample_rate_hz=scenario_rate)
            record(name, followup["pass"], first_capture=result, waveform=followup,
                   scope="steady off state; initial capture contained transitions")
        else:
            record(name, True, waveform=result)

    def rejected(name, path, body, expected_code=409, client=None):
        client = client or hmi
        code, payload = client.request("POST", path, body)
        hmi.commands.append({"label": name, "path": path, "body": body,
                             "http_status": code, "ok": payload.get("ok"),
                             "transport": "wsl_nat_wifi_http" if client.via_wsl else "direct_wifi_http"})
        record(name, code == expected_code and payload.get("ok") is False,
               http_status=code, reason=payload.get("error"))
        idle_capture(name + "_outputs")

    def prepare():
        hmi.post("/api/stop-sequence", {"emergency": False}, "scenario STOP")
        hmi.command("CLEAR")
        wait_status(hmi, lambda s: outputs_off(s) and s.get("estop") == 0
                    and s.get("bp_fault") == 0 and s.get("bp_bad_cnt") == 0,
                    4, "scenario clear")

    def start(name):
        prepare()
        hmi.post("/api/hv-arm", {"action": "arm", "confirm": "ARM LV HV OFF"}, name + " ARM")
        hmi.command("DIAG ON")
        request_started = time.monotonic()
        hmi.post("/api/start-sequence", {}, name + " START SEQUENCE")
        request_completed = time.monotonic()
        result = analyze_active(capture(manager, device, out / (name + "_active"), 0.1, scenario_rate),
                                sample_rate_hz=scenario_rate)
        record(name + "_active", result["pass"], waveform=result,
               scope="diagnostic fixed-duty PWM; not production V/f")
        return request_started, request_completed

    prepare()
    unauthenticated = WifiHmi(hmi.base, "", [], via_wsl=hmi.via_wsl)
    try:
        rejected("missing_key", "/api/start-sequence", {}, 401, unauthenticated)
    finally:
        unauthenticated.close()
    rejected("start_without_arm", "/api/start-sequence", {})
    rejected("wrong_arm_phrase", "/api/hv-arm", {"action": "arm", "confirm": "WRONG"})

    for cycle in range(3):
        name = f"repeat_{cycle + 1}"
        start(name)
        hmi.post("/api/stop-sequence", {"emergency": False}, name + " STOP")
        idle_capture(name + "_stopped")
        rejected(name + "_restart_without_arm", "/api/start-sequence", {})

    start("emergency")
    hmi.post("/api/stop-sequence", {"emergency": True}, "scenario ESTOP")
    stopped = wait_status(hmi, lambda s: outputs_off(s) and s.get("estop") == 1,
                          3, "ESTOP latch")
    record("estop_latched", stopped.get("estop") == 1)
    idle_capture("emergency_stopped")
    rejected("restart_with_estop", "/api/start-sequence", {})

    with operator_keepalive(hmi) as keepalive:
        began, start_completed = start("run_limit")
        limit = float(hmi.status()["hmi_start_runlimit_s"])
        deadline = began + limit + 2
        while time.monotonic() < deadline:
            status = hmi.status()
            if outputs_off(status) and status.get("estop") == 1:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("run-limit failed to stop PWM")
        elapsed = time.monotonic() - began
    record("run_limit_stopped", limit - 0.2 <= elapsed <= limit + 2
           and status.get("estop") == 1 and not keepalive["errors"],
           elapsed_from_start_request_s=elapsed,
           start_request_duration_s=start_completed - began,
           keepalive=keepalive,
           estop=status.get("estop"), configured_limit_s=limit)
    idle_capture("run_limit_outputs")

    start("heartbeat_loss")
    # Bound the independent MCU backup while making the 3 s watchdog first.
    hmi.command("SET RUNLIMIT 8")
    before = hmi.status()
    watchdog = float(before["hmi_operator_heartbeat_timeout_s"])
    if not 1 <= watchdog <= 5:
        raise RuntimeError("unexpected operator watchdog interval")
    began = time.monotonic()
    # Status GET does not refresh heartbeat. No authenticated request until off.
    stopped = wait_status(hmi, lambda s: outputs_off(s) and s.get("estop") == 1,
                          watchdog + 2, "operator heartbeat loss")
    elapsed = time.monotonic() - began
    record("heartbeat_loss_stopped", elapsed < 7 and stopped.get("hmi_hv_armed") == 0,
           elapsed_s=elapsed, watchdog_s=watchdog, backup_runlimit_s=8)
    idle_capture("heartbeat_loss_outputs")
    prepare()
