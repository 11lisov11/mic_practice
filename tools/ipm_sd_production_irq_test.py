"""Test the production IRQ with software BG while outputs are already off."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from run_wifi_nucleo_pwm_bench import (
    WifiHmi, analyze_static, capture, read_control_token, verify_unpowered_preflash, wait_status,
)
from wifi_stop_tail_probe import TIM1, parse_registers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-isolated-zero-bus", action="store_true")
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--package", type=Path, default=Path("firmware/ready_to_flash_sd_20261006"))
    args = parser.parse_args()
    if not args.confirm_isolated_zero_bus:
        parser.error("Disconnected mains/DC source, motor and J4; zero DC bus required")
    from saleae import automation
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    package = args.package.resolve()
    elf = package / "nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf"
    programmer = "C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe"
    gdb = ("C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins/"
           "com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.14.3.rel1.win32_1.0.100.202602081740/"
           "tools/bin/arm-none-eabi-gdb.exe")
    address_result = subprocess.run(
        [gdb, "-batch", "-ex", "file " + elf.as_posix(),
         "-ex", "p/x &Mci[0].CurrentFaults", "-ex", "p/x &Mci[0].PastFaults"],
        text=True, capture_output=True, check=True, timeout=15)
    (out / "elf_addresses.log").write_text(address_result.stdout + address_result.stderr)
    addresses = [int(x, 16) for x in re.findall(r"\$\d+ = (0x[0-9a-f]+)", address_result.stdout)]
    if (len(addresses) != 2 or not 0x20000000 <= addresses[0] < 0x20008000
            or addresses[1] != addresses[0] + 2):
        raise RuntimeError("ELF fault addresses invalid")
    addr = addresses[0]
    token = read_control_token("adb", "3880458060", "/home/arduino/.config/mic-ai/control_token")
    hmi = WifiHmi("http://192.168.1.138:8080", token, [], via_wsl=True)
    report = {"pass": False, "checks": {}, "fault_word_address": hex(addr),
              "scope": "software BG while MOE already off; not active external BKIN qualification",
              "elf_sha256": hashlib.sha256(elf.read_bytes()).hexdigest()}
    injected = False

    def cli(extra, name):
        result = subprocess.run([programmer, "-c", "port=SWD", "mode=HOTPLUG",
                                 "sn=003A002C3335510933383531", *extra],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=15)
        (out / name).write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError("CubeProgrammer failed: " + name)
        return parse_registers(result.stdout)

    def snapshot(name):
        words = cli(["-r32", hex(TIM1), "104", "-r32", hex(addr), "4"], name)
        return {"MOE": bool(words[TIM1 + 0x44] & 0x8000),
                "CurrentFaults": words[addr] & 0xFFFF, "PastFaults": words[addr] >> 16}

    try:
        report["before_status"] = hmi.status()
        verify_unpowered_preflash(report["before_status"])
        if (report["before_status"].get("mc_fw_build") != 2026100601
                or report["before_status"].get("bp_clear_pending") != 0):
            raise RuntimeError("Wrong production identity or pending CLEAR")
        report["before"] = snapshot("before.log")
        if report["before"]["MOE"] or report["before"]["PastFaults"] & 0x400:
            raise RuntimeError("Expected off outputs without an existing DP fault")
        with automation.Manager.connect(port=10430) as manager, ThreadPoolExecutor(max_workers=1) as pool:
            device = "A7D1BB81883C0092"
            if not any(d.device_id == device and not d.is_simulation for d in manager.get_devices()):
                raise RuntimeError("Physical analyzer missing")
            future = pool.submit(capture, manager, device, out / "capture", 2.0, 4_000_000)
            time.sleep(0.5)
            injected = True
            cli(["-w32", hex(TIM1 + 0x14), "0x80", "-nv"], "inject_BG.log")
            time.sleep(0.2)
            report["after"] = snapshot("after.log")
            report["waveform"] = analyze_static(future.result(timeout=10), sample_rate_hz=4_000_000)
        report["after_status"] = hmi.status()
        report["checks"] = {
            "new_driver_fault_latched": bool(report["after"]["PastFaults"] & 0x400),
            "no_new_overvoltage_fault": (report["after"]["PastFaults"] & 2) == (report["before"]["PastFaults"] & 2),
            "MOE_remained_off": not report["after"]["MOE"],
            "all_six_LOW_through_injection": report["waveform"]["pass"],
            "wifi_still_SAFE": report["after_status"].get("state") == "SAFE"
            and report["after_status"].get("pwm") == 0,
        }
        report["pass"] = all(report["checks"].values())
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            if injected:
                # Reset the test fault, not the image or safety thresholds.
                cli(["-rst"], "cleanup_reset.log")
                report["clean_status"] = wait_status(
                    hmi, lambda s: s.get("mc_fw_build") == 2026100601 and s.get("state") == "SAFE"
                    and s.get("pwm") == 0 and s.get("bp_age_ms", 999999) < 300, 8, "clean production boot")
                hmi.command("CLEAR")
                wait_status(hmi, lambda s: s.get("bp_bad_cnt") == 0 and s.get("bp_bad") == 0
                            and s.get("pwm") == 0, 8, "clean UART counters")
                report["clean_registers"] = snapshot("cleanup_registers.log")
                if report["clean_registers"]["PastFaults"] & 0x400:
                    raise RuntimeError("Injected test fault survived cleanup")
            report["final_stop_http"] = hmi.fail_safe_stop()[0]
            report["pass"] = report["pass"] and report["final_stop_http"] == 200
        except Exception as exc:
            report["cleanup_error"] = str(exc)
            report["pass"] = False
        hmi.close()
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report.get(k) for k in
                      ("pass", "checks", "before", "after", "clean_registers", "error", "cleanup_error")}, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
