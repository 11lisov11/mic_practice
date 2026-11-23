"""Clone the active MCSDK project into an explicitly unpowered-only fixture."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


BENCH_BUILD = 2026100799
BENCH_BUS_READY = '''static void uno_update_softstart_state(uint32_t now_ms) {
  (void)now_ms;
  /* Only this isolated fixture replaces the external soft-start wait. */
  uno_link.softstart_ready = mic_logic_bench_bus_ready();
  uno_link.softstart_tracking = false;
}
'''

FIXTURE_STATE = '''
/* UNPOWERED MCSDK FIXTURE ONLY. Never flash this image for a powered drive.
   ADC telemetry stays real; only V/f modulation normalization uses virtual 310 V.
   Operator-measured bus must be <2 V. Use the same filtered voltage as MCSDK;
   an unpowered board's raw ADC pickup is not an independent voltage sensor. */
static volatile uint32_t mic_bench_last_adc_ms;
static volatile uint16_t mic_bench_adc_samples;
static volatile bool mic_bench_interlock_fault;
static volatile uint16_t mic_bench_adc_raw_last;
static volatile uint16_t mic_bench_adc_raw_max;
static volatile uint8_t mic_bench_interlock_reason;
static volatile bool mic_bench_zero_observed;
static uint16_t mic_bench_raw_window[32];
static uint8_t mic_bench_raw_index;
static volatile uint32_t mic_bench_raw_sum;
static uint32_t mic_bench_run_started_ms;
static bool mic_bench_run_tracking;

bool mic_logic_bench_bus_ready(void) {
  /* Read the ISR timestamp before the clock to avoid a preemption-age wrap. */
  const uint32_t last_adc = mic_bench_last_adc_ms;
  const uint32_t now = HAL_GetTick();
  return !mic_bench_interlock_fault && mic_bench_zero_observed &&
         mic_bench_adc_samples >= 32U &&
         (uint32_t)(now - last_adc) <= 20U &&
         VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super) <= 2U;
}

static uint16_t mic_logic_bench_observe_bus(uint16_t raw, uint16_t faults) {
  const uint32_t now = HAL_GetTick();
  if (raw != UINT16_MAX) {
    mic_bench_adc_raw_last = raw;
    if (raw > mic_bench_adc_raw_max) mic_bench_adc_raw_max = raw;
    mic_bench_last_adc_ms = now;
    if (mic_bench_adc_samples != UINT16_MAX) ++mic_bench_adc_samples;
    mic_bench_raw_sum -= mic_bench_raw_window[mic_bench_raw_index];
    mic_bench_raw_window[mic_bench_raw_index] = raw;
    mic_bench_raw_sum += raw;
    mic_bench_raw_index = (mic_bench_raw_index + 1U) & 31U;
    const uint16_t filtered_v = VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super);
    if (mic_bench_adc_samples >= 32U && filtered_v <= 2U) {
      mic_bench_zero_observed = true;
    }
    /* RVBS_Init seeds its filter near nominal. Wait for a measured zero
       before using a later nonzero filtered voltage as a latched interlock. */
    if (mic_bench_zero_observed && filtered_v > 2U) {
      mic_bench_interlock_fault = true;
      mic_bench_interlock_reason = 1U;
    }
  }
  if (mic_bench_adc_samples >= 32U &&
      (uint32_t)(now - mic_bench_last_adc_ms) > 20U) {
    mic_bench_interlock_fault = true;
    mic_bench_interlock_reason = 2U;
  }
  if ((TIM1->BDTR & TIM_BDTR_MOE) != 0U) {
    if (!mic_bench_run_tracking) {
      mic_bench_run_tracking = true;
      mic_bench_run_started_ms = now;
    } else if ((uint32_t)(now - mic_bench_run_started_ms) >= 15000U) {
      mic_bench_interlock_fault = true;
      mic_bench_interlock_reason = 3U;
    }
  } else {
    mic_bench_run_tracking = false;
  }
  if (mic_bench_interlock_fault) {
    LL_TIM_DisableAllOutputs(TIM1);
    return faults | MC_DP_FAULT;
  }
  if (mic_logic_bench_bus_ready()) {
    /* Undervoltage is expected ONLY in this detached, zero-bus fixture. */
    return faults & (uint16_t)~MC_UNDER_VOLT;
  }
  return faults;
}
'''


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError("Expected one fixture anchor: " + old[:80])
    return text.replace(old, new, 1)


def function_span(text: str, name: str) -> tuple[int, int]:
    match = re.search(r"static void " + name + r"\([^;]*?\)\s*\{", text)
    if not match:
        raise RuntimeError("Missing " + name)
    # This known function has no braces embedded in strings or comments.
    depth = 1
    end = match.end()
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return match.start(), end


def fixture_state(bus_limit_v: int = 2) -> str:
    if type(bus_limit_v) is not int or bus_limit_v not in (2, 10):
        raise ValueError("Only isolated 2 V and auxiliary-only 10 V fixtures are supported")
    if bus_limit_v == 2:
        return FIXTURE_STATE
    return FIXTURE_STATE.replace("<= 2U", "<= 10U").replace(
        "> 2U", "> 10U").replace(
        "UNPOWERED MCSDK FIXTURE ONLY. Never flash this image for a powered drive.",
        "AUXILIARY-ONLY MCSDK FIXTURE. J1 and motor must be disconnected.").replace(
        "Operator-measured bus must be <2 V.",
        "Filtered ADC bus must remain <=10 V; no external DC source is permitted.").replace(
        "before using a later nonzero filtered voltage as a latched interlock.",
        "before using a later above-limit voltage as a latched interlock.")


def prepare(root: Path, out: Path, *, production_build: int = 2026100707,
            bench_build: int = BENCH_BUILD, bus_limit_v: int = 2,
            automatic_sd_pulse: bool = False, source_override: Path | None = None) -> dict:
    source = root / "mcsdk_reference/AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV"
    allowed_pairs = {(2026100707, BENCH_BUILD), (2026100801, 2026100899), (2026101006, 2026101099)}
    if (production_build, bench_build) not in allowed_pairs:
        raise RuntimeError("Unreviewed production/fixture build pair")
    if source_override is not None:
        source = source_override.resolve(strict=True)
        if (production_build, bench_build) != (2026101006, 2026101099) or not source.is_relative_to(root.resolve()):
            raise RuntimeError("Unreviewed fixture source override")
    elif production_build == 2026101006:
        raise RuntimeError("UART v3 fixture requires its reviewed production snapshot")
    state = fixture_state(bus_limit_v)
    if bus_limit_v != 2 and (production_build, bench_build) != (2026100801, 2026100899):
        raise RuntimeError("Auxiliary-only fixture requires reviewed 801/899 protocol pair")
    if automatic_sd_pulse and bus_limit_v != 10:
        raise RuntimeError("External GPIO SD stimulus requires auxiliary-only 10 V fixture")
    text = (source / "Src/main.c").read_text(encoding="utf-8-sig")
    build_match = re.search(r'#define MIC_NUCLEO_FW_BUILD_ID (\d+)UL', text)
    if not build_match or int(build_match[1]) != production_build:
        raise RuntimeError(f"Expected audited Nucleo {production_build} source")
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    target = out / "project"
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("Debug", "Release", ".metadata"))
    main = target / "Src/main.c"
    text = main.read_text(encoding="utf-8-sig")
    text = replace_once(text, build_match[0],
                        f"#define MIC_NUCLEO_FW_BUILD_ID {bench_build}UL")
    text = replace_once(text, "static void uno_link_init(void);",
                        "static void uno_link_init(void);\nbool mic_logic_bench_bus_ready(void);")
    begin, end = function_span(text, "uno_update_softstart_state")
    text = text[:begin] + BENCH_BUS_READY + text[end:]
    if automatic_sd_pulse:
        init = '''  /* External test wire only: PC8 -> 1k -> STEVAL TP23. */
  HAL_GPIO_WritePin(GPIOC, GPIO_PIN_8, GPIO_PIN_SET);
  GPIO_InitStruct.Pin = GPIO_PIN_8;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_OD;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);
'''
        text = replace_once(text, "  /* USER CODE BEGIN MX_GPIO_Init_2 */",
                            "  /* USER CODE BEGIN MX_GPIO_Init_2 */\n" + init)
    main.write_text(text, encoding="utf-8")

    tasks = target / "Src/mc_tasks.c"
    text = tasks.read_text(encoding="utf-8-sig")
    if automatic_sd_pulse:
        state = '#include "aux_sd_pulse.h"\nstatic MicBenchSdPulse mic_bench_sd_pulse;\n' + state
        pulse = '''  /* This pin is an external stimulus; never substitute a TIM1 BG event. */
  const bool pull_sd = mic_bench_sd_pull(&mic_bench_sd_pulse, now,
      (TIM1->BDTR & TIM_BDTR_MOE) != 0U, mic_logic_bench_bus_ready());
  HAL_GPIO_WritePin(GPIOC, GPIO_PIN_8, pull_sd ? GPIO_PIN_RESET : GPIO_PIN_SET);
'''
        state = replace_once(state, "  if (mic_bench_interlock_fault) {",
                             pulse + "  if (mic_bench_interlock_fault) {")
    text = replace_once(text, "__weak void TSK_SafetyTask_PWMOFF(uint8_t bMotor)",
                        state + "\n__weak void TSK_SafetyTask_PWMOFF(uint8_t bMotor)")
    anchor = "CodeReturn |= errMask[bMotor] & RVBS_CalcAvVbus(&BusVoltageSensor_M1, rawValueM1);"
    text = replace_once(text, anchor, anchor +
                        "\n    CodeReturn = mic_logic_bench_observe_bus(rawValueM1, CodeReturn);")
    tasks.write_text(text, encoding="utf-8")

    vf_relative = Path("MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLibACIM/Any/Src/acim_vf_control.c")
    vf = target / vf_relative
    text = vf.read_text(encoding="utf-8-sig")
    text = replace_once(text, "uint16_t hVbus_V = VBS_GetAvBusVoltage_V(pBVS);",
                        "/* Isolated fixture normalization; actual ADC telemetry is unchanged. */\n"
                        "  (void)pBVS;\n  uint16_t hVbus_V = 310U;")
    vf.write_text(text, encoding="utf-8")

    changed = {Path("Src/main.c"), Path("Src/mc_tasks.c"), vf_relative}
    if automatic_sd_pulse:
        pulse_header = Path("Inc/aux_sd_pulse.h")
        shutil.copyfile(root / "tools/fixtures/aux_sd_pulse.h", target / pulse_header)
        changed.add(pulse_header)
    files = [p.relative_to(source) for p in source.rglob("*") if p.is_file()
             and not any(x in ("Debug", "Release", ".metadata") for x in p.relative_to(source).parts)]
    mismatches = [str(p) for p in files if p not in changed and
                  (source / p).read_bytes() != (target / p).read_bytes()]
    if mismatches:
        raise RuntimeError("Unexpected clone differences: " + str(mismatches))
    report = {
        "pass": True, "purpose": "ISOLATED LOGIC ONLY; NOT FOR HV OR MOTOR",
        "fixture_variant": ("auxiliary_only_10v_auto_sd_pc8" if automatic_sd_pulse
                            else "zero_bus" if bus_limit_v == 2 else "auxiliary_only_10v"),
        "external_stimulus": {"gpio": "PC8", "connector": "CN10-2", "type": "open_drain",
                              "resistor_ohm": 1000, "destination": "STEVAL TP23",
                              "after_pwm_ms": 800, "hold_ms": 250, "once_per_boot": True}
                             if automatic_sd_pulse else None,
        "identity_note": "899 identifies the reviewed UART layout; use variant and image hashes for binary identity",
        "bench_build": bench_build, "production_build": production_build,
        "project": str(target), "production_untouched": True,
        "unchanged_files": len(files) - len(set(files) & changed),
        "changed_files": {str(p): {"production_sha256": hashlib.sha256((source / p).read_bytes()).hexdigest()
                                  if (source / p).is_file() else None,
                                  "bench_sha256": hashlib.sha256((target / p).read_bytes()).hexdigest()}
                          for p in sorted(changed)},
        "critical_sources_identical": {
            str(p): hashlib.sha256((target / p).read_bytes()).hexdigest() for p in (
                Path("Src/stm32g4xx_mc_it.c"), Path("Src/stm32g4xx_hal_msp.c"),
                Path("Src/pwm_curr_fdbk.c"), Path("Inc/drive_parameters.h"),
                Path("MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLibACIM/Any/Src/pwm.c"))},
        "bench_only_changes": ["separate test identity",
                               f"real ADC <= {bus_limit_v} V interlock and 15 s output cap",
                               "isolated low-voltage ready instead of HV settle",
                               "310 V virtual modulation normalization"],
        "hardware_validated": False,
        "operator_measured_bus_max_v": 2 if bus_limit_v == 2 else None,
        "fixture_mcsdk_filtered_voltage_limit_v": bus_limit_v,
        "raw_ADC_is_diagnostic_only": True,
    }
    (out / "fixture_manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--production-build", type=int, default=2026100707)
    parser.add_argument("--bench-build", type=int, default=BENCH_BUILD)
    parser.add_argument("--max-bus-v", type=int, choices=(2, 10), default=2,
                        help="10 V variant permits J4 only; J1 and motor remain disconnected")
    parser.add_argument("--automatic-sd-pulse", action="store_true",
                        help="PC8 open-drain external test wire only; no software break injection")
    args = parser.parse_args()
    report = prepare(Path(__file__).resolve().parents[1], args.outdir,
                     production_build=args.production_build, bench_build=args.bench_build,
                     bus_limit_v=args.max_bus_v, automatic_sd_pulse=args.automatic_sd_pulse)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
