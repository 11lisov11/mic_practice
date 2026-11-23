"""Seal offline TX DMA fix; no hardware access."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import install_uart_tx_dma_pair as install

C=install.C;ROOT=install.ROOT
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    t=json.loads((C/'selftest/report.json').read_text(encoding='utf-8'));assert t['pass']
    debug=C/'nucleo/STM32CubeIDE/Debug';nuc=C/'build/nucleo';nuc.mkdir(parents=True,exist_ok=True)
    for p in debug.iterdir():
        if p.is_file() and (p.suffix in ('.hex','.bin','.elf') or p.name.endswith('.json')):shutil.copyfile(p,nuc/p.name)
    for folder,name,build in [(nuc,'ACIM-NUCLEOG431RB-IPM15B-VF_OL',install.NEW[1]),(C/'build/uno','unoq_mcsdk_scalar',install.NEW[0])]:
        m=json.loads((folder/(name+'.build-manifest.json')).read_text(encoding='utf-8-sig'))
        assert m['firmware_build_id']==build
        if build==install.NEW[1]:assert m['build_errors']==m['build_warnings']==0
        for item in m['artifacts']:assert sha(folder/item['file'])==item['sha256'].lower()
    source=(debug/'ACIM-NUCLEOG431RB-IPM15B-VF_OL.map').read_text(encoding='utf-8-sig')
    match=re.search(r'^\._user_heap_stack\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)',source,re.M)
    margin=0x20008000-int(match[1],16)-int(match[2],16);assert margin>=5000
    if install.OLD==(2026101811,2026101810):
        s=json.loads((ROOT/'artifacts/live_bench_20261018/uart_tx_dma_install_r1/tx_watchdog_fault_status.json').read_text(encoding='utf-8'))
    else:s=json.loads((ROOT/'artifacts/live_bench_20261018/sd_live_j4_reset_probe_r1/reset_outcome_verification.json').read_text(encoding='utf-8'))['current_status']
    assert install.precheck(s)[0]
    for key,value in [('pwm',1),('hmi_hv_armed',1),('vdc',21),('bp_vdc',21),('mc_age_ms',300),('mc_transport_fault',4),('precharge',1)]:
        assert not install.precheck(dict(s,**{key:value}))[0],key
    compile(install.make_remote_installer(),'remote_installer.py','exec')
    m=json.loads((C/'manifest.json').read_text(encoding='utf-8'))
    m.update(built=True,selftest_pass=True,ram_margin_after_reserved_heap_stack_bytes=margin,installer_guard_checks=8,
        source_sha256={p.relative_to(C).as_posix():sha(p) for tree in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi')
            for p in (C/tree).rglob('*') if p.is_file() and '__pycache__' not in p.parts},
        build_sha256={p.relative_to(C).as_posix():sha(p) for p in (C/'build').rglob('*') if p.is_file()})
    (C/'manifest.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
    uno,nuc=install.verify_package()
    print(json.dumps(dict(pass_=True,ram_margin_bytes=margin,uno_sha256=sha(uno),nucleo_sha256=sha(nuc),hardware_commands=0)))

if __name__=='__main__':main()
