"""Give shunt telemetry a unique protocol version and preserve UART recorder."""
import json
import shutil
import prepare_current_shunt_monitor as util
import prepare_current_shunt_settling as previous

ROOT=util.ROOT
BASE=previous.OUT
OUT=BASE.parent/'current_shunt_monitor_r3'
OLD=(2026102407,2026102408)
NEW=(2026102409,2026102410)

def main():
    assert not OUT.exists()
    m=json.loads(util.read(BASE/'manifest.json'))
    assert m['installed'] and m['installation_flash_verified']
    for rel,digest in m['source_sha256'].items():assert util.sha(BASE/rel)==digest,rel
    for folder in ('nucleo','UNOQ_MOTOR','web_hmi'):
        shutil.copytree(BASE/folder,OUT/folder,ignore=shutil.ignore_patterns('Debug','__pycache__'))
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
        for p in (OUT/folder).rglob('*'):
            if p.is_file():
                s=util.read(p).replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))
                util.write(p,s)
    wire=util.read(ROOT/'tools/current_shunt_monitor/current_wire.h').replace('2026102406',str(NEW[1]))
    util.write(OUT/'UNOQ_MOTOR/current_wire.h',wire)
    p=OUT/'nucleo/Src/current_shunt.c';s=util.read(p)
    s=util.once(s,'detail?0xD4:0xD3','detail?0xD6:0xD5');util.write(p,s)
    p=OUT/'web_hmi/server.py';s=util.read(p)
    a=s.index('# Imported as source into the HMI;');b=s.index('def with_motor_controller_aliases',a)
    decoder=s[a:b].replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))
    decoder=decoder.replace('0xd3','0xd5').replace('0xd4','0xd6')
    s=s[:a]+decoder+s[b:]
    s=util.once(s,'        (2026102407, 2026102408),','        (2026102407, 2026102408),\n        (2026102409, 2026102410),')
    s=util.once(s,'(2026102407,2026102408)) and','(2026102407,2026102408),(2026102409,2026102410)) and')
    s=''.join(line.replace(',2026102408)',',2026102408,2026102410)').replace(', 2026102408)',', 2026102408, 2026102410)')
        if ('not in (' in line or ('mc_fw_build' in line and ' in (2026' in line)) else line
        for line in s.splitlines(keepends=True))
    util.write(p,s)
    for folder in ('build/uno','build/nucleo'):(OUT/folder).mkdir(parents=True)
    for key in ('source_sha256','build_sha256','verification_sha256','verification_summary'):
        m.pop(key,None)
    m.update(pair_compatibility_ids=list(NEW),predecessor=str(BASE),built=False,selftest_pass=False,
        installed=False,installation_flash_verified=False,installation_calibration_unchanged=False,
        installation_runtime_pair_verified=False,adc_idle_zero_verified=False,
        summary_version=0xd5,detail_version=0xd6,wire_version_collision_fixed=True,
        uart_reject_record_preserved=True,known_wire_version_collision=False)
    util.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n');print(OUT)

if __name__=='__main__':main()
