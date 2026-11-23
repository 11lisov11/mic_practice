"""Build a 30 s V/f profile and execute the pinned MCSDK ramp on the host; no hardware."""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


SNAPSHOT = "artifacts/live_bench_20261010/uart_v3_candidate/firmware_r6/nucleo"


def plan(maximum_hz=50.0, stop_mode="ramp"):
    if type(maximum_hz) not in (int, float) or not math.isfinite(maximum_hz) or not 5 <= maximum_hz <= 50:
        raise ValueError("profile maximum must be within 5..50 Hz")
    if stop_mode not in ("ramp", "coast"):
        raise ValueError("unknown stop mode")
    deceleration_at = round(28-max(3,(maximum_hz-.1)/5), 3)
    profile = dict(duration_s=30, maximum_electrical_hz=maximum_hz, stop_mode=stop_mode,
        phases=[dict(at_s=0, command="START", target_hz=maximum_hz),
                dict(at_s=deceleration_at, command="SET FREQ", target_hz=0.1),
                dict(at_s=30, command="STOP", target_hz=0)],
        independent_safety_limit_s=33, emergency_heartbeat_timeout_s=3,
        ramp_owner="Nucleo MCSDK", ramp_rate_ceiling_hz_per_s=5,
        note="Nonzero deceleration target avoids immediate zero-frequency PWM shutdown")
    if stop_mode == "coast":
        profile["phases"].pop(1)
        profile["note"] = "PWM off at 30 s; no commanded deceleration or guaranteed rotor standstill time"
    return profile


def regeneration_bound(capacitance_uf, initial_vdc=325.0, maximum_hz=50):
    if capacitance_uf is not None and (not math.isfinite(capacitance_uf) or capacitance_uf <= 0):
        raise ValueError("positive finite DC capacitance required")
    if not math.isfinite(initial_vdc) or not 0 < initial_vdc < 360:
        raise ValueError("initial DC voltage must be within (0,360) V")
    plan(maximum_hz)
    # This is the retained simulation prior, NOT identified motor/load inertia.
    inertia_upper = 0.0004
    kinetic = 0.5 * inertia_upper * (2 * math.pi * maximum_hz) ** 2
    required_uf = 2 * kinetic / (360**2 - initial_vdc**2) * 1e6
    final_vdc = None if capacitance_uf is None else math.sqrt(initial_vdc**2 + 2*kinetic/(capacitance_uf*1e-6))
    return dict(model="lossless full rotor-energy transfer to DC capacitors",
        identified_inertia=False, attached_load_inertia_included=False,
        assumed_inertia_upper_kg_m2=inertia_upper, kinetic_energy_j=kinetic,
        initial_vdc=initial_vdc, comparison_ceiling_vdc=360,
        minimum_capacitance_uf_without_margin=required_uf,
        conditional_envelope_below_ceiling=None if final_vdc is None else final_vdc <= 360,
        entered_capacitance_uf=capacitance_uf, projected_vdc=final_vdc,
        scope="conditional energy envelope, not motor simulation or hardware approval")


