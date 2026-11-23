"""Prepare an isolated local-stop candidate; never connect to hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from prepare_mcsdk_logic_bench import replace_once
from prepare_ipm_break_wifi import source_hashes

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/live_bench_20261011/ipm_break_wifi/candidate_r6/nucleo"
ASSETS = ROOT / "research/local_stop"
BUILD_ID = 2026101204
PWM = "MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLibACIM/Any/Src/pwm.c"
R3 = "MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLib/G4xx/Src/r3_2_g4xx_pwm_curr_fdbk.c"


def patched_main(text):
    text = replace_once(text, "2026101102UL", f"{BUILD_ID}UL")
    text = replace_once(text, 'GPIO_InitStruct.Mode = GPIO_MODE_IT_FALLING;',
                        'GPIO_InitStruct.Mode = GPIO_MODE_IT_RISING;')
    text = replace_once(text, '#include "uart_v3_transport.h"',
                        (ASSETS / "local_stop.inc").read_text() + '\n#include "uart_v3_transport.h"')
    text = replace_once(text, "  const bool fault = uno_link.fault_latched || mcsdk_fault;",
                        "  const bool local_stop = mic_local_stop_blocked();\n"
                        "  const bool fault = uno_link.fault_latched || mcsdk_fault || local_stop;")
    text = replace_once(text, "  if (link_ok) status |= UNO_STATUS_LINK_OK;",
                        "  if (local_stop) { status |= 0x80U | UNO_STATUS_ESTOP; fault_code = UNO_FAULT_ESTOP; }\n"
                        "  if (link_ok) status |= UNO_STATUS_LINK_OK;")
    text = replace_once(text, "  if (motor_state == RUN) status |= UNO_STATUS_PWM_ACTIVE | UNO_STATUS_SHUTDOWN_RELEASED;",
                        "  if (LL_TIM_IsEnabledAllOutputs(TIM1)) status |= UNO_STATUS_PWM_ACTIVE | UNO_STATUS_SHUTDOWN_RELEASED;")
    text = replace_once(text, "    (void)MC_AcknowledgeFaultMotor1();\n    uno_link.fault_latched = false;",
                        "    (void)MC_AcknowledgeFaultMotor1();\n"
                        "    if (mic_local_stop_latched != 0U && !mic_local_stop_clear()) {\n"
                        "      uno_latch_fault_reason(UNO_FAULT_ESTOP, UNO_DIAG_ESTOP);\n      return;\n    }\n"
                        "    uno_link.fault_latched = false;")
    text = replace_once(text, "  if ((flags & UNO_FLAG_ESTOP) != 0U) {",
                        "  if (mic_local_stop_blocked()) {\n"
                        "    uno_latch_fault_reason(UNO_FAULT_ESTOP, UNO_DIAG_ESTOP);\n    return;\n  }\n\n"
                        "  if ((flags & UNO_FLAG_ESTOP) != 0U) {")
    text = replace_once(text, "static void uno_link_poll(void) {",
                        "static void uno_link_poll(void) {\n"
                        "  if (mic_local_stop_blocked()) uno_latch_fault_reason(UNO_FAULT_ESTOP, UNO_DIAG_ESTOP);")
    return text


def guarded_pwm(text):
    text = replace_once(text, '#include "pwm.h"', '#include "pwm.h"\n#include "local_stop.h"') if '#include "pwm.h"' in text else replace_once(
        text, '#include "r3_2_g4xx_pwm_curr_fdbk.h"',
        '#include "r3_2_g4xx_pwm_curr_fdbk.h"\n#include "local_stop.h"')
    text, count = re.subn(r"LL_TIM_EnableAllOutputs\s*\(", "mic_local_stop_enable_outputs(", text)
    if count not in (1, 5):
        raise RuntimeError("Unexpected MOE publication count")
    return text


def prepare(out):
    before = source_hashes(BASE)
    out.mkdir(parents=True, exist_ok=False)
    project = out / "nucleo"
    shutil.copytree(BASE, project, ignore=shutil.ignore_patterns("Debug", "Release"))
    shutil.copy2(ASSETS / "local_stop.h", project / "Inc/local_stop.h")
    changed = {}
    for name, transform in (("Src/main.c", patched_main), (PWM, guarded_pwm), (R3, guarded_pwm)):
        target = project / name
        target.write_text(transform(target.read_text()), encoding="utf-8")
        changed[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    wire = project / 'Inc/break_wire.h'
    wire.write_text(replace_once(wire.read_text(), 'BW_NUCLEO_BUILD 2026101102UL',
                                f'BW_NUCLEO_BUILD {BUILD_ID}UL'), encoding='utf-8')
    changed['Inc/break_wire.h'] = hashlib.sha256(wire.read_bytes()).hexdigest()
    ioc = next(project.glob('*.ioc'))
    ioc.write_text(replace_once(ioc.read_text(), 'PC13.GPIO_ModeDefaultEXTI=GPIO_MODE_IT_FALLING',
                               'PC13.GPIO_ModeDefaultEXTI=GPIO_MODE_IT_RISING'), encoding='utf-8')
    changed[ioc.name] = hashlib.sha256(ioc.read_bytes()).hexdigest()
    after = source_hashes(project)
    differences = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    if differences != set(changed) | {"Inc/local_stop.h"} or source_hashes(BASE) != before:
        raise RuntimeError("Unexpected source changes")
    report = dict(schema="mic_ai.local_stop_candidate.v1", firmware_build_id=BUILD_ID,
                  baseline_sha256=before, candidate_sha256=after,
                  changed_files=sorted(differences), installed=False,
                  hardware_commands=0, hardware_validated=False, hv_release_approved=False,
                  watchdog_ms=300, run_limit_changed=False)
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--outdir", type=Path, required=True)
    a = p.parse_args()
    r = prepare(a.outdir.resolve())
    print(json.dumps({k:r[k] for k in ("firmware_build_id", "changed_files", "installed")}))
