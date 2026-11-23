"""Seal offline evidence and release files, without contacting hardware."""
import hashlib
import json
import re
import shutil
import subprocess
from elftools.elf.elffile import ELFFile
import prepare_foc_observer_schedule_fix as p
from build_multi_native import BIN
from test_foc_update_latency_fix import function


def sha(f):
    with f.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    m = json.loads(p.read(p.OUT / 'manifest.json'))
    assert not m['installed']
    tests = json.loads(p.read(p.OUT / 'verification/selftest.json'))
    sim = json.loads(p.read(p.OUT / 'verification/schedule_model.json'))
    assert tests['passed'] and sim['passed'] and sim['same_latency_still_stops']
    assert json.loads(p.read(p.OUT / 'nucleo_build_report.json'))['passed']
    assert json.loads(p.read(p.OUT / 'build/uno/llext-check.json'))['pass']
    uno_manifest = json.loads((p.OUT / 'build/uno/unoq_mcsdk_scalar.build-manifest.json').read_text(encoding='utf-8-sig'))
    assert uno_manifest['firmware_build_id'] == p.NEW[0]
    changed = {'nucleo/Inc/motor_control.h', 'nucleo/Inc/uart_v3_transport.h',
               'UNOQ_MOTOR/uart_v3_transport.h', 'nucleo/Src/main.c'}
    for folder in ('nucleo/Inc', 'nucleo/Src', 'UNOQ_MOTOR', 'web_hmi'):
        for f in (p.OUT / folder).rglob('*'):
            if not f.is_file() or '__pycache__' in f.parts:
                continue
            rel = f.relative_to(p.OUT).as_posix()
            if rel in changed:
                continue
            expected = p.read(p.BASE / rel).replace('2026103009', '2026103011').replace('2026103010', '2026103012').replace('3009-estimate-publish', '3011-observer-schedule')
            assert p.read(f) == expected, rel
    old = p.read(p.BASE / 'nucleo/Src/main.c')
    new = p.read(p.OUT / 'nucleo/Src/main.c')
    assert re.findall(r'HAL_NVIC_SetPriority\([^;]+;', old) == re.findall(r'HAL_NVIC_SetPriority\([^;]+;', new)
    for name in ('uno_rearm_break_irq', 'uno_handle_valid_frame', 'uno_clear_frame_is_safe',
                 'mic_local_stop_clear', 'mic_local_stop_enable_outputs'):
        assert function(old, name) == function(new, name), name
    ef = p.OUT / 'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
    from configure_multi_algorithm import load
    _, raw, _ = load(p.ROOT / 'artifacts/live_bench_20261029/air56_estimated_foc_r2/profile.json')
    with ef.open('rb') as stream:
        elf = ELFFile(stream)
        syms = {s.name: s for s in elf.get_section_by_name('.symtab').iter_symbols()}
        def data(name, size):
            s = syms[name]
            section = elf.get_section(s['st_shndx'])
            off = s['st_value'] - section['sh_addr']
            return section.data()[off:off+size]
        assert data('model', 52) == raw and data('qualification', 1) == bytes([128])
        static_ram = elf.get_section_by_name('.bss')['sh_size'] + elf.get_section_by_name('.data')['sh_size']
        reserve = elf.get_section_by_name('._user_heap_stack')['sh_size']
        assert static_ram + reserve < 32768
        units = []
        for cu in elf.get_dwarf_info().iter_CUs():
            value = cu.get_top_DIE().attributes.get('DW_AT_name')
            if value and 'live_bench_20261029' in value.value.decode(errors='replace'):
                name = value.value.decode(errors='replace').replace('\\', '/')
                assert (p.OUT / 'nucleo').as_posix() in name, name
                units.append(name)
    assembly = ''
    for name in ('ma_native_service', 'ma_native_fast', 'ma_fail_at', 'ma_native_regular_fault'):
        asm = subprocess.check_output([str(BIN / 'arm-none-eabi-objdump.exe'), '-d', '--disassemble=' + name, str(ef)], text=True)
        assert '<' + name + '>:' in asm and 'cpsid' not in asm.lower() and 'primask' not in asm.lower(), name
        assembly += asm
    p.write(p.OUT / 'verification/critical_ARM.txt', assembly)
    # Preserve all prior installed firmware evidence and powered captures.
    preserved = json.loads(p.read(p.BASE / 'powered_FOC_publication_preflight_r1/prior_files_sha256.json'))
    for folder in p.BASE.iterdir():
        if folder.is_dir() and folder.name.startswith(('hardware_install', 'post_install', 'idle_verification',
                'installation_verified', 'FOC_publication_trial_preparation', 'autonomous_', 'powered_FOC')):
            for f in folder.rglob('*'):
                if f.is_file():
                    preserved[f.relative_to(p.ROOT).as_posix()] = sha(f)
    for rel, h in preserved.items():
        assert sha(p.ROOT / rel) == h, rel
    for rel, h in json.loads(p.read(p.BASE / 'source_hashes.json')).items():
        assert sha(p.BASE / rel) == h, rel
    p.write(p.OUT / 'verification/preserved_captures_sha256.json', json.dumps(preserved, indent=2) + '\n')
    release = p.OUT / 'release'
    release.mkdir(exist_ok=True)
    for name, source in [('nucleo_2026103012_observer_schedule.bin', ef.with_suffix('.bin')),
                         ('unoq_2026103011_observer_schedule.elf-zsk.bin', p.OUT / 'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin')]:
        shutil.copy2(source, release / name)
    hashes = {}
    for folder in ('nucleo/Inc', 'nucleo/Src', 'UNOQ_MOTOR', 'libraries', 'web_hmi'):
        for f in (p.OUT / folder).rglob('*'):
            if f.is_file() and '__pycache__' not in f.parts and f.suffix not in ('.pyc', '.log'):
                hashes[f.relative_to(p.OUT).as_posix()] = sha(f)
    p.write(p.OUT / 'source_hashes.json', json.dumps(hashes, indent=2) + '\n')
    audit = dict(passed=True, exact_calculated_profile=True, source_units=units,
        total_RAM_allocated=static_ram+reserve, unallocated_RAM=32768-static_ram-reserve,
        current_trip_A=1.35, ADC_guard_ticks=2048, estimate_limit_ms=2, fast_budget_cycles=5312,
        IRQ_priorities_unchanged=True, IRQ_masking_added=False, numeric_equations_unchanged=True,
        target_speedup_not_measured=True, hardware_five_seconds_not_proven=True)
    p.write(p.OUT / 'verification/ELF_audit.json', json.dumps(audit, indent=2) + '\n')
    m.update(built=True, installed=False, selftests_passed=True, model_budget_sweep_passed=True,
        preserved_files_verified=len(preserved), RAM_total=static_ram+reserve,
        target_timing_measurement_required_before_powered_trial=True,
        no_powered_trials_this_stage=True,
        artifacts={f.relative_to(p.OUT).as_posix(): sha(f) for f in release.iterdir() if f.is_file()})
    p.write(p.OUT / 'manifest.json', json.dumps(m, indent=2) + '\n')
    print(json.dumps(dict(passed=True, pair=list(p.NEW), built=True, installed=False,
        preserved_files=len(preserved), RAM_total=m['RAM_total'], artifacts=m['artifacts'])))


if __name__ == '__main__':
    main()
