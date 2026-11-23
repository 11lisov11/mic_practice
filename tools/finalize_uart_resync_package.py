"""Finish package metadata after offline tests and builds; no device access."""
import hashlib,json,re,shutil
from pathlib import Path
import install_uart_resync_fix_pair as installer

ROOT=Path(__file__).resolve().parents[1]
C=installer.C
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    r=json.loads((C/'selftest/report.json').read_text())
    assert r['pass'] and r['fixed_probe']['cases']==83968 and r['fixed_probe']['unexpected_latches_after_two_damaged_frames']==0
    debug=C/'nucleo/STM32CubeIDE/Debug'
    builds=[]
    for folder,name,identity in [(debug,'ACIM-NUCLEOG431RB-IPM15B-VF_OL',2026101806),(C/'build/uno','unoq_mcsdk_scalar',2026101807)]:
        m=json.loads((folder/(name+'.build-manifest.json')).read_text(encoding='utf-8-sig'))
        assert m['firmware_build_id']==identity
        if identity==2026101806:assert m['build_errors']==m['build_warnings']==0
        for item in m['artifacts']:assert sha(folder/item['file'])==item['sha256'].lower()
        builds.append(m)
    for p in debug.iterdir():
        if p.is_file() and (p.suffix in ('.hex','.bin','.elf') or p.name.endswith('.json')):shutil.copyfile(p,C/'build/nucleo'/p.name)
    text=(debug/'ACIM-NUCLEOG431RB-IPM15B-VF_OL.map').read_text(encoding='utf-8-sig')
    match=re.search(r'^\._user_heap_stack\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)',text,re.M)
    margin=0x20008000-int(match[1],16)-int(match[2],16);assert margin>=5000
    # Programming with an already archived transport latch retains that
    # evidence; active outputs/high voltage remain forbidden.
    old=json.loads((ROOT/'artifacts/live_bench_20261018/fast_capture_to_50_r1/post_fault_status.json').read_text())
    s=dict(old,vdc=10,bp_vdc=10,bp_vbus_raw=100,mc_uart_error_flags=0,bp_uart_error_flags=0,
        mc_age_ms=20,bp_vbus_age_ms=20,bp_temp_age_ms=20)
    assert installer.precheck(s)[0]
    rejects=0
    for k,v in [('vdc',323),('bp_vdc',323),('pwm',1),('hmi_hv_armed',1),('mc_fault_reason',2),
        ('mc_transport_fault',4),('mc_fault_occurred_mask',1024),('bp_vbus_raw',201),('mc_age_ms',300),
        ('bp_uart_error_flags',8),('mc_last_uart_error_flags',1),('precharge',1)]:
        assert not installer.precheck(dict(s,**{k:v}))[0],k;rejects+=1
    compile(installer.make_remote_installer(),'remote_hmi_installer.py','exec')
    m=json.loads((C/'manifest.json').read_text());m.update(built=True,selftest_pass=True,
        host_cases=83968,selftest_checks=r['checks'],ram_margin_after_reserved_heap_stack_bytes=margin,
        installer_guard_checks=rejects+1,source_sha256={p.relative_to(C).as_posix():sha(p)
            for t in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi') for p in (C/t).rglob('*')
            if p.is_file() and '__pycache__' not in p.parts},
        build_sha256={p.relative_to(C).as_posix():sha(p) for p in (C/'build').rglob('*') if p.is_file()})
    (C/'manifest.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
    r.update(ram_margin_after_reserved_heap_stack_bytes=margin,installer_guard_checks=rejects+1)
    (C/'selftest/report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    uno,nuc=installer.verify_package()
    print(json.dumps(dict(pass_=True,ram_margin_bytes=margin,uno_sha256=sha(uno),nucleo_sha256=sha(nuc),hardware_commands=0)))

if __name__=='__main__':main()
