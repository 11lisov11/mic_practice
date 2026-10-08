"""Isolate post-STOP capture tails with TIM1 disabled and the G431 core halted."""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

from saleae_pwm_analyze import load_csv

TIM1 = 0x40012C00
GPIOA = 0x48000000
GPIOB = 0x48000400
DHCSR = 0xE000EDF0
PIN_GROUPS = ((GPIOA, (7, 8, 9, 10)), (GPIOB, (0, 1)))


def parse_registers(text: str) -> dict[int, int]:
    words = {}
    for line in text.splitlines():
        match = re.fullmatch(r"\s*0x([0-9a-fA-F]{8})\s*:\s*((?:[0-9a-fA-F]{8}\s*)+)\s*", line)
        if match:
            address = int(match[1], 16)
            for i, value in enumerate(match[2].split()):
                words[address + 4 * i] = int(value, 16)
    return words


def hardware_off(words: dict[int, int]) -> dict:
    checks = {}
    try:
        checks["core_halted"] = bool(words[DHCSR] & (1 << 17))
        checks["TIM1_counter_disabled"] = (words[TIM1] & 1) == 0
        checks["TIM1_MOE_disabled"] = (words[TIM1 + 0x44] & (1 << 15)) == 0
        checks["TIM1_six_outputs_disabled"] = (words[TIM1 + 0x20] & 0x555) == 0
        checks["GPIO_output_mode"] = all(
            (words[base] >> (2 * pin)) & 3 == 1
            for base, pins in PIN_GROUPS for pin in pins)
        checks["GPIO_push_pull"] = all(
            (words[base + 4] & (1 << pin)) == 0
            for base, pins in PIN_GROUPS for pin in pins)
        checks["GPIO_latches_low"] = all(
            (words[base + 0x14] & (1 << pin)) == 0
            for base, pins in PIN_GROUPS for pin in pins)
        checks["GPIO_inputs_low"] = all(
            (words[base + 0x10] & (1 << pin)) == 0
            for base, pins in PIN_GROUPS for pin in pins)
    except KeyError:
        checks["registers_complete"] = False
    return {"pass": bool(checks) and all(checks.values()), "checks": checks,
            "registers": {f"0x{k:08X}": f"0x{v:08X}" for k, v in words.items()}}


def tail_summary(path: Path, rate: int) -> dict:
    times, values = load_csv(path, list(range(6)))
    edges = [times[i] for ch in range(6) for i in range(1, len(times))
             if values[ch][i] != values[ch][i - 1]]
    last = max(edges, default=0.0)
    return {"edge_count": len(edges), "last_edge_s": last,
            "last_edge_sample": round(last * rate),
            "all_final_low": all(values[ch][-1] == 0 for ch in range(6)),
            "quiet_tail_s": times[-1] - last}


