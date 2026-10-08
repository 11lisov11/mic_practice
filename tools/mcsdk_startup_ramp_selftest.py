"""Offline startup contract and quantized ramp model; no board commands."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import math


def quantized_ramp(target_hz, cascading):
    # Model the documented MCSDK ramp re-target semantics: the current value
    # is quantized to SPEED_UNIT before each re-target. This is not a motor model.
    reference = 0.0
    increment = 0.0
    remaining = 0
    last_target = None
    programs = 0
    samples = {}
    for tick in range(5001):
        seconds = tick / 500.0
        if tick % 25 == 0:
            command = min(target_hz, seconds * 5.0) if cascading else target_hz
            target = int(command * 10 + 1e-9)
            if target != last_target:
                current = math.floor(reference + 1e-9)
                reference = float(current)
                duration = max(3000, math.ceil(abs(target - current) * 20))
                remaining = duration * 500 // 1000 + 1
                increment = (target - current) / remaining
                last_target = target
                programs += 1
        if remaining > 1:
            reference += increment
            remaining -= 1
        elif remaining == 1:
            reference = float(last_target)
            remaining = 0
        if tick in (500, 1000, 1500, 2000, 5000):
            samples[str(seconds)] = round(math.floor(reference + 1e-9) / 10, 3)
    return {"ramp_programs": programs, "electrical_reference_hz": samples}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    uno = (root/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text(encoding='utf-8-sig')
    source = (root/'mcsdk_reference/AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV/Src/main.c').read_text(encoding='utf-8-sig')
    assert 'unoq_scalar_wire_frequency(mcsdk_scalar, g_freq_cmd, g_freq_ref)' in uno
    assert 'unoq_local_current_trip(NUCLEO_MCSDK_ACIM_BACKEND, g_offset_ready,' in uno
    ramp = re.search(r'static uint16_t uno_speed_ramp_ms\(int16_t target\) \{.*?\n\}', source, re.S).group()
    program = '''#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include "mcsdk_supervisory.h"
#define SPEED_UNIT 10
#define POLE_PAIR_NUM 1
enum { IDLE, RUN, UNO_MAX_RAMP_HZ_PER_S=5, UNO_SPEED_RAMP_MS=3000 };
int state=IDLE; int16_t current=0;
int MC_GetSTMStateMotor1() { return state; }
int16_t MC_GetMecSpeedReferenceMotor1() { return current; }
unsigned cases=0;
void check(bool ok) { ++cases; if (!ok) std::abort(); }
''' + ramp + '''
int main() {
 for (int t=1;t<=500;++t) for(int c=0;c<=500;++c) {
  state=RUN; current=c;
  unsigned d=uno_speed_ramp_ms(t), delta=std::abs(t-c);
  check(d>=3000 && delta*1000U<=d*50U);
 }
 state=IDLE; current=500;
 check(uno_speed_ramp_ms(100)==3000);
 check(uno_speed_ramp_ms(500)==10000);
 for(unsigned i=0;i<=60;++i) {
  float ref=i*.25f;
  check(unoq_scalar_wire_frequency(true,10,ref)==10);
  check(unoq_scalar_wire_frequency(false,10,ref)==ref);
 }
 for (bool calibrated : {false,true}) for(bool enabled : {false,true}) {
  check(!unoq_local_current_trip(true,calibrated,enabled,100,-100,100,6));
  check(unoq_local_current_trip(false,calibrated,enabled,7,0,0,6)==(calibrated&&enabled));
  check(!unoq_local_current_trip(false,calibrated,enabled,6,-6,6,6));
 }
 std::printf("%u",cases);
}
'''
    # initializer lists are used only by the host test.
    program = '#include <initializer_list>\n' + program
    compiler = shutil.which('g++')
    if not compiler:
        raise RuntimeError('g++ is required')
    with tempfile.TemporaryDirectory() as tmp:
        unit, exe = Path(tmp)/'test.cpp', Path(tmp)/'test.exe'
        unit.write_text(program, encoding='utf-8')
        subprocess.run([compiler,'-std=c++17','-Wall','-Wextra','-Werror',
                        '-I',str(root/'UNOQ_MOTOR'),str(unit),'-o',str(exe)],check=True)
        cases = int(subprocess.check_output([str(exe)],text=True))
    old, new = quantized_ramp(10,True), quantized_ramp(10,False)
    assert old['ramp_programs'] > 1 and new['ramp_programs'] == 1
    assert new['electrical_reference_hz']['4.0'] == 10
    assert old['electrical_reference_hz']['3.0'] < new['electrical_reference_hz']['3.0']
    report = {'pass':True,'scope':'production helpers + mathematical ramp semantics, no physical PWM/motor',
              'native_assertions':cases,'old_cascaded_ramp':old,'single_owner_ramp':new,
              'motor_rotation_proven':False,'current_protection_note':'legacy UNO ADC trip retained only for non-MCSDK topology; IPM/MCSDK guards untouched'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
