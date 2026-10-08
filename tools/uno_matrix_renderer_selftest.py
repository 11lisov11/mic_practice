"""Execute the production renderer with the installed core's packing/wrapper."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def generate(root: Path, core: Path) -> tuple[str, list[Path]]:
    sketch = root / "UNOQ_MOTOR/UNOQ_MOTOR.ino"
    source = sketch.read_text(encoding="utf-8-sig")
    globals_ = source[source.index("static Arduino_LED_Matrix g_matrix;"):
                      source.index("#if USE_ROUTER_BRIDGE", source.index("static Arduino_LED_Matrix g_matrix;"))]
    body = source[source.index("static bool matrix_test_active() {"):
                  source.index("static void handle_button() {")]
    preamble = r'''
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <initializer_list>
using byte = uint8_t;
using voidFuncPtr = void(*)();
static uint32_t clock_ms;
uint32_t millis() { return clock_ms; }
void delay(uint32_t) {}
static uint32_t submitted[4];
static unsigned writes;
static bool initialized;
extern "C" {
void matrixBegin() { initialized = true; }
void matrixWrite(const uint32_t* frame) { memcpy(submitted, frame, 16); ++writes; }
}
#include "Arduino_LED_Matrix.h"
static bool g_pwm_enabled, g_estop_latched, g_bp_softstart_ready;
static float g_freq_cmd, g_freq_ref;
static const float POLE_PAIRS = 1;
static const bool NUCLEO_MCSDK_ACIM_BACKEND = true;
static uint8_t g_bp_status;
static const uint8_t BP_STATUS_PWM_ACTIVE = 0x20;
static void matrix_set_pixel(int, int);
static void matrix_draw_digit(int, int, int);
static unsigned checks;
void check(bool condition) { ++checks; if (!condition) { fprintf(stderr,"check %u failed\n",checks); exit(1); } }
bool raw_pixel(int x, int y) {
  int i = y*13 + (12-x);
  return (submitted[i/32] >> (i%32)) & 1;
}
'''
    cases = r'''
// Independent glyph oracle: corrupted production digit tables must not pass.
static const uint8_t expected_digits[10][5] = {
  {7,5,5,5,7}, {2,6,2,2,7}, {7,1,7,4,7}, {7,1,7,1,7}, {5,5,7,1,1},
  {7,4,7,1,7}, {7,4,7,5,7}, {7,1,2,2,2}, {7,5,7,5,7}, {7,5,7,1,7}
};
void check_digit(int x0, int d) {
  for(int y=0;y<5;++y) for(int x=0;x<3;++x)
    check(raw_pixel(x0+x,1+y) == bool((expected_digits[d][y] >> (2-x)) & 1));
}
int main() {
  matrix_init(); check(initialized && g_matrix_ready && writes==1);
  clock_ms=100; matrix_start_test(5000);
  check(matrix_test_active()); clock_ms=5100;
  check(!matrix_test_active() && g_matrix_test_until_ms==0);
  clock_ms=0x80001000; check(!matrix_test_active());
  clock_ms=0U-15000U; matrix_start_test(15000U);
  check(g_matrix_test_until_ms==1 && matrix_test_active());
  clock_ms=2; check(!matrix_test_active());
  clock_ms=0; g_matrix_last_ms=0;
  for(int tenths=0;tenths<=999;++tenths) {
    g_freq_cmd=tenths/10.0f; g_freq_ref=0; clock_ms+=200;
    unsigned old=writes; matrix_update(); check(writes==old+1);
    check_digit(5,(tenths/10)%10); check_digit(9,tenths%10);
    if(tenths>=100) check_digit(1,tenths/100);
    else for(int y=1;y<=5;++y) for(int x=1;x<=3;++x) check(!raw_pixel(x,y));
    check(raw_pixel(8,5) && raw_pixel(8,6));
    old=writes; matrix_update(); check(writes==old);
  }
  g_pwm_enabled=true; g_freq_cmd=20; g_freq_ref=5; clock_ms=202000;
  matrix_update(); check_digit(5,5); check_digit(9,0);
  clock_ms=203000; matrix_update(); check_digit(1,3); check_digit(5,0); check_digit(9,0);
  for(int x=10;x<13;++x) check(raw_pixel(x,7));
  g_pwm_enabled=false; g_bp_softstart_ready=true; g_bp_status=BP_STATUS_PWM_ACTIVE;
  clock_ms+=200; matrix_update(); check(raw_pixel(0,0) && raw_pixel(12,0));
  g_estop_latched=true; clock_ms+=200; matrix_update(); check(!raw_pixel(12,0));
  g_matrix_test_until_ms=clock_ms+15000;
  for(unsigned phase=0;phase<4;++phase) {
    clock_ms+=500; matrix_update();
    for(int i=0;i<4;++i) check(submitted[i]==(((clock_ms/500)&1)?0xffffffffU:0U));
  }
  // The deadline comparison and update interval must survive millis rollover.
  g_matrix_last_ms=0xffffff00U; g_matrix_test_until_ms=0x1000U; clock_ms=0x100U;
  matrix_update(); check(submitted[0]==0);
  g_matrix_test_until_ms=0; g_pwm_enabled=false; g_freq_cmd=20; clock_ms=0x1200;
  matrix_update(); check_digit(1,2); check_digit(5,0); check_digit(9,0);
  printf("{\"pass\":true,\"checks\":%u,\"frequency_values\":1000,\"frames\":{",checks);
  g_bp_softstart_ready=false; g_bp_status=0; g_estop_latched=false;
  bool first=true;
  for(int f : {0,5,20}) {
    g_freq_cmd=float(f); clock_ms+=200; matrix_update();
    printf("%s\"%d\":[%u,%u,%u,%u]",first?"":",",f,submitted[0],submitted[1],submitted[2],submitted[3]);
    first=false;
  }
  printf("}}");
}
'''
    # Refer to the real library, not a reimplementation of its bit ordering.
    return preamble + globals_ + body + cases, [sketch, core]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    core = Path.home() / "AppData/Local/Arduino15/packages/arduino/hardware/zephyr/0.90.0/libraries/Arduino_LED_Matrix/src/Arduino_LED_Matrix.h"
    program, sources = generate(root, core)
    report = {"pass": False, "scope": "actual digit renderer and core 0.90 packing; matrixWrite stubbed",
              "physical_display_verified": False,
              "sources": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    try:
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            (tmp / "Arduino.h").write_text("#pragma once\n", encoding="ascii")
            (tmp / "cmsis_core.h").write_text("#pragma once\n", encoding="ascii")
            unit = args.outdir / "renderer.cpp"
            unit.write_text(program, encoding="utf-8")
            result = subprocess.run([shutil.which("g++") or "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                                     "-I", str(tmp), "-I", str(core.parent), str(unit), "-o", str(tmp / "test.exe")],
                                    capture_output=True, text=True, timeout=60)
            (args.outdir / "compile.log").write_text(result.stdout + result.stderr, encoding="utf-8")
            if result.returncode:
                raise RuntimeError("renderer compilation failed")
            run = subprocess.run([str(tmp / "test.exe")], capture_output=True, text=True, timeout=30)
            if run.returncode:
                raise RuntimeError(run.stderr)
            report.update(json.loads(run.stdout))
            mutations = {
                "SAFE_uses_zero_ramp_instead_of_setpoint": program.replace(
                    "float freq = g_pwm_enabled ? g_freq_ref : g_freq_cmd;", "float freq = g_freq_ref;"),
                "all_digits_drawn_as_zero": program.replace(
                    "uint8_t row = DIGIT_3X5[digit][y];", "uint8_t row = DIGIT_3X5[0][y];"),
            }
            report["mutations_detected"] = {}
            for name, broken in mutations.items():
                if broken == program:
                    raise RuntimeError("Mutation did not alter source: " + name)
                unit.write_text(broken, encoding="utf-8")
                build = subprocess.run([shutil.which("g++") or "g++", "-std=c++17", "-I", str(tmp),
                                        "-I", str(core.parent), str(unit), "-o", str(tmp / "mutation.exe")],
                                       capture_output=True, text=True, timeout=60)
                if build.returncode:
                    raise RuntimeError("Mutation compilation failed: " + name)
                result = subprocess.run([str(tmp / "mutation.exe")], capture_output=True, timeout=30)
                report["mutations_detected"][name] = result.returncode != 0
                if result.returncode == 0:
                    raise RuntimeError("Renderer regression was not detected: " + name)
            unit.write_text(program, encoding="utf-8")
    except Exception as exc:
        report["pass"] = False
        report["error"] = str(exc)
    (args.outdir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
