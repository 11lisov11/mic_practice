"""Compare our ACIM profile conversion to installed ST Workbench code, offline.

No board access, generation, flashing or use of the fixture as a real motor.
The numerical motor values below are test fixtures, not AIR56B2 measurements.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

from prepare_air56_lso_profile import lso_values
from mcsdk_release_preflight_selftest import profile as test_profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workbench', type=Path, default=Path(
        'C:/Program Files (x86)/STMicroelectronics/MC_SDK_6.4.2/Utilities/PC_Software/STMCWB'))
    args = parser.parse_args()
    js_path = next(p for p in (args.workbench/'assets/www/static/js_css').glob('index-*.js')
                   if 'const S1n=' in p.read_text(encoding='utf-8'))
    source = js_path.read_text(encoding='utf-8')
    # Execute the locally installed vendor's complete motor conversion function.
    start = source.index('const S1n=')
    end = source.index(';globalThis.', start)
    conversion = source[start:end] + ';'
    match = re.search(r'_1n=\(e,t,n\)=>Gl\(wl\(e/1e6\*n,SF\),wl\(t/1e6\*n,SF\)\)', source)
    if match is None:
        raise RuntimeError('ST mechanical unit conversion changed; review before using')
    board = {'M1_RSHUNT': '0.04', 'M1_AMPLIFICATION_GAIN': '2.1', 'ADC_REFERENCE_VOLTAGE': '3.3'}
    ioc = ''.join(f'MotorControl.{k}={v}\n' for k, v in board.items())
    fixtures = []
    for nominal, im in ((1.0, 0.6), (1.24, 0.63), (2.1, 0.9)):
        p = test_profile('nameplate_and_measurement')
        p.update(rated_current_a=nominal, magnetizing_current_rms_a=im,
                 viscous_friction_nm_s=0.0002)
        motor = dict(polesPairs=p['pole_pairs'], Rr=p['rotor_resistance_ohm'],
                     Rs=p['stator_resistance_ohm'], Lls=p['stator_leakage_inductance_h'],
                     Llr=p['rotor_leakage_inductance_h'], Lms=p['magnetizing_inductance_h'],
                     In=nominal, Im=im, Vn=p['rated_line_voltage_v']/math.sqrt(3),
                     Fn=p['rated_frequency_hz'], maxSpeed=1500, inertia=1000, friction=200,
                     label='TEST FIXTURE ONLY', description='not a physical motor')
        fixtures.append(dict(profile=p, motor=motor))
    script = '''
const fs=require('node:fs');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const hT=(e,t)=>t.motor;
const Xo=e=>(name,prefix=false)=>prefix?'M1_'+name:name;
const me=(fallback,value)=>value??fallback;
const Icn=e=>e*Math.sqrt(2);
const Acn=(e,t)=>65536*e*Math.sqrt(2)*t.rsh*t.oagain/t.vdd;
const $e=(value,places=0)=>Number(value.toFixed(places));
const Wr=value=>typeof value==='number'&&Number.isFinite(value);
''' + conversion + '''
process.stdout.write(JSON.stringify(input.fixtures.map(f=>S1n(0,{
motor:f.motor,originalIOC:{MotorControl:input.board}}))));
'''
    result = subprocess.run(['node', '-e', script], input=json.dumps(dict(board=board, fixtures=fixtures)),
                            capture_output=True, text=True, timeout=15, check=True)
    vendor_values = json.loads(result.stdout)
    checks = []
    keys = ('ACIM_NOMINAL_CURRENT', 'ACIM_DEFAULT_FLUX_COMPONENT', 'ACIM_IQMAX', 'IMAGN_A',
            'LM', 'LR', 'M1_LS', 'TAU_S', 'TAU_R', 'SIGMA', 'WB_UI_INERTIA', 'WB_UI_FRICTION')
    for index, (f, vendor) in enumerate(zip(fixtures, vendor_values)):
        ours = lso_values(f['profile'], ioc)
        for key in keys:
            actual, expected = ours['MotorControl.'+key], vendor[key]
            # Iq uses conservative floor, whereas the GUI rounds to nearest.
            tolerance = 1.0 if key == 'ACIM_IQMAX' else 1.1e-7
            checks.append(dict(fixture=index, key=key, actual=actual, workbench=expected,
                               passed=math.isclose(actual, expected, rel_tol=1e-12, abs_tol=tolerance)))
    report = dict(passed=all(row['passed'] for row in checks), checks=checks,
                  workbench_js=str(js_path), workbench_sha256=hashlib.sha256(js_path.read_bytes()).hexdigest(),
                  source_kind='software_test_fixtures', hardware_commands=0,
                  physical_motor_parameters_verified=False,
                  mechanical_units_vendor_expression=match.group(0))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'], checks=len(checks), output=str(args.output)), indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
