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


def prepare(root: Path, out: Path, *, production_build: int = 2026100707,
            bench_build: int = BENCH_BUILD) -> dict:
    source = root / "mcsdk_reference/AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV"
    allowed_pairs = {(2026100707, BENCH_BUILD), (2026100801, 2026100899)}
    if (production_build, bench_build) not in allowed_pairs:
        raise RuntimeError("Unreviewed production/fixture build pair")
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
    main.write_text(text, encoding="utf-8")

    tasks = target / "Src/mc_tasks.c"
    text = tasks.read_text(encoding="utf-8-sig")
    text = replace_once(text, "__weak void TSK_SafetyTask_PWMOFF(uint8_t bMotor)",
                        FIXTURE_STATE + "\n__weak void TSK_SafetyTask_PWMOFF(uint8_t bMotor)")
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
    files = [p.relative_to(source) for p in source.rglob("*") if p.is_file()
             and not any(x in ("Debug", "Release", ".metadata") for x in p.relative_to(source).parts)]
    mismatches = [str(p) for p in files if p not in changed and
                  (source / p).read_bytes() != (target / p).read_bytes()]
    if mismatches:
        raise RuntimeError("Unexpected clone differences: " + str(mismatches))
    report = {
        "pass": True, "purpose": "ISOLATED ZERO-BUS LOGIC ONLY; NOT FOR HV OR MOTOR",
        "bench_build": bench_build, "production_build": production_build,
        "project": str(target), "production_untouched": True,
        "unchanged_files": len(files) - len(changed),
        "changed_files": {str(p): {"production_sha256": hashlib.sha256((source / p).read_bytes()).hexdigest(),
                                  "bench_sha256": hashlib.sha256((target / p).read_bytes()).hexdigest()}
                          for p in sorted(changed)},
        "critical_sources_identical": {
            str(p): hashlib.sha256((target / p).read_bytes()).hexdigest() for p in (
                Path("Src/stm32g4xx_mc_it.c"), Path("Src/stm32g4xx_hal_msp.c"),
                Path("Src/pwm_curr_fdbk.c"), Path("Inc/drive_parameters.h"),
                Path("MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLibACIM/Any/Src/pwm.c"))},
        "bench_only_changes": ["separate build identity", "real ADC zero-bus interlock and 15 s output cap",
                               "zero-bus ready instead of HV settle", "310 V virtual modulation normalization"],
        "hardware_validated": False,
        "operator_measured_bus_max_v": 2,
        "fixture_mcsdk_filtered_voltage_limit_v": 2,
        "raw_ADC_is_diagnostic_only": True,
    }
    (out / "fixture_manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--production-build", type=int, default=2026100707)
    parser.add_argument("--bench-build", type=int, default=BENCH_BUILD)
    args = parser.parse_args()
    report = prepare(Path(__file__).resolve().parents[1], args.outdir,
                     production_build=args.production_build, bench_build=args.bench_build)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