def simulate_native(root, profile):
    project = root / SNAPSHOT
    source = project / "MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLib/Any/Src/ramp_ext_mngr.c"
    header = source.parents[1] / "Inc/ramp_ext_mngr.h"
    main = (project / "Src/main.c").read_text(encoding="utf-8-sig")
    match = re.search(r"static uint16_t uno_speed_ramp_ms\(int16_t target\) \{.*?\n\}", main, re.S)
    if not match:
        raise ValueError("pinned receiver ramp helper missing")
    assert "UNO_SPEED_RAMP_MS = 3000U" in main and "UNO_MAX_RAMP_HZ_PER_S = 5U" in main
    unit = r'''#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include "ramp_ext_mngr.h"
#define SPEED_UNIT 10
#define POLE_PAIR_NUM 1
enum {IDLE,RUN,UNO_MAX_RAMP_HZ_PER_S=5,UNO_SPEED_RAMP_MS=3000};
RampExtMngr_Handle_t manager{};
int state=IDLE;
int MC_GetSTMStateMotor1() { return state; }
int16_t MC_GetMecSpeedReferenceMotor1() { return (int16_t)REMNG_GetValue(&manager); }
''' + match.group() + r'''
int main(int argc,char** argv) {
 if(argc!=4) return 2;
 const int16_t maximum=(int16_t)(std::atof(argv[1])*10+.5);
 const unsigned down_tick=(unsigned)(std::atof(argv[2])*500+.5);
 const bool coast=std::atoi(argv[3])!=0;
 manager.FrequencyHz=500; REMNG_Init(&manager);
 uint16_t duration=uno_speed_ramp_ms(maximum);
 if(!REMNG_ExecRamp(&manager,maximum,duration)) return 3;
 state=RUN;
 std::puts("time_s,reference_hz");
 for(unsigned tick=0;tick<15000;++tick) {
  if(!coast && tick==down_tick) {
   duration=uno_speed_ramp_ms(1);
   if(!REMNG_ExecRamp(&manager,1,duration)) return 4;
  }
  int32_t value=REMNG_Calc(&manager);
  std::printf("%.3f,%.1f\n",tick/500.0,value/10.0);
 }
 return REMNG_GetValue(&manager)==(coast ? maximum : 1) ? 0 : 5;
}
'''
    compiler = shutil.which("g++")
    if not compiler:
        raise RuntimeError("g++ required for native MCSDK test")
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copyfile(header, work / header.name)
        (work / "mc_type.h").write_text("#include <stdint.h>\n#include <stdbool.h>\n#define __weak\n#define MC_NULL 0\n")
        (work / "profile.cpp").write_text(unit)
        exe = work / "profile.exe"
        result = subprocess.run([compiler,"-std=c++17","-Wall","-Wextra","-Werror","-x","c++",
            "-I",str(work),str(source),str(work/"profile.cpp"),"-o",str(exe)],capture_output=True,text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        result = subprocess.run([str(exe),str(profile["maximum_electrical_hz"]),
            str(profile["phases"][1]["at_s"]),str(int(profile["stop_mode"]=="coast"))],capture_output=True,text=True)
        if result.returncode:
            raise RuntimeError("native ramp failed: " + str(result.returncode))
    rows = list(csv.DictReader(io.StringIO(result.stdout)))
    frequencies = [float(row["reference_hz"]) for row in rows]
    maximum = profile["maximum_electrical_hz"]
    down_s = profile["phases"][1]["at_s"]
    down_tick = round(down_s*500)
    checks = dict(samples_15000=len(rows)==15000,
        maximum_reached=maximum in frequencies,
        acceleration_monotone=all(a<=b for a,b in zip(frequencies[:down_tick],frequencies[1:down_tick])),
        deceleration_monotone=all(a>=b for a,b in zip(frequencies[down_tick:],frequencies[down_tick+1:])),
        range_valid=all(0<=f<=maximum for f in frequencies),
        terminal_reference=frequencies[-1]==(maximum if profile["stop_mode"]=="coast" else .1),
        quantized_steps_bounded=all(abs(a-b)<=.100001 for a,b in zip(frequencies,frequencies[1:])))
    return result.stdout, dict(pass_=all(checks.values()), checks=checks,
        first_maximum_s=next(float(r["time_s"]) for r in rows if float(r["reference_hz"])==maximum),
        near_zero_s=None if profile["stop_mode"]=="coast" else next(float(r["time_s"]) for r in rows if float(r["time_s"])>=down_s and float(r["reference_hz"])==.1),
        execution_scope="actual MCSDK ramp library and receiver ramp helper with host hardware stubs",
        rotor_speed_verified=False, motor_dynamics_simulated=False,
        source_sha256={str(p.relative_to(root)).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (source,header,project/"Src/main.c")})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--outdir",type=Path,required=True)
    p.add_argument("--maximum-hz",type=float,default=50)
    p.add_argument("--dc-capacitance-uf",type=float)
    p.add_argument("--stop-mode",choices=("ramp","coast"),default="ramp")
    args = p.parse_args()
    profile = plan(args.maximum_hz,args.stop_mode)
    envelope = regeneration_bound(args.dc_capacitance_uf, maximum_hz=args.maximum_hz)
    envelope["applies_to_chosen_stop_mode"] = args.stop_mode=="ramp"
    if args.stop_mode=="coast":
        envelope["note"] = "Full-energy return bound is a sensitivity example, not a prediction of a PWM-off coast"
    csv_text, native = simulate_native(Path(__file__).resolve().parents[1], profile)
    report = dict(prepared=True, pass_=native.pop("pass_"), profile=profile, native_ramp=native,
        regeneration_envelope=envelope, hardware_commands=0, live_execution_available=False,
        hv_release_approved=False, blockers=["Installed gate still permits only 3 s / 10 Hz",
            "Actual DC capacitance and braking/load configuration need confirmation",
            "Ramp reference is not measured rotor speed; current telemetry remains unqualified"])
    report["pass"] = report.pop("pass_")
    out = args.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    (out/"native_ramp.csv").write_text(csv_text,encoding="utf-8")
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("pass","prepared","hardware_commands","live_execution_available")}))
    print(json.dumps({k:native[k] for k in ("first_maximum_s","near_zero_s")}))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
