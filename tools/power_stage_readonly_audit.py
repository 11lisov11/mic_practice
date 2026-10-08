"""Read production break/GPIO registers; never START, halt, reset or flash."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from run_wifi_nucleo_pwm_bench import WifiHmi, verify_unpowered_preflash
from wifi_stop_tail_probe import GPIOA, TIM1, parse_registers

NVIC_ISER0 = 0xE000E100


def break_register_checks(words: dict[int, int]) -> dict:
    try:
        bdtr, af1 = words[TIM1 + 0x44], words[TIM1 + 0x60]
        checks = {
            "MOE_off": not bool(bdtr & (1 << 15)),
            "break_enabled": bool(bdtr & (1 << 12)),
            "break_polarity_high_after_source_inversion": bool(bdtr & (1 << 13)),
            "automatic_output_disabled": not bool(bdtr & (1 << 14)),
            "BKIN_external_source_enabled": bool(af1 & 1),
            "BKIN_source_active_low": bool(af1 & (1 << 9)),
            "break_interrupt_enabled": bool(words[TIM1 + 0x0C] & (1 << 7)),
            "break_NVIC_enabled": bool(words[NVIC_ISER0] & (1 << 24)),
            "PA6_alternate_mode": ((words[GPIOA] >> 12) & 3) == 2,
            "PA6_open_drain": bool(words[GPIOA + 4] & (1 << 6)),
            "PA6_pull_up": ((words[GPIOA + 0x0C] >> 12) & 3) == 1,
            "PA6_AF6_TIM1": ((words[GPIOA + 0x20] >> 24) & 15) == 6,
            "PA6_observed_high": bool(words[GPIOA + 0x10] & (1 << 6)),
        }
    except KeyError:
        return {"pass": False, "checks": {"registers_complete": False}}
    return {"pass": all(checks.values()), "checks": checks,
            "registers": {hex(k): hex(v) for k, v in words.items()}}


def source_checks(root: Path) -> dict:
    project = root / "mcsdk_reference/AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV"
    irq_path = project / "Src/stm32g4xx_mc_it.c"
    irq = irq_path.read_text(encoding="utf-8-sig")
    handler = re.search(r"void TIMx_BRK_M1_IRQHandler\(void\)\s*\{(.*?)\n\}", irq, re.S)
    if not handler:
        raise RuntimeError("Missing break handler")
    body = handler[1]
    power_path = project / "Inc/power_stage_parameters.h"
    power = power_path.read_text(encoding="utf-8-sig")
    values = {}
    for name in ("RSHUNT", "AMPLIFICATION_GAIN", "V0_V", "T0_C", "dV_dT"):
        match = re.search(r"^#define\s+" + name + r"\s+([0-9.]+)", power, re.M)
        if not match:
            raise RuntimeError("Missing power-stage parameter " + name)
        values[name] = float(match[1])
    checks = {"shunt_0_04_ohm": values["RSHUNT"] == 0.04,
              "amplified_current_gain_2_1": values["AMPLIFICATION_GAIN"] == 2.1,
              "temperature_model_is_ST_NTC_profile": values["V0_V"] == 0.408
              and values["T0_C"] == 25 and values["dV_dT"] == 0.025,
              "SD_routes_to_driver_protection_not_OVP": "PWMC_DP_Handler(" in body
              and "PWMC_OVP_Handler(" not in body}
    return {"pass": all(checks.values()), "checks": checks, "values": values,
            "break_handler": body.strip(),
            "source_sha256": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in (irq_path, power_path)},
            "required_physical_configuration": {
                "SW1_SW2_SW4": "1-2: amplified currents", "SW3": "2-3: NTC, not TSO",
                "SW5_SW6": "open: not single-shunt", "SW7_SW8": "closed: three-shunt"}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {"scope": "passive register/source audit; no power-stage qualification",
              "motor_commands_sent": [], "hardware_validated": False, "pass": False}
    hmi = WifiHmi("http://192.168.1.138:8080", "", [], via_wsl=True)
    try:
        before = hmi.status()
        verify_unpowered_preflash(before)
        if before.get("fw_build") != 2026092901 or before.get("mc_fw_build") != 2026100601:
            raise RuntimeError("Unexpected firmware identity")
        report["before"] = before
        report["sources"] = source_checks(root)
        programmer = "C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe"
        command = [programmer, "-c", "port=SWD", "mode=HOTPLUG",
                   "sn=003A002C3335510933383531", "-r32", hex(TIM1), "104",
                   "-r32", hex(GPIOA), "40", "-r32", hex(NVIC_ISER0), "4"]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=15)
        (out / "registers.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError("Read-only ST-Link access failed")
        report["runtime"] = break_register_checks(parse_registers(result.stdout))
        report["after"] = hmi.status()
        verify_unpowered_preflash(report["after"])
        report["pass"] = report["runtime"]["pass"] and report["sources"]["pass"]
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        hmi.close()
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pass": report["pass"], "runtime": report.get("runtime", {}).get("checks"),
                      "sources": report.get("sources", {}).get("checks"),
                      "error": report.get("error")}, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
