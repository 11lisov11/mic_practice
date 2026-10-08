"""Compile real MCSDK SD IRQ/DP routines against deterministic host stubs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def function(source, name):
    pattern = r"(?:__weak\s+)?(?:void\s*\*|void|uint16_t)\s*" + name + r"\([^;]*?\)\s*\{.*?^\}"
    match = re.search(pattern, source, re.M | re.S)
    if match is None:
        raise RuntimeError("Cannot extract " + name)
    return match[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    project = root / "mcsdk_reference/AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV"
    irq = project / "Src/stm32g4xx_mc_it.c"
    library = project / "Src/pwm_curr_fdbk.c"
    types = project / "Inc/mc_type.h"
    defs = types.read_text(encoding="utf-8-sig")
    constants = {}
    for name in ("MC_NO_FAULTS", "MC_OVER_VOLT", "MC_OVER_CURR", "MC_DP_FAULT"):
        match = re.search(r"#define\s+" + name + r"\s+\(\(uint16_t\)(0x[0-9a-fA-F]+)\)", defs)
        if match is None:
            raise RuntimeError("Missing " + name)
        constants[name] = match[1]
    program = r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
#define __weak
struct TIM_TypeDef { uint32_t flags; uint32_t moe; bool bie, level; } timer;
#define TIM1 (&timer)
struct PWMC_Handle_t {
 bool OverVoltageFlag, OverCurrentFlag, driverProtectionFlag, BrakeActionLock;
 uint8_t Motor;
};
struct { PWMC_Handle_t _Super; } PWM_Handle_M1;
unsigned off_calls, ovp_calls, scheduler_calls;
bool LL_TIM_IsActiveFlag_BRK(TIM_TypeDef *t) { return (t->flags & 1) != 0; }
bool LL_TIM_IsActiveFlag_BRK2(TIM_TypeDef *t) { return (t->flags & 2) != 0; }
void LL_TIM_ClearFlag_BRK(TIM_TypeDef *t) { if (!t->level) t->flags &= ~1U; }
void LL_TIM_ClearFlag_BRK2(TIM_TypeDef *t) { if (!t->level) t->flags &= ~2U; }
void LL_TIM_DisableIT_BRK(TIM_TypeDef *t) { t->bie = false; }
void PWMC_SwitchOffPWM(PWMC_Handle_t *) { ++off_calls; timer.moe = 0; }
void PWMC_OVP_Handler(PWMC_Handle_t *p, TIM_TypeDef *) {
 ++ovp_calls; p->OverVoltageFlag = true; p->BrakeActionLock = true;
}
void MC_Scheduler() { ++scheduler_calls; }
"""
    program += "\n" + "\n".join(f"#define {k} ((uint16_t){v})" for k, v in constants.items())
    lib = library.read_text(encoding="utf-8-sig")
    program += "\n" + function(lib, "PWMC_DP_Handler")
    program += "\n" + function(lib, "PWMC_IsFaultOccurred")
    program += "\n" + function(irq.read_text(encoding="utf-8-sig"), "TIMx_BRK_M1_IRQHandler")
    program += r"""
int main() {
 for (unsigned flags=0; flags<4; ++flags) {
  PWM_Handle_M1 = {}; timer = {flags, 1, true, false};
  off_calls=ovp_calls=scheduler_calls=0;
  TIMx_BRK_M1_IRQHandler();
  assert(timer.flags==0 && ovp_calls==0 && scheduler_calls==1);
  assert(timer.bie == (flags==0));
  assert(!PWM_Handle_M1._Super.BrakeActionLock);
  assert(!PWM_Handle_M1._Super.OverVoltageFlag);
  if (flags) {
   assert(timer.moe==0 && off_calls==((flags&1U)+((flags>>1U)&1U)));
   assert(PWMC_IsFaultOccurred(&PWM_Handle_M1._Super)==MC_DP_FAULT);
   assert(PWMC_IsFaultOccurred(&PWM_Handle_M1._Super)==MC_NO_FAULTS);
  } else {
   assert(timer.moe==1 && off_calls==0);
   assert(PWMC_IsFaultOccurred(&PWM_Handle_M1._Super)==MC_NO_FAULTS);
  }
 }
 PWM_Handle_M1={}; timer={1,1,true,true}; off_calls=ovp_calls=scheduler_calls=0;
 for (unsigned tick=0; tick<1000; ++tick) {
  if (timer.bie && timer.flags) TIMx_BRK_M1_IRQHandler();
 }
 assert(!timer.bie && timer.flags==1 && timer.moe==0 && off_calls==1 && scheduler_calls==1);
 assert(PWMC_IsFaultOccurred(&PWM_Handle_M1._Super)==MC_DP_FAULT);
 timer.level=false;
 assert(!timer.bie && timer.moe==0);
 std::puts("4 SD IRQ combinations and sustained-level interrupt starvation regression passed");
}
"""
    compiler = shutil.which("g++")
    if not compiler:
        raise RuntimeError("g++ is required")
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    # Generated translation unit embeds the unchanged real library routines.
    (out / "host_test.cpp").write_text(program, encoding="utf-8")
    with tempfile.TemporaryDirectory() as folder:
        executable = Path(folder) / "test.exe"
        result = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                                 str(out / "host_test.cpp"), "-o", str(executable)],
                                text=True, capture_output=True)
        (out / "compile.log").write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError("Host compilation failed")
        run = subprocess.run([str(executable)], text=True, capture_output=True)
        (out / "run.log").write_text(run.stdout + run.stderr)
    report = {"pass": run.returncode == 0, "cases": 5,
              "scope": "real source routines with host stubs, not physical BKIN qualification",
              "sources": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (irq, library, types)}}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"pass": report["pass"], "cases": 5}, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
