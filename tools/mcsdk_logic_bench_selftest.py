"""Test all safety boundaries of the unpowered-only MCSDK fixture."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from prepare_mcsdk_logic_bench import FIXTURE_STATE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    preamble = r'''
#include <cstdint>
#include <cassert>
#include <cstdio>
#define MC_DP_FAULT 0x400U
#define MC_UNDER_VOLT 4U
#define TIM_BDTR_MOE 0x8000U
struct { struct { uint16_t ConversionFactor; } _Super; } BusVoltageSensor_M1={{500}};
struct Timer { uint32_t BDTR; } timer;
#define TIM1 (&timer)
uint32_t now_ms, observed_v;
uint32_t HAL_GetTick() { return now_ms; }
template<class T> uint16_t VBS_GetAvBusVoltage_V(T *) { return observed_v; }
void LL_TIM_DisableAllOutputs(Timer *p) { p->BDTR &= ~TIM_BDTR_MOE; }
'''
    cases = r'''
void reset() {
 now_ms=observed_v=0; timer.BDTR=0;
 mic_bench_last_adc_ms=mic_bench_adc_samples=0; mic_bench_interlock_fault=false;
 mic_bench_raw_index=0; mic_bench_raw_sum=0; mic_bench_zero_observed=false;
 for(auto &sample : mic_bench_raw_window) sample=0;
 mic_bench_run_started_ms=0; mic_bench_run_tracking=false;
}
void ready() { for(unsigned i=0;i<32;++i) mic_logic_bench_observe_bus(0,4); }
int main() {
 reset(); assert(!mic_logic_bench_bus_ready());
 for(unsigned i=0;i<31;++i) assert(mic_logic_bench_observe_bus(0,4)==4);
 assert(!mic_logic_bench_bus_ready());
 assert(mic_logic_bench_observe_bus(0,4)==0 && mic_logic_bench_bus_ready());
 assert(mic_logic_bench_observe_bus(0,0x416)==0x412); // DP, OV and temperature retained
 reset(); ready(); now_ms=20;
 assert(mic_logic_bench_observe_bus(UINT16_MAX,4)==0);
 now_ms=21; timer.BDTR=TIM_BDTR_MOE;
 assert(mic_logic_bench_observe_bus(UINT16_MAX,4)&MC_DP_FAULT);
 assert(!timer.BDTR && !mic_logic_bench_bus_ready());
 assert(mic_logic_bench_observe_bus(0,4)&MC_DP_FAULT); // no automatic restart
 for(unsigned raw=0;raw<1000;++raw) {
  reset(); ready(); timer.BDTR=TIM_BDTR_MOE;
  uint16_t fault=mic_logic_bench_observe_bus((uint16_t)raw,4);
  assert(fault==0 && timer.BDTR); // raw pickup is recorded, never relabelled as a voltage
 }
 for(unsigned voltage=0;voltage<=450;++voltage) {
  reset(); ready(); timer.BDTR=TIM_BDTR_MOE; observed_v=voltage;
  uint16_t fault=mic_logic_bench_observe_bus(0,4);
  assert(bool(fault&MC_DP_FAULT)==(voltage>2));
  assert(bool(timer.BDTR)==(voltage<=2));
 }
 reset(); ready(); observed_v=3; assert(!mic_logic_bench_bus_ready());
 // MCSDK RVBS_Init seeds the filtered voltage near nominal before any ADC sample.
 reset(); observed_v=295;
 for(unsigned n=0;n<1000;++n) assert(!(mic_logic_bench_observe_bus(0,4)&MC_DP_FAULT));
 assert(!mic_logic_bench_bus_ready() && !mic_bench_interlock_fault);
 observed_v=0; assert(mic_logic_bench_observe_bus(0,4)==0 && mic_logic_bench_bus_ready());
 reset(); ready(); timer.BDTR=TIM_BDTR_MOE;
 mic_logic_bench_observe_bus(0,0);
 now_ms=14999; assert(mic_logic_bench_observe_bus(0,0)==0);
 now_ms=15000; assert(mic_logic_bench_observe_bus(0,0)&MC_DP_FAULT);
 assert(!timer.BDTR);
 reset(); ready(); now_ms=UINT32_MAX-10;
 mic_logic_bench_observe_bus(0,0); now_ms+=20;
 assert(mic_logic_bench_observe_bus(UINT16_MAX,4)==0);
 ++now_ms; assert(mic_logic_bench_observe_bus(UINT16_MAX,4)&MC_DP_FAULT);
 reset(); ready(); now_ms=UINT32_MAX-100; timer.BDTR=TIM_BDTR_MOE;
 mic_logic_bench_observe_bus(0,0); now_ms+=15000;
 assert(mic_logic_bench_observe_bus(0,0)&MC_DP_FAULT);
 std::puts("fixture boundaries, 1000 diagnostic raw values, 451 filtered voltages, stale ADC and uint32 wrap passed");
}
'''
    unit = out / "fixture_test.cpp"
    unit.write_text(preamble + FIXTURE_STATE + cases)
    compiler = shutil.which("g++")
    if not compiler:
        raise RuntimeError("g++ required")
    with tempfile.TemporaryDirectory() as folder:
        exe = Path(folder) / "test.exe"
        built = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                                str(unit), "-o", str(exe)], capture_output=True, text=True)
        (out / "compile.log").write_text(built.stdout + built.stderr)
        if built.returncode:
            raise RuntimeError("fixture compilation failed")
        run = subprocess.run([str(exe)], capture_output=True, text=True)
        (out / "run.log").write_text(run.stdout + run.stderr)
    report = {"pass": run.returncode == 0, "raw_values_tested": 1000, "filtered_voltages_tested": 451,
              "scope": "host fixture interlock test; not a physical voltage injection"}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
