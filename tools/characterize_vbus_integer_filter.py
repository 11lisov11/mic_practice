"""Characterize unchanged MCSDK Vbus filtering; no board or calibration changes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from ipm_sd_irq_selftest import function


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    project = root/'mcsdk_reference/AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV'
    base = project/'MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLib/Any/Src'
    divider = base/'r_divider_bus_voltage_sensor.c'
    voltage = base/'bus_voltage_sensor.c'
    ratio = float(re.search(r'#define\s+VBUS_PARTITIONING_FACTOR\s+([0-9.]+)',
                           (project/'Inc/power_stage_parameters.h').read_text())[1])
    vref = float(re.search(r'#define\s+ADC_REFERENCE_VOLTAGE\s+([0-9.]+)',
                          (project/'Inc/parameters_conversion.h').read_text())[1])
    factor = int(vref/ratio)
    source = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#define __weak
#define MC_UNDER_VOLT 4U
#define MC_OVER_VOLT 2U
#define MC_NO_FAULTS 0U
#define MC_NO_ERROR 0U
struct BusVoltageSensor_Handle_t { uint16_t ConversionFactor, LatestConv, AvBusVoltage_d, FaultState; };
struct RDivider_Handle_t {
 BusVoltageSensor_Handle_t _Super;
 uint16_t OverVoltageThreshold, OverVoltageThresholdLow;
 bool OverVoltageHysteresisUpDir;
 uint16_t UnderVoltageThreshold;
};
'''
    text = divider.read_text(encoding='utf-8-sig')
    source += function(text, 'RVBS_CheckFaultState')+'\n'
    source += function(text, 'RVBS_CalcAvVbus')+'\n'
    source += function(voltage.read_text(encoding='utf-8-sig'), 'VBS_GetAvBusVoltage_V')+'\n'
    source += r'''
int main() {
 unsigned cases=0, max_error=0; double max_display_error=0;
 for (unsigned code=0; code<4096; ++code) {
  const uint16_t raw=code<<4;
  for (unsigned init : {0U,65535U}) {
   RDivider_Handle_t h{}; h._Super.ConversionFactor=FACTOR;
   h._Super.AvBusVoltage_d=init;
   h.OverVoltageThreshold=h.OverVoltageThresholdLow=65000;
   for (unsigned n=0; n<4096; ++n) RVBS_CalcAvVbus(&h,raw);
   unsigned error=raw-h._Super.AvBusVoltage_d;
   assert(h._Super.AvBusVoltage_d<=raw && error<=255);
   if (init==65535) assert(error==0);
   if (error>max_error) max_error=error;
   double lost=raw*double(FACTOR)/65536-VBS_GetAvBusVoltage_V(&h._Super);
   if (lost>max_display_error) max_display_error=lost;
   auto previous=h._Super.AvBusVoltage_d;
   RVBS_CalcAvVbus(&h,0xFFFF);
   assert(h._Super.AvBusVoltage_d==previous);
   ++cases;
  }
 }
 std::printf("{\"pass\":true,\"constant_input_cases\":%u,\"max_filter_lag_u16\":%u,"
             "\"max_filter_and_integer_display_loss_v\":%.9f}\n",cases,max_error,max_display_error);
}
'''
    source = source.replace('#include <cstdio>', '#include <cstdio>\n#include <initializer_list>')
    source = source.replace('FACTOR', str(factor))
    out = a.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out/'host_test.cpp').write_text(source, encoding='utf-8')
    compiler = shutil.which('g++')
    if not compiler:
        raise RuntimeError('g++ required')
    with tempfile.TemporaryDirectory() as temp:
        exe = Path(temp)/'filter.exe'
        r = subprocess.run([compiler, '-O2', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            str(out/'host_test.cpp'), '-o', str(exe)], capture_output=True, text=True, timeout=30)
        (out/'compile.log').write_text(r.stdout+r.stderr, encoding='utf-8')
        r.check_returncode()
        report = json.loads(subprocess.check_output([str(exe)], text=True, timeout=30))
    report.update(scope='Unchanged SDK functions with host stubs; constant input characterization, not a physical sensor test',
                  conversion_factor=factor, firmware_modified=False, calibration_modified=False,
                  sources={str(s.relative_to(root)):hashlib.sha256(s.read_bytes()).hexdigest()
                           for s in (divider,voltage)})
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