def run_probe(hmi, manager, device: str, out: Path, report: dict,
              programmer: Path, stlink: str) -> None:
    from run_wifi_nucleo_pwm_bench import analyze_active, analyze_static, capture, wait_status
    from wifi_bench_scenarios import operator_keepalive, outputs_off

    records = report.setdefault("stop_tail_probe", [])

    def debug_command(args: list[str], log: Path) -> str:
        command = [str(programmer), "-c", "port=SWD", "mode=HOTPLUG", "sn=" + stlink, *args]
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=15)
        log.write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError("ST-Link probe command failed: " + log.name)
        return result.stdout

    def halted_captures(folder: Path, rate: int, entry: dict) -> None:
        # A one-shot CubeProgrammer invocation resumes on disconnect. Keep
        # OpenOCD connected through both captures and bracket them with reads.
        package = Path.home() / ".platformio/packages/tool-openocd"
        executable = package / "bin/openocd.exe"
        if not executable.is_file():
            raise FileNotFoundError(executable)
        commands = ["gdb_port disabled", "tcl_port disabled", "telnet_port disabled",
                    "adapter serial " + stlink, "init", "halt", "echo REGISTERS_BEFORE"]
        reads = [f"mdw {hex(TIM1)} 20", f"mdw {hex(GPIOA)} 6",
                 f"mdw {hex(GPIOB)} 6", f"mdw {hex(DHCSR)} 1"]
        commands += reads + ["echo HALTED_CAPTURE_READY", "sleep 10000",
                             "echo REGISTERS_AFTER"] + reads + ["echo CAPTURE_WINDOW_END", "resume", "shutdown"]
        command = [str(executable), "-s", str(package / "openocd/scripts"),
                   "-f", "interface/stlink.cfg", "-f", "target/stm32g4x.cfg"]
        for item in commands:
            command += ["-c", item]
        log = folder / "persistent_halt.log"
        with log.open("w", encoding="utf-8") as stream:
            process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 10
                while "HALTED_CAPTURE_READY" not in log.read_text(encoding="utf-8"):
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Persistent OpenOCD halt not ready; inspect persistent_halt.log")
                    time.sleep(0.05)
                text = log.read_text(encoding="utf-8")
                entry["before_capture"] = hardware_off(parse_registers(text))
                if not entry["before_capture"]["pass"]:
                    raise RuntimeError("PWM pins not confirmed push-pull LOW with TIM1 off/core halted")
                first = capture(manager, device, folder / "halted_first", 0.1, rate)
                entry["first_capture"] = tail_summary(first, rate)
                second = capture(manager, device, folder / "halted_confirmation", 0.1, rate)
                entry["confirmation"] = analyze_static(second, sample_rate_hz=rate)
                if "REGISTERS_AFTER" in log.read_text(encoding="utf-8"):
                    raise RuntimeError("Capture processing exceeded persistent halt window")
                process.wait(timeout=15)
                if process.returncode:
                    raise RuntimeError("Persistent OpenOCD probe failed")
                text = log.read_text(encoding="utf-8")
                if "CAPTURE_WINDOW_END" not in text or "REGISTERS_AFTER" not in text:
                    raise RuntimeError("Missing post-capture register bracket")
                entry["after_capture"] = hardware_off(parse_registers(text.split("REGISTERS_AFTER", 1)[1]))
                if not entry["after_capture"]["pass"]:
                    raise RuntimeError("Core/output invariants changed during capture")
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)

    for cycle, rate in enumerate((2_000_000, 4_000_000, 24_000_000), 1):
        folder = out / f"stop_tail_probe_{cycle}"
        folder.mkdir()
        entry = {"rate_hz": rate, "pass": False}
        records.append(entry)
        hmi.fail_safe_stop()
        hmi.command("CLEAR")
        wait_status(hmi, lambda s: outputs_off(s) and s.get("bp_fault") == 0
                    and s.get("estop") == 0 and s.get("bp_bad") == 0
                    and s.get("bp_bad_cnt") == 0, 8, "probe SAFE with cleared UART counters")
        hmi.post("/api/hv-arm", {"action": "arm", "confirm": "ARM LV HV OFF"}, "probe ARM LV")
        hmi.command("DIAG ON")
        halted = False
        try:
            with operator_keepalive(hmi):
                hmi.post("/api/start-sequence", {}, "probe START")
                active = capture(manager, device, folder / "active", 0.1, rate)
                entry["active"] = analyze_active(active, sample_rate_hz=rate)
                if not entry["active"]["pass"]:
                    raise RuntimeError("Probe active waveform invalid")
                hmi.fail_safe_stop()
                entry["off_status"] = wait_status(hmi, outputs_off, 3, "probe STOP")
                # Mark before attempting halt so every failure path resumes the core.
                halted = True
                halted_captures(folder, rate, entry)
                entry["pass"] = entry["confirmation"]["pass"] and entry["first_capture"]["all_final_low"]
        finally:
            if halted:
                debug_command(["-run"], folder / "resume.log")
                # The diagnostic bridge keeps a lifetime bad-frame counter;
                # CLEAR does not reset it. A prolonged debug halt can lose UART
                # bytes. Start a new diagnostic session rather than waive ARM.
                debug_command(["-rst"], folder / "reset_diagnostic_session.log")
                entry["new_diagnostic_session_after_halt"] = True
                time.sleep(0.2)
            hmi.fail_safe_stop()
        if not entry["pass"]:
            raise RuntimeError("Halted-core STOP probe failed")
        hmi.command("CLEAR")
        wait_status(hmi, lambda s: outputs_off(s) and s.get("bp_fault") == 0
                    and s.get("estop") == 0 and s.get("bp_bad") == 0
                    and s.get("bp_bad_cnt") == 0, 8, "resumed probe SAFE with cleared UART counters")
        (folder / "result.json").write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    report["stop_tail_scope"] = (
        "Halted core, disabled TIM1 and push-pull LOW bracket first capture. "
        "Any observed PWM prefix cannot demonstrate software PWM restart; "
        "does not measure HTTP-to-STOP latency or validate production power stage.")
