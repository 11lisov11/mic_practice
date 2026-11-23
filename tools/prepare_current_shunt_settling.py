"""Extend current ADC acquisition time without relaxing zero acceptance."""
from pathlib import Path
import json
import shutil
import prepare_current_shunt_monitor as previous

ROOT=previous.ROOT
BASE=previous.OUT
OUT=BASE.parent/'current_shunt_monitor_r2'
OLD=(2026102405,2026102406)
NEW=(2026102407,2026102408)

def main():
    assert not OUT.exists()
    m=json.loads(previous.read(BASE/'manifest.json'))
    assert m['installed'] and m['installation_flash_verified']
    for rel,digest in m['source_sha256'].items():assert previous.sha(BASE/rel)==digest,rel
    for folder in ('nucleo','UNOQ_MOTOR','web_hmi'):
        shutil.copytree(BASE/folder,OUT/folder,ignore=shutil.ignore_patterns('Debug','__pycache__'))
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
        for p in (OUT/folder).rglob('*'):
            if p.is_file():
                s=previous.read(p)
                s=s.replace('2026102405','2026102407').replace('2026102406','2026102408')
                previous.write(p,s)
    p=OUT/'web_hmi/server.py';s=previous.read(p)
    # Historical calibration/command identities remain accepted, current decoder
    # accepts the actual new pair only.
    a=s.index('# Imported as source into the HMI;');b=s.index('def with_motor_controller_aliases',a)
    s=s[:a]+s[a:b].replace('2026102405','2026102407').replace('2026102406','2026102408')+s[b:]
    s=previous.once(s,'        (2026102405, 2026102406),','        (2026102405, 2026102406),\n        (2026102407, 2026102408),')
    s=previous.once(s,'(2026102405,2026102406)) and','(2026102405,2026102406),(2026102407,2026102408)) and')
    s=''.join(line.replace(',2026102406)',',2026102406,2026102408)').replace(', 2026102406)',', 2026102406, 2026102408)')
        if ('not in (' in line or ('mc_fw_build' in line and ' in (2026' in line)) else line
        for line in s.splitlines(keepends=True))
    previous.write(p,s)
    # Give the external amplifier/RC and the ADC capacitor more acquisition time
    # after mux switching. Conversion still completes before the apex at42.5MHz.
    # Do not widen the accepted zero range/span to hide the observed49-count span.
    p=OUT/'nucleo/Src/main.c';s=previous.read(p)
    assert s.count('InjectedSamplingTime = ADC_SAMPLETIME_6CYCLES_5;')==2
    s=s.replace('InjectedSamplingTime = ADC_SAMPLETIME_6CYCLES_5;',
                'InjectedSamplingTime = ADC_SAMPLETIME_24CYCLES_5;')
    previous.write(p,s)
    for folder in ('build/uno','build/nucleo'):(OUT/folder).mkdir(parents=True)
    for key in ('source_sha256','build_sha256','verification_sha256','verification_summary'):
        m.pop(key,None)
    m.update(pair_compatibility_ids=list(NEW),predecessor=str(BASE),built=False,selftest_pass=False,
        installed=False,installation_flash_verified=False,installation_calibration_unchanged=False,
        installation_runtime_pair_verified=False,adc_idle_zero_verified=False,
        current_adc_sample_cycles=24.5,previous_current_adc_sample_cycles=6.5,
        zero_acceptance_unchanged=True,settling_hypothesis_verified=False)
    previous.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(OUT)

if __name__=='__main__':main()
