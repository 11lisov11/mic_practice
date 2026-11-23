"""Seal offline-built SD candidate and prove programming guards, without devices."""
from pathlib import Path
import hashlib
import json
import math
import re
import shutil
import install_sd_live_diagnostics_pair as installer

C=installer.C
ROOT=installer.ROOT


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    test=json.loads((C/'selftest/report.json').read_text(encoding='utf-8'))
    assert test['pass'] and test['bkin']['pass'] and test['uart']['pass']
    debug=C/'nucleo/STM32CubeIDE/Debug'
    nuc=C/'build/nucleo'
    nuc.mkdir(parents=True,exist_ok=True)
    for path in debug.iterdir():
        if path.is_file() and (path.suffix in ('.hex','.bin','.elf') or path.name.endswith('.json')):
            shutil.copyfile(path,nuc/path.name)
    for folder,name,build in [(nuc,'ACIM-NUCLEOG431RB-IPM15B-VF_OL',2026101808),(C/'build/uno','unoq_mcsdk_scalar',2026101809)]:
        manifest=json.loads((folder/(name+'.build-manifest.json')).read_text(encoding='utf-8-sig'))
        assert manifest['firmware_build_id']==build
        if build==2026101808:assert manifest['build_errors']==manifest['build_warnings']==0
        for item in manifest['artifacts']:assert sha(folder/item['file'])==item['sha256'].lower()
    text=(debug/'ACIM-NUCLEOG431RB-IPM15B-VF_OL.map').read_text(encoding='utf-8-sig')
    match=re.search(r'^\._user_heap_stack\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)',text,re.M)
    margin=0x20008000-int(match[1],16)-int(match[2],16)
    assert margin>=5000
    # Exact current saved DP+undervoltage state is allowed for programming only.
    status=json.loads((ROOT/'artifacts/live_bench_20261018/sd_reset_investigation_r1/live_read/final_status.json').read_text(encoding='utf-8'))
    assert installer.precheck(status)[0]
    rejects=0
    for key,value in [('pwm',1),('hmi_hv_armed',1),('vdc',21),('bp_vdc',21),('mc_age_ms',300),('bp_status',0x22),('mc_transport_fault',4),('bp_uart_error_flags',8),('precharge',1)]:
        assert not installer.precheck(dict(status,**{key:value}))[0],key
        rejects+=1
    compile(installer.make_remote_installer(),'sd_remote_installer.py','exec')
    manifest=json.loads((C/'manifest.json').read_text(encoding='utf-8'))
    manifest.update(built=True,selftest_pass=True,ram_margin_after_reserved_heap_stack_bytes=margin,
        installer_guard_checks=rejects+1,
        source_sha256={p.relative_to(C).as_posix():sha(p) for tree in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi')
            for p in (C/tree).rglob('*') if p.is_file() and '__pycache__' not in p.parts},
        build_sha256={p.relative_to(C).as_posix():sha(p) for p in (C/'build').rglob('*') if p.is_file()})
    (C/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    uno,nucleo=installer.verify_package()
    print(json.dumps(dict(pass_=True,ram_margin_bytes=margin,uno_sha256=sha(uno),nucleo_sha256=sha(nucleo),hardware_commands=0)))


if __name__=='__main__':main()
