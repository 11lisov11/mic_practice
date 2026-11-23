"""Compile and execute the real recorder/receiver with simulated DMA input."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import struct
import subprocess
import sys
import math

ROOT=Path(__file__).resolve().parents[1]
C=ROOT/'artifacts/live_bench_20261018/bkin_full_pulse_r1'
BASE=ROOT/'artifacts/live_bench_20261017/bkin_dma_arr_fix_r1'
def load_hmi():
    spec=importlib.util.spec_from_file_location('bkin_full_pulse_hmi',C/'web_hmi/server.py')
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    return m
def main():
    work=C/'selftest';checks=[]
    def check(ok,name):
        checks.append({'name':name,'pass':bool(ok)})
        if not ok: raise AssertionError(name)
    cmd=['gcc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function',
        '-I',str(C/'nucleo/Inc'),'-I',str(C/'UNOQ_MOTOR'),'-I',str(ROOT/'tools/bkin_full_pulse'),
        str(ROOT/'tools/bkin_full_pulse/sim.c'),'-o',str(work/'sim.exe')]
    subprocess.run(cmd,check=True,capture_output=True,text=True)
    r=subprocess.run([str(work/'sim.exe')],cwd=work,check=True,capture_output=True,text=True)
    host=json.loads(r.stdout);check(host['pass'] and host['host_cases']>=121,'actual C recorder + actual Uno receiver: 121 scenarios')
    hmi=load_hmi()
    def decode(raw,**fields):
        return hmi.bkin_wave_status({'mc_fw_build':2026101802,'mc_break_wave_hex':raw.hex(),
            'mc_break_wave_age_ms':86400000,'mc_age_ms':30,**fields})
    for p in work.glob('pulse_*.bin'):
        width=int(p.stem.split('_')[1]);d=decode(p.read_bytes())
        check(d.get('pulse_complete') and d['pulse_width_us']==width and d['post_complete'],p.stem+' HMI exact complete pulse')
        check(d['stored_record'] and d['live_peer_fresh'],'stored evidence survives delivery age '+p.stem)
    for name,reason in [('timeout','timeout_low_unfinished'),('left','missing_falling_edge'),
        ('no_low','low_not_observed'),('overrun','sampling_overrun'),('dma_error','dma_error'),
        ('stalled','dma_error'),('overflow','run_capacity_exceeded')]:
        d=decode((work/(name+'.bin')).read_bytes())
        check(d['available'] and d['reason']==reason and d['pulse_width_us'] is None and not d['pulse_complete'],name+' never invents pulse width')
    raw=(work/'pulse_70_511.bin').read_bytes()
    check(decode(raw,mc_age_ms=999999)['live_peer_fresh'] is False,'stored snapshot does not claim a fresh live peer')
    check(decode(raw,mc_fw_build=2026101710)['reason']=='wrong_peer_build','incompatible peer rejected')
    check(decode(raw[:-1])['reason']=='invalid_hex','truncated record rejected')
    # Malformed metadata with otherwise valid transport is rejected too.
    for offset,value in [(0,0),(4,2),(8,160),(16,0),(20,0),(24,65),(28,100065),
        (32,33),(36,0),(40,0xffffffff),(44,99),(48,0),(52,16),(56,1025),(60,1),
        (64,2),(68,0),(312,1)]:
        bad=bytearray(raw);struct.pack_into('<I',bad,offset,value)
        check(not decode(bad)['available'],f'invalid field offset {offset} rejected')
    # Preserve the measured scale/contract and all unrelated motor-control files.
    before=(BASE/'nucleo/Src/main.c').read_text(encoding='utf-8-sig')
    after=(C/'nucleo/Src/main.c').read_text(encoding='utf-8-sig')
    a='static bool mic_bkin_dma_initialized;';b='static void mic_bkin_wave_packet('
    strip=lambda s:s[:s.index(a)]+s[s.index(b):]
    check(strip(before).replace('2026101710','2026101802').replace('#include "bkin_wave_capture.h"','#include "bkin_wave_capture.h"\n#include "pulse_core.h"')==strip(after),'only recorder block + include + build ID changed in main.c')
    for p in (BASE/'nucleo').rglob('*'):
        if not p.is_file() or any(n in ('Debug','Release','.settings') for n in p.parts): continue
        rel=p.relative_to(BASE)
        if rel.as_posix() in ('nucleo/Src/main.c','nucleo/Inc/break_wire.h','nucleo/Inc/first_break_snapshot.h','nucleo/Inc/bkin_wave_capture.h'): continue
        target=C/rel
        check(target.is_file() and p.read_bytes()==target.read_bytes(),'unmodified '+str(rel))
    old={'fw_build':2026101711,'mc_fw_build':2026101710,'rpc_schema_version':3,'mc_capabilities':1,'mc_mcsdk_telemetry':1}
    new=dict(old,fw_build=2026101803,mc_fw_build=2026101802)
    check(hmi._vbus_calibration_identity_matches(old,new),'existing calibration identity accepted without writing points')
    check(not hmi._vbus_calibration_identity_matches(old,dict(new,mc_fw_build=999)),'unknown firmware calibration identity rejected')
    # Verify installation gate without connecting to the boards. Retaining an
    # ESTOP is allowed during programming; an armed/running drive is rejected.
    import install_bkin_full_pulse_pair as installer
    s={'fw_build':2026101711,'mc_fw_build':2026101710,'state':'SAFE','pwm':0,
       'hmi_hv_armed':0,'bp_status':4,'estop':1,'rpc_schema_version':3,'mc_capabilities':1,
       'bp_mcsdk_telemetry':1,'vdc':20,'bp_vdc':20,'mc_age_ms':20,'bp_vbus_age_ms':20,
       'bp_temp_age_ms':20,'bp_vbus_valid':1,'bp_temp_valid':1,'bp_temp_fault':0,
       'bp_vbus_raw':200,'mc_uart_error_flags':0,'bp_uart_error_flags':0,
       'mc_transport_fault':0,'bp_transport_fault':0,'precharge':0,'pfc':0,'brake':0,'bp_ext':0}
    check(installer.precheck(s)[0],'programming at user-authorized <=20 V retains ESTOP')
    for key,value in [('vdc',20.01),('bp_vdc',323),('vdc',float('nan')),
        ('bp_vbus_raw',201),('mc_age_ms',300),('pwm',1),('hmi_hv_armed',1),
        ('state','VF_RUN'),('bp_status',0x22),('bp_temp_fault',1),('mc_transport_fault',7)]:
        check(not installer.precheck(dict(s,**{key:value}))[0],'programming guard rejects '+key+'='+str(value))
    remote=installer.make_remote_installer();compile(remote,'remote_hmi_installer.py','exec')
    check('choices=(20,), default=20' in remote,'remote HMI installer uses the same 20 V programming tier')
    node=shutil.which('node')
    if not node: raise RuntimeError('node required to validate browser code')
    subprocess.run([node,'--check',str(C/'web_hmi/static/app.js')],check=True,capture_output=True)
    check(True,'browser syntax valid')
    debug=C/'nucleo/STM32CubeIDE/Debug'
    nm=json.loads((debug/'ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json').read_text(encoding='utf-8-sig'))
    um=json.loads((C/'build/uno/unoq_mcsdk_scalar.build-manifest.json').read_text(encoding='utf-8-sig'))
    check(nm['firmware_build_id']==2026101802 and nm['build_errors']==0 and nm['build_warnings']==0,'Nucleo compiles with zero warnings/errors')
    check(um['firmware_build_id']==2026101803,'Uno image identity correct')
    for folder,m in [(debug,nm),(C/'build/uno',um)]:
        for entry in m['artifacts']:
            p=folder/entry['file'];check(hashlib.sha256(p.read_bytes()).hexdigest()==entry['sha256'].lower(),'image hash '+entry['file'])
    for p in debug.iterdir():
        if p.is_file() and (p.suffix in ('.hex','.bin','.elf') or p.name.endswith('.json')):
            shutil.copyfile(p,C/'build/nucleo'/p.name)
    report={'pass':True,'checks':len(checks),'host':host,'details':checks,'hardware_validated':False,'hardware_commands':0}
    (work/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    m=json.loads((C/'manifest.json').read_text());m.update(built=True,selftest_pass=True,selftest_checks=len(checks),host_cases=host['host_cases'])
    m['source_sha256']={str(p.relative_to(C)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi') for p in (C/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    m['build_sha256']={str(p.relative_to(C)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in (C/'build').rglob('*') if p.is_file()}
    (C/'manifest.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('pass','checks','host','hardware_validated','hardware_commands')}))
if __name__=='__main__':main()
