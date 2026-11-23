"""Check target library selection, control isolation, and actual HMI contracts."""
import copy
import json
from pathlib import Path
from elftools.elf.elffile import ELFFile
import prepare_rpc_coldboot_fix as p
import sys
if '--boot-retry' in sys.argv:import prepare_rpc_boot_retry as p
from ipm_break_wifi_selftest import load_module

def main():
    c=p.OUT;checks=[]
    assert json.loads((c/'verification/native/report.json').read_text())['passed']
    predecessor=p.base.BASE if '--boot-retry' in sys.argv else p.BASE
    old=(predecessor/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text(encoding='utf-8-sig')
    new=(c/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text(encoding='utf-8-sig')
    diag='''    s += " rpc_response_timeouts=";s += String((unsigned long)mic_rpc_health.response_timeouts);
    s += " rpc_send_timeouts=";s += String((unsigned long)mic_rpc_health.send_timeouts);
    s += " rpc_late_responses=";s += String((unsigned long)mic_rpc_health.late_responses);
    s += " rpc_unknown_methods=";s += String((unsigned long)mic_rpc_health.unknown_methods);
'''
    normalized=new.replace('FW_BUILD_ID = '+str(p.NEW[0])+'U;','FW_BUILD_ID = 2026102605U;').replace(diag,'')
    if '--boot-retry' in sys.argv:
        normalized=normalized.replace('''    // The local Bridge override reuses its transport and updater. Retry only
    // here, where local and remote PWM are already required to be OFF.''','''    // This function already refuses active local or peer PWM. A failed begin
    // still owns a running updater thread: do not recreate it in-place.
    if (NUCLEO_MCSDK_ACIM_BACKEND) { NVIC_SystemReset(); return; }''')
        normalized=normalized.replace('    (void)Bridge.begin(RPC_BAUD); // Bounded failure; idle bridge_tick retries without resetting control.',
            '    if (!Bridge.begin(RPC_BAUD) && NUCLEO_MCSDK_ACIM_BACKEND) NVIC_SystemReset();')
    assert normalized==old
    for f in (predecessor/'UNOQ_MOTOR').iterdir():
        if f.is_file() and f.name!='UNOQ_MOTOR.ino':assert f.read_bytes()==(c/'UNOQ_MOTOR'/f.name).read_bytes(),f.name
    checks.append('Motor algorithm, watchdog, SD, encoder capture, display and UART control code unchanged; identity, read-only counters'+(' and idle-only startup retry differ' if '--boot-retry' in sys.argv else ' differ'))
    build=json.loads((c/'build/uno/unoq_mcsdk_scalar.build-manifest.json').read_text(encoding='utf-8-sig'))
    assert build['firmware_build_id']==p.NEW[0]
    for rel,digest in build['library_override_sha256'].items():assert p.util.sha(c/'libraries'/rel)==digest.lower(),rel
    cache=Path.home()/'AppData/Local/arduino/sketches'
    found=[]
    for d in cache.iterdir():
        if not d.is_dir():continue
        dep=d/'sketch/UNOQ_MOTOR.ino.cpp.d'
        if not dep.exists():continue
        text=dep.read_text().replace('\\\n','').replace('\\ ', ' ')
        if str(c/'libraries').replace('\\','/') not in text.replace('\\','/'):continue
        singleton=d/'libraries/Arduino_RouterBridge/singletons.cpp.d'
        assert singleton.exists()
        st=singleton.read_text().replace('\\\n','').replace('\\ ', ' ').replace('\\','/')
        for rel in ('Arduino_RouterBridge/src/bridge.h','Arduino_RPClite/src/decoder.h'):
            assert str(c/'libraries'/rel).replace('\\','/') in st,rel
            assert str(c/'libraries'/rel).replace('\\','/') in text.replace('\\','/'),rel
        found.append(d)
        (c/'verification/sketch_dependencies.txt').write_text(text)
        (c/'verification/singleton_dependencies.txt').write_text(st)
    assert found,'No dependency proof of local override compilation'
    with (c/'build/uno/UNOQ_MOTOR.ino.elf').open('rb') as f:
        e=ELFFile(f);symbols={s.name:s for s in e.get_section_by_name('.symtab').iter_symbols()}
        assert 'mic_rpc_health' in symbols
    checks.append('Both sketch and Bridge singleton compiled against same patched local headers; target ELF includes health counters; loader relocation check passed')
    assert json.loads((c/'build/uno/llext-check.json').read_text())['pass']
    h=load_module(c/'web_hmi/server.py')
    fixture=json.loads((p.base.OUT/'diagnosis/get_with_snapshot.json' if '--boot-retry' in sys.argv else c/'diagnosis/get_with_snapshot.json').read_text())['status']
    s=copy.deepcopy(fixture);s['fw_build']=p.NEW[0]
    s=h.with_zero_history(h.with_shunt_currents(s))
    assert s['mc_zero_history_valid']==1
    assert h.manual_scalar_supported(dict(s,manual_scalar_capable=1))
    identity_keys=('rpc_schema_version','mc_capabilities','mc_mcsdk_telemetry','fw_build','mc_fw_build')
    stored={k:fixture[k] for k in identity_keys};current=dict(stored,fw_build=p.NEW[0])
    assert h._vbus_calibration_identity_matches(stored,current)
    parsed=h.RpcBridge._parse_status_string('DATA state=SAFE mode=VF pwm=0 rpc_response_timeouts=2 rpc_send_timeouts=3 rpc_late_responses=4 rpc_unknown_methods=5')
    assert [parsed[x] for x in ('rpc_response_timeouts','rpc_send_timeouts','rpc_late_responses','rpc_unknown_methods')]==[2,3,4,5]
    assert h.with_zero_history(dict(s,fw_build=2026102699))['mc_zero_history_valid']==0
    checks.append('Recorded zero capture and calibration decode with new Uno identity; unknown identity rejected; four diagnostics parse through actual HMI')
    report=dict(passed=True,hardware_commands=0,checks=checks,autonomous_coldboot_verified=False)
    (c/'verification/report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
if __name__=='__main__':main()
