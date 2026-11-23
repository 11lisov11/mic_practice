"""Seal build/test evidence for the BKIN filter pair, entirely offline."""
import hashlib
import json
import re
import shutil
import install_sd_break_filter_pair as install

C, ROOT = install.C, install.ROOT


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    debug = C / 'nucleo/STM32CubeIDE/Debug'
    nuc = C / 'build/nucleo'
    nuc.mkdir(parents=True, exist_ok=True)
    for p in debug.iterdir():
        if p.is_file() and (p.suffix in ('.hex', '.bin', '.elf') or p.name.endswith('.json')):
            shutil.copyfile(p, nuc / p.name)
    build = json.loads((nuc / 'ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json').read_text(encoding='utf-8-sig'))
    assert build['build_errors'] == build['build_warnings'] == build['build_exit_code'] == 0
    assert json.loads((C / 'build/uno/llext-check.json').read_text(encoding='utf-8'))['pass']
    source = (debug / 'ACIM-NUCLEOG431RB-IPM15B-VF_OL.map').read_text(encoding='utf-8-sig')
    match = re.search(r'^\._user_heap_stack\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)', source, re.M)
    margin = 0x20008000 - int(match[1], 16) - int(match[2], 16)
    assert margin >= 5000
    # Explicitly synthetic guard fixtures: no fabricated live state is submitted
    # to the installer or controllers. The real archived fault is never CLEARed.
    s = json.loads((ROOT / 'artifacts/live_bench_20261018/uart_tx_dma_to_50_r2/latest_stopped_status.json').read_text(encoding='utf-8'))
    if 'data' in s:
        s = s['data']
    s.update(fw_build=install.OLD[0], mc_fw_build=install.OLD[1], state='SAFE', pwm=0,
             hmi_hv_armed=0, vdc=2, bp_vdc=2, bp_vbus_raw=20, mc_age_ms=20,
             bp_vbus_age_ms=20, bp_temp_age_ms=20)
    assert install.precheck(s)[0], install.precheck(s)
    cases = [dict(name='retained DP accepted for programming only', passed=True)]
    for key, value in [('pwm', 1), ('hmi_hv_armed', 1), ('vdc', 21), ('bp_vdc', 21),
                       ('bp_vbus_raw', 201), ('mc_age_ms', 300), ('mc_transport_fault', 4),
                       ('precharge', 1), ('pfc', 1), ('brake', 1), ('mc_uart_error_flags', 2),
                       ('bp_temp_fault', 1), ('fw_build', 0)]:
        assert not install.precheck(dict(s, **{key: value}))[0], key
        cases.append(dict(name='reject ' + key, passed=True))
    compile(install.make_remote_installer(), 'remote_installer.py', 'exec')
    (C / 'installer_guard_selftest.json').write_text(json.dumps(dict(passed=True, synthetic_fixtures=True,
        hardware_commands=0, checks=cases), indent=2) + '\n', encoding='utf-8')
    m = json.loads((C / 'manifest.json').read_text(encoding='utf-8'))
    m.update(built=True, selftest_pass=True, ram_margin_after_reserved_heap_stack_bytes=margin,
        source_sha256={p.relative_to(C).as_posix(): sha(p)
            for tree in ('nucleo/Inc', 'nucleo/Src', 'nucleo/Drivers', 'nucleo/Middlewares', 'UNOQ_MOTOR', 'web_hmi')
            for p in (C / tree).rglob('*') if p.is_file() and '__pycache__' not in p.parts},
        build_sha256={p.relative_to(C).as_posix(): sha(p) for p in (C / 'build').rglob('*') if p.is_file()},
        verification_sha256={rel: sha(C / rel) for rel in ('selftest/report.json', 'filter_selftest/report.json', 'installer_guard_selftest.json')})
    for p in (C / 'nucleo').glob('*.ioc'):
        m['source_sha256'][p.relative_to(C).as_posix()] = sha(p)
    (C / 'manifest.json').write_text(json.dumps(m, indent=2) + '\n', encoding='utf-8')
    uno, nuc = install.verify_package()
    print(json.dumps(dict(passed=True, ram_margin_bytes=margin, uno_sha256=sha(uno), nucleo_sha256=sha(nuc), hardware_commands=0)))


if __name__ == '__main__':
    main()
