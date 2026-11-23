"""Prepare the current-only research pair from the installed, sealed sources."""
import ast
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNO_BASE = ROOT / 'artifacts/live_bench_20261028/i2c_wire_epoch_fix_r2'
MC_BASE = ROOT / 'artifacts/live_bench_20261028/i2c_wire_capture_r1'
OUT = ROOT / 'artifacts/live_bench_20261029/current_only_r1'
OLD = (2026102813, 2026102812)
NEW = (2026102901, 2026102902)


def read(p): return p.read_text(encoding='utf-8')
def write(p, s):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding='utf-8', newline='\n')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def once(s, a, b):
    assert s.count(a) == 1, a[:100]
    return s.replace(a, b)


def remove_function(s, name):
    pattern = r'^static void '+name+r'\([^;]*?\)\s*\{.*?^\}\n'
    s, n = re.subn(pattern, '', s, flags=re.M | re.S)
    assert n == 1, name
    return s


def main():
    assert not OUT.exists(), 'Preserve previous packages; never overwrite'
    for base in (UNO_BASE, MC_BASE):
        manifest = json.loads(read(base/'manifest.json'))
        assert manifest['built'] and manifest['readback_verified']
        for table in ('source_sha256', 'build_sha256', 'verification_sha256'):
            for rel, digest in manifest[table].items():
                assert sha(base/rel) == digest, str(base/rel)
    for folder, base in [('UNOQ_MOTOR', UNO_BASE), ('web_hmi', UNO_BASE),
                         ('libraries', UNO_BASE), ('nucleo', MC_BASE)]:
        def copy(src, dst):
            rel = Path(src).relative_to(base/folder)
            if folder == 'nucleo' and rel.parts[0] in ('Drivers', 'MCSDK_v6.4.2-Full'):
                os.link(src, dst)
                return dst
            return shutil.copy2(src, dst)
        shutil.copytree(base/folder, OUT/folder, copy_function=copy,
                        ignore=shutil.ignore_patterns('Debug', 'Release', '__pycache__', '*.pyc'))
    for folder in ('UNOQ_MOTOR', 'nucleo/Src', 'nucleo/Inc'):
        for p in (OUT/folder).rglob('*'):
            if not p.is_file(): continue
            a = read(p)
            b = a.replace(str(OLD[0]), str(NEW[0])).replace(str(OLD[1]), str(NEW[1]))
            if a != b: write(p, b)
    p = OUT/'nucleo/Src/main.c'
    s = read(p)
    for header in ('nucleo_encoder.h', 'nucleo_i2c_wire.h', 'wire_capture.h'):
        s = once(s, '#include "'+header+'"\n', '')
    for name in ('mic_send_i2c_wire_page', 'mic_send_encoder_page',
                 'mic_send_encoder_fault_page', 'mic_send_encoder_health_page',
                 'mic_send_encoder_release_page', 'mic_send_bus_clear'):
        s = remove_function(s, name)
    s = once(s, '  mic_encoder_init();\n  mic_i2c_wire_init();\n', '')
    start = s.index('    const bool off_low_bus=')
    end = s.index('    mic_send_bus_clear(HAL_GetTick());', start) + len('    mic_send_bus_clear(HAL_GetTick());')
    s = s[:start] + '    /* Current-only profile: no encoder I2C or optional wire DMA. */' + s[end:]
    write(p, s)
    for name in ('nucleo_encoder.c', 'nucleo_i2c_wire.c'):
        write(OUT/'nucleo/Src'/name,
              '/* Current-only profile: optional AS5600 driver and I2C capture removed.\n'
              ' * Keep the CubeIDE source link; no code, pins, clocks, DMA or IRQs. */\n')
    p = OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino'
    s = read(p)
    a = s.index('    s += " enc_source=nucleo_g431_i2c1";')
    b = s.index('\n  }', a)
    old = s[a:b]
    # Preserve the native MCU auto-stop timestamps and limit, not the I2C diagnostics.
    run_lines = [line for line in old.splitlines() if 's += " run_' in line]
    assert len(run_lines) == 6
    s = s[:a] + '    s += " enc_source=disabled";\n' + '\n'.join(run_lines) + s[b:]
    a = s.index('    g_as5600 = remote_encoder_snapshot(')
    b = s.index('\n  }', a)
    s = s[:a] + '''    // No sensor speed is available in this profile. RPC legacy slots stay invalid.
    g_as5600 = As5600Sample{};
    g_bp_enc_raw = 0; g_bp_enc_ok = false; g_bp_enc_ms = 0;
    g_enc_speed_valid = false; g_enc_rpm = 0.0f;
    g_enc_mech_hz = 0.0f; g_enc_elec_hz = 0.0f;''' + s[b:]
    write(p, s)
    write(OUT/'UNOQ_MOTOR/as5600_teacher.cpp', '''// Current-only build: no Wire/I2C worker or GPIO recovery.
#include "as5600_teacher.h"
void as5600_teacher_begin() {}
As5600Sample as5600_teacher_snapshot(uint32_t) { return As5600Sample{}; }
bool as5600_diag_select(uint8_t) { return false; }
bool as5600_diag_ready() { return false; }
''')
    p = OUT/'web_hmi/server.py'
    s = read(p)
    for old in ('(2026102813,2026102812)', '(2026102813, 2026102812)'):
        s = s.replace(old, old+', (2026102901,2026102902)')
    # Extend only integer peer lists; never inflate a two-element firmware pair.
    tree = ast.parse(s)
    lines = s.splitlines(keepends=True)
    offsets = [0]
    for line in lines: offsets.append(offsets[-1]+len(line.encode('utf-8')))
    raw = s.encode('utf-8')
    edits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Tuple) or not all(isinstance(x, ast.Constant) and type(x.value) is int for x in node.elts): continue
        values = tuple(x.value for x in node.elts)
        if len(values) <= 2 or OLD[1] not in values or NEW[1] in values: continue
        a = offsets[node.lineno-1]+node.col_offset
        b = offsets[node.end_lineno-1]+node.end_col_offset
        edits.append((a,b,raw[a:b][:-1].rstrip().rstrip(b',')+b','+str(NEW[1]).encode()+b')'))
    for a,b,value in sorted(edits, reverse=True): raw=raw[:a]+value+raw[b:]
    s = raw.decode('utf-8')
    a = s.index('def with_motor_controller_aliases(')
    b = s.index('\ndef ', a+5)
    chunk = s[a:b]
    pos = chunk.rindex('    return data')
    chunk = chunk[:pos]+chunk[pos:].replace('    return data', '    return with_current_only_profile(data)', 1)
    s = s[:a]+chunk+s[b:]
    s = once(s, 'def with_motor_controller_aliases(',
             read(ROOT/'tools/current_only/hmi_profile.py')+'\n\ndef with_motor_controller_aliases(')
    ast.parse(s)
    write(p,s)
    p = OUT/'web_hmi/static/app.js'
    s = read(p)
    a = s.index('    if (encVal) {')
    b = s.index('\n    const ts = new Date(data.ts);', a)
    old = s[a:b]
    new = '''    if (encVal && data.enc_source === "disabled") {
      encVal.textContent = "Без датчика; скорость вала не измеряется";
      encVal.title = "Исследовательский режим: фазные токи и частота поля. Оценка скорости ещё не квалифицирована.";
    } else ''' + old.lstrip()
    s = s[:a]+new+s[b:]
    write(p,s)
    p=OUT/'web_hmi/static/index.html'
    s=read(p).replace('>Энкодер</div>', '>Обратная связь</div>')
    s=s.replace('<title>', '<title>АИР · токи · ')
    write(p,s)
    references = {str((base/'manifest.json').relative_to(ROOT)): sha(base/'manifest.json')
                  for base in (UNO_BASE, MC_BASE)}
    write(OUT/'archive_references.json', json.dumps(references, indent=2))
    write(OUT/'manifest.json', json.dumps(dict(schema='mic_ai.current_only.v1',
          pair_compatibility_ids=list(NEW), base_pair=list(OLD), built=False,
          installed=False, selftest_pass=False, readback_verified=False,
          calibration_changed=False, thresholds_changed=False, uart_changed=False,
          motor_control_changed=False, adc_sampling_changed=False,
          as5600_enabled=False, ai_control_enabled=False,
          speed_measurement_available=False), indent=2))
    print(OUT)


if __name__ == '__main__': main()
