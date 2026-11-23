"""Seal actual build and offline evidence. No device or network access."""
import json
import re
import shutil
import subprocess
import sys
import prepare_sd_dual_capture as package
import install_sd_dual_capture_pair as install

C,ROOT=package.OUT,package.ROOT
sha=install.io.sha
def main():
    debug=C/'nucleo/STM32CubeIDE/Debug'
    for p in debug.iterdir():
        if p.is_file() and (p.suffix in ('.hex','.bin','.elf') or p.name.endswith('.json')):
            shutil.copyfile(p,C/'build/nucleo'/p.name)
    n=json.loads((C/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json').read_text(encoding='utf-8-sig'))
    assert n['build_errors']==n['build_warnings']==n['build_exit_code']==0
    assert json.loads((C/'build/uno/llext-check.json').read_text(encoding='utf-8'))['pass']
    text=(debug/'ACIM-NUCLEOG431RB-IPM15B-VF_OL.map').read_text(encoding='utf-8-sig')
    match=re.search(r'^\._user_heap_stack\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)',text,re.M)
    margin=0x20008000-int(match[1],16)-int(match[2],16);assert margin>=5000
    # Synthetic programming-state fixtures, never submitted to the live stand.
    s=json.loads((ROOT/'artifacts/live_bench_20261020/sd_break_filter_to_50_r1/latest_stopped_status.json').read_text(encoding='utf-8'))
    if 'data' in s:s=s['data']
    s.update(fw_build=package.OLD[0],mc_fw_build=package.OLD[1],state='SAFE',pwm=0,
             hmi_hv_armed=0,vdc=2,bp_vdc=2,bp_vbus_raw=20,mc_age_ms=20,bp_vbus_age_ms=20,bp_temp_age_ms=20)
    assert install.precheck(s)[0],install.precheck(s)
    checks=[dict(name='latched DP retained on programming bench',passed=True)]
    for key,value in [('pwm',1),('hmi_hv_armed',1),('vdc',21),('bp_vdc',21),
                      ('bp_vbus_raw',201),('mc_age_ms',300),('mc_transport_fault',4),
                      ('precharge',1),('pfc',1),('brake',1),('mc_uart_error_flags',2),
                      ('bp_temp_fault',1),('fw_build',0)]:
        assert not install.precheck(dict(s,**{key:value}))[0],key
        checks.append(dict(name='reject '+key,passed=True))
    compile(install.make_remote_installer(),'remote_installer.py','exec')
    assert '((2026102001,2026102002),(2026102101,2026102102))' in install.make_remote_installer()
    # Exercise the actual CLI adapter after all legacy imports. It must pick
    # this pair, never an older adapter's shared global defaults.
    cli=json.loads(subprocess.check_output([sys.executable,str(ROOT/'tools/install_sd_dual_capture_usb_pair.py'),
                                          '--verify-package-only'],text=True)) if (C/'manifest.json').exists() and json.loads((C/'manifest.json').read_text())['built'] else None
    if cli is not None:
        assert cli['uno_sha256']==sha(C/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin')
        assert cli['nucleo_sha256']==sha(C/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex')
        assert cli['hardware_commands']==0
        checks.append(dict(name='USB adapter selects the exact new images',passed=True))
    (C/'installer_guard_selftest.json').write_text(json.dumps(dict(passed=True,synthetic_fixtures=True,
        hardware_commands=0,checks=checks),indent=2)+'\n',encoding='utf-8')
    m=json.loads((C/'manifest.json').read_text(encoding='utf-8'))
    m.update(built=True,selftest_pass=True,ram_margin_after_reserved_heap_stack_bytes=margin,
        source_sha256={p.relative_to(C).as_posix():sha(p)
            for tree in ('nucleo/Inc','nucleo/Src','nucleo/Drivers','nucleo/MCSDK_v6.4.2-Full','UNOQ_MOTOR','web_hmi')
            for p in (C/tree).rglob('*') if p.is_file() and '__pycache__' not in p.parts},
        build_sha256={p.relative_to(C).as_posix():sha(p) for p in (C/'build').rglob('*') if p.is_file()},
        verification_sha256={rel:sha(C/rel) for rel in ('selftest/report.json','installer_guard_selftest.json')})
    for p in (C/'nucleo').glob('*.ioc'):m['source_sha256'][p.relative_to(C).as_posix()]=sha(p)
    (C/'manifest.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
    uno,nuc=install.verify_package()
    print(json.dumps(dict(passed=True,ram_margin_bytes=margin,uno_sha256=sha(uno),nucleo_sha256=sha(nuc),installed=False,hardware_commands=0)))
if __name__=='__main__':main()
