"""Audit production USART1 configuration without UART commands or register writes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

from run_wifi_nucleo_pwm_bench import WifiHmi, verify_unpowered_preflash
from wifi_stop_tail_probe import parse_registers

USART1 = 0x40013800
GPIOB = 0x48000400
RCC = 0x40021000
TIM1 = 0x40012C00
DHCSR = 0xE000EDF0
# Exclude RDR and all ADC registers: reads can consume data or clear flags.
READ_BLOCKS = ((USART1, 16), (USART1 + 0x2C, 4), (GPIOB, 40),
               (RCC + 8, 8), (RCC + 0x88, 4), (TIM1 + 0x44, 4), (DHCSR, 4))


def decode(words: dict[int, int]) -> dict:
    cr1, cr2, cr3, brr = (words[USART1 + x] for x in (0, 4, 8, 12))
    cfgr, pll, ccipr = (words[RCC + x] for x in (8, 12, 0x88))
    # The production board uses a 24 MHz HSE. Refuse unknown clock trees
    # instead of silently assuming that every BRR is driven by 170 MHz.
    known_clock = ((cfgr >> 2) & 3) == 3 and (pll & 3) == 3
    m, n, divider = ((pll >> 4) & 15) + 1, (pll >> 8) & 127, 2 * (((pll >> 25) & 3) + 1)
    hpre, ppre = (cfgr >> 4) & 15, (cfgr >> 11) & 7
    known_clock = known_clock and hpre == 0 and ppre == 0 and (ccipr & 3) in (0, 1)
    kernel = 24_000_000 * n / m / divider if known_clock else None
    oversample_16 = not bool(cr1 & (1 << 15))
    prescaler_one = words[USART1 + 0x2C] == 0
    baud = kernel / brr if kernel and brr and oversample_16 and prescaler_one else None
    baud_error = abs(baud / 115200 - 1) * 100 if baud else None
    checks = {
        "known_HSE_clock_tree": known_clock,
        "USART_enabled_TX_RX": (cr1 & 13) == 13,
        "8_bit_no_parity": (cr1 & ((1 << 28) | (1 << 12) | (1 << 10))) == 0,
        "one_stop_bit": (cr2 & (3 << 12)) == 0,
        "oversampling_16": oversample_16,
        "majority_voting_NOT_ONEBIT": not bool(cr3 & (1 << 11)),
        "prescaler_one": prescaler_one,
        "baud_error_below_0_1_percent": baud_error is not None and baud_error < .1,
        "RX_interrupt_enabled": bool(cr1 & (1 << 5)),
        "hardware_errors_interrupt_enabled": bool(cr3 & 1),
        "FIFO_enabled": bool(cr1 & (1 << 29)),
        "no_RTS_CTS": (cr3 & ((1 << 8) | (1 << 9))) == 0,
        "PB6_PB7_AF7": all(((words[GPIOB + 0x20] >> (pin * 4)) & 15) == 7 for pin in (6, 7)),
        "PB6_PB7_alternate_mode": all(((words[GPIOB] >> (pin * 2)) & 3) == 2 for pin in (6, 7)),
        "PB6_PB7_pullups": all(((words[GPIOB + 0x0C] >> (pin * 2)) & 3) == 1 for pin in (6, 7)),
        "PWM_MOE_off": not bool(words[TIM1 + 0x44] & (1 << 15)),
        "BKIN_enabled": bool(words[TIM1 + 0x44] & (1 << 12)),
        "core_not_halted": not bool(words[DHCSR] & (1 << 17)),
    }
    return {"pass": all(checks.values()), "checks": checks,
            "nominal_kernel_hz": kernel, "nominal_baud": baud,
            "nominal_baud_error_percent": baud_error,
            "clock_note": "24 MHz HSE nominal; does not measure oscillator tolerance or Uno Q timing",
            "registers": {hex(k): hex(v) for k, v in words.items()}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=30)
    args = parser.parse_args()
    if not 5 <= args.seconds <= 120:
        parser.error("seconds must be 5..120")
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {"pass": False, "scope": "idle UART configuration and link audit, not an energized EMI test",
              "commands_sent": [], "hardware_noise_source_identified": False,
              "utc": datetime.now(timezone.utc).isoformat(), "samples": []}
    h = WifiHmi("http://192.168.1.138:8080", "", [], via_wsl=True)
    try:
        before = h.status()
        report["before"] = before
        verify_unpowered_preflash(before)
        if (before.get("fw_build"), before.get("mc_fw_build")) != (2026100707, 2026100707):
            raise RuntimeError("unsupported firmware identity")
        command = ["C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe",
                   "-c", "port=SWD", "mode=HOTPLUG", "sn=003A002C3335510933383531"]
        for address, size in READ_BLOCKS:
            command.extend(("-r32", hex(address), str(size)))
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=25)
        (out / "registers.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError("read-only ST-Link access failed")
        report["runtime"] = decode(parse_registers(result.stdout))
        deadline = time.monotonic() + args.seconds
        while True:
            s = h.status()
            report["samples"].append(s)
            verify_unpowered_preflash(s)
            if time.monotonic() >= deadline:
                break
            time.sleep(.5)
        samples = [before, *report["samples"]]
        counters = ("bp_bad", "bp_bad_cnt", "mc_bad_sequence", "mc_bad_integrity")
        report["no_new_errors"] = all(s.get(k) == before.get(k) for s in samples for k in counters)
        report["identities_stable"] = all((s.get("fw_build"), s.get("mc_fw_build")) == (2026100707, 2026100707) for s in samples)
        report["controller_messages_delta"] = report["samples"][-1]["bp_good_cnt"] - before["bp_good_cnt"]
        report["pass"] = (report["runtime"]["pass"] and report["no_new_errors"]
                          and report["identities_stable"] and report["controller_messages_delta"] > 0)
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        h.close()
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in ("pass", "error", "runtime", "no_new_errors", "controller_messages_delta")}, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
