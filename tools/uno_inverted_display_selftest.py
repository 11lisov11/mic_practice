"""Execute candidate renderer and real core packing, with an independent glyph oracle."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import prepare_current_peak_capture as package
import uno_bus_display_selftest as bus
import uno_matrix_renderer_selftest as original
from current_peak_capture.display_orientation import OLD, NEW


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--mirror-x', action='store_true', help='Test both-axis compensation using the inverted-board observer model')
    args = parser.parse_args()
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if args.candidate:
        package.OUT=args.candidate.resolve()
        package.NEW=tuple(json.loads((package.OUT/'manifest.json').read_text(encoding='utf-8'))['pair_compatibility_ids'])
    core = Path.home()/'AppData/Local/Arduino15/packages/arduino/hardware/zephyr/0.90.0/libraries/Arduino_LED_Matrix/src/Arduino_LED_Matrix.h'
    program, sources = original.generate(package.OUT, core)
    program = program[:program.index('int main() {')] + bus.CASES
    program = program.replace('static bool matrix_test_active() {', bus.EXTRA_GLOBALS+'\nstatic bool matrix_test_active() {', 1)
    program = program.replace('2026102402U', str(package.NEW[1])+'U')
    # Observer coordinates for the user's inverted board; do not call the
    # production mapper in this oracle. Real library packing remains in use.
    program = program.replace('int i = y*13 + (12-x);', 'int i = (7-y)*13 + x;')
    if args.mirror_x:
        from prepare_unoq_display_order_r2 import MAPPING
        program=program.replace('int i = (7-y)*13 + x;', 'int i = (7-y)*13 + (12-x);')
    program = program.replace('for(int v=0;v<=999;++v)', 'for(int v=0;v<=999;++v)')
    old_print = 'printf("{\\"passed\\":true,\\"checks\\":%u,\\"voltage_values\\":1000,\\"running_frequency_values\\":1000}",checks);'
    assert program.count(old_print) == 1
    program = program.replace(old_print, r'''
  printf("{\"passed\":true,\"checks\":%u,\"voltage_values\":1000,\"running_frequency_values\":1000,\"frames\":{",checks);
  bool first=true;
  for(int v : {0,10,19,91,50,310,325}) {
    fresh(float(v)); matrix_update();
    printf("%s\"%d\":[%u,%u,%u,%u]",first?"":",",v,submitted[0],submitted[1],submitted[2],submitted[3]);
    first=false;
  }
  printf("}}");''')
    report = dict(passed=False, physical_display_verified=False, hardware_commands=0,
                  orientation='remove previous X mirror and flip Y; 180 degrees relative to previous frame',
                  sources={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    if args.mirror_x:
        report['orientation']='Compensate X and Y; physical orientation model inferred from user report10->01; physical confirmation pending'
    try:
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            for name in ('Arduino.h', 'cmsis_core.h'):
                (tmp/name).write_text('#pragma once\n')
            unit, exe = out/'renderer.cpp', tmp/'renderer.exe'
            cmd = [shutil.which('g++'), '-std=c++17', '-Wall', '-Wextra', '-Werror',
                   '-I', str(tmp), '-I', str(core.parent), str(unit), '-o', str(exe)]

            def run(source, label):
                unit.write_text(source, encoding='utf-8')
                build = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                (out/(label+'_compile.log')).write_text(build.stdout+build.stderr, encoding='utf-8')
                assert build.returncode == 0, label+' compilation failed'
                return subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)

            result = run(program, 'production')
            assert result.returncode == 0, result.stderr
            report.update(json.loads(result.stdout))
            report['mutations_detected'] = {}
            mutations=(
                ('old_orientation', NEW, OLD),
                ('missing_vertical_flip', '(MATRIX_H - 1 - y) * MATRIX_W + x', 'y * MATRIX_W + x'),
                ('wrong_order', '(MATRIX_H - 1 - y) * MATRIX_W + x', '(MATRIX_H - 1 - y) * MATRIX_W + (MATRIX_W - 1 - x)'),
                ('corrupted_glyph', 'uint8_t row = DIGIT_3X5[digit][y];', 'uint8_t row = DIGIT_3X5[0][y];'),
                ('stale_voltage', '(uint32_t)(now - g_bp_vbus_ms) <= BP_VBUS_STALE_MS', 'true'),
            )
            if args.mirror_x:
                mutations=(
                    ('reported_bad_y_only_mapping', MAPPING, NEW),
                    ('missing_vertical_flip', '(MATRIX_H - 1 - y) * MATRIX_W + (MATRIX_W - 1 - x)', 'y * MATRIX_W + (MATRIX_W - 1 - x)'),
                    ('corrupted_glyph', 'uint8_t row = DIGIT_3X5[digit][y];', 'uint8_t row = DIGIT_3X5[0][y];'),
                    ('stale_voltage', '(uint32_t)(now - g_bp_vbus_ms) <= BP_VBUS_STALE_MS', 'true'),
                )
            for label, old, new in mutations:
                assert program.count(old) == 1, label
                broken = run(program.replace(old, new), label)
                report['mutations_detected'][label] = broken.returncode != 0
                assert broken.returncode != 0, label+' escaped detection'
            unit.write_text(program, encoding='utf-8')
        # Human-readable pixels decoded from the actual emitted packed frames.
        lines = []
        for value, words in report['frames'].items():
            lines += [value+' V']
            for y in range(8):
                lines.append(''.join('#' if (words[((7-y)*13+(12-x if args.mirror_x else x))//32] >> (((7-y)*13+(12-x if args.mirror_x else x))%32)) & 1 else '.' for x in range(13)))
            lines.append('')
        (out/'preview.txt').write_text('\n'.join(lines), encoding='utf-8')
    except Exception as exc:
        report.update(passed=False, error=str(exc))
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('sources','frames')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
