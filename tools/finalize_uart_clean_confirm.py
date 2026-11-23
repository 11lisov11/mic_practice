"""Seal offline evidence and completed images; no hardware/network access."""
import json
import re
import shutil
import subprocess
import sys
import prepare_uart_clean_confirm as package
import install_uart_clean_confirm_pair as install

C,ROOT=package.OUT,package.ROOT
sha=install.io.sha
def main():
    debug=C/'nucleo/STM32CubeIDE/Debug'
    for p in debug.iterdir():
        if p.is_file() and (p.suffix in ('.hex','.bin','.elf') or p.name.endswith('.json')):
            shutil.copyfile(p,C/'build/nucleo'/p.name)
    b=json.loads((C/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json').read_text(encoding='utf-8-sig'))
    assert b['build_errors']==b['build_warnings']==b['build_exit_code']==0
    assert json.loads((C/'build/uno/llext-check.json').read_text(encoding='utf-8'))['pass']
    mapping=(debug/'ACIM-NUCLEOG431RB-IPM15B-VF_OL.map').read_text(encoding='utf-8-sig')
    match=re.search(r'^\._user_heap_stack\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)',mapping,re.M)
    margin=0x20008000-int(match[1],16)-int(match[2],16);assert margin>=5000
    s=json.loads((ROOT/'artifacts/live_bench_20261021/sd_dual_motor_to_25_r1/post_stop_read/final_status.json').read_text(encoding='utf-8'))
    s=s.get('data',s)
    # A synthetic low-bus copy of the retained fault, never sent to hardware.
    low=dict(s,vdc=2,bp_vdc=2,bp_vbus_raw=20,mc_age_ms=20,bp_vbus_age_ms=20,bp_temp_age_ms=20)
    assert install.precheck(low)[0],install.precheck(low)
    checks=[dict(name='known NE latch retained on synthetic low-bus programming bench',passed=True)]
    for key,value in [('pwm',1),('hmi_hv_armed',1),('vdc',21),('bp_vdc',21),('bp_vbus_raw',201),
                      ('mc_age_ms',300),('mc_uart_error_flags',8),('bp_uart_error_flags',2),
                      ('mc_transport_fault',4),('mc_last_bad_reason',11),('mc_fault_current_mask',0x400),
                      ('precharge',1),('pfc',1),('brake',1),('bp_temp_fault',1),('fw_build',0)]:
        assert not install.precheck(dict(low,**{key:value}))[0],key
        checks.append(dict(name='programming rejects '+key,passed=True))
    clean=dict(low,mc_uart_error_flags=0,bp_uart_error_flags=0,mc_transport_fault=0,bp_transport_fault=0)
    assert install.precheck(clean)[0]
    remote=install.make_remote_installer();compile(remote,'remote_installer.py','exec')
    assert install.GUARD in remote and '((2026102101,2026102102),(2026102103,2026102104))' in remote
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
    cli=json.loads(subprocess.check_output([sys.executable,str(ROOT/'tools/install_uart_clean_confirm_usb_pair.py'),
        '--verify-package-only'],text=True))
    assert cli['uno_sha256']==sha(uno) and cli['nucleo_sha256']==sha(nuc) and cli['hardware_commands']==0
    (C/'usb_adapter_verification.json').write_text(json.dumps(cli,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,pair=list(package.NEW),ram_margin_bytes=margin,
        uno_sha256=sha(uno),nucleo_sha256=sha(nuc),installed=False,hardware_commands=0)))

if __name__=='__main__':main()
