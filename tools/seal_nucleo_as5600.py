"""Seal checked images and immutable source hashes; no hardware access."""
import json
from pathlib import Path
import re
import shutil
import prepare_nucleo_as5600 as p
import prepare_current_shunt_monitor as u

def main():
    c=p.OUT;m=json.loads(u.read(c/'manifest.json'))
    assert not m['installed']
    checks=json.loads(u.read(c/'verification/report.json'));assert checks['passed']
    debug=c/'nucleo/STM32CubeIDE/Debug';name='ACIM-NUCLEOG431RB-IPM15B-VF_OL'
    for f in debug.iterdir():
        if f.is_file() and f.name.startswith(name+'.'):
            shutil.copyfile(f,c/'build/nucleo'/f.name)
    for folder,manifest,build in [('uno','unoq_mcsdk_scalar',p.NEW[0]),('nucleo',name,p.NEW[1])]:
        b=json.loads(u.read(c/'build'/folder/(manifest+'.build-manifest.json')))
        assert b['firmware_build_id']==build
        if folder=='nucleo':assert b['build_errors']==b['build_warnings']==0
        for item in b['artifacts']:assert u.sha(c/'build'/folder/item['file'])==item['sha256'].lower()
    assert json.loads(u.read(c/'build/uno/llext-check.json'))['pass']
    text=u.read(debug/(name+'.map'))
    end=int(re.search(r'0x([0-9a-f]+)\s+PROVIDE \(_end =',text)[1],16)
    margin=0x20008000-end-0x600
    baseline=u.read(p.NUC/'nucleo/STM32CubeIDE/Debug'/(name+'.map'))
    baseline_end=int(re.search(r'0x([0-9a-f]+)\s+PROVIDE \(_end =',baseline)[1],16)
    # The predecessor has exactly4096 bytes above its reserved heap/stack.
    # Budget the new fixed encoder state explicitly rather than claiming
    # that a RAM-consuming feature leaves that number unchanged.
    encoder_static_budget=128
    assert 0<=end-baseline_end<=encoder_static_budget
    assert margin>=4096-encoder_static_budget
    stack=u.read(debug/'Application/User/current_shunt.su')
    irq_stack=int(re.search(r':mic_current_adc_irq\s+(\d+)\s',stack)[1]);assert irq_stack<=384
    m.update(built=True,selftest_pass=True,hardware_validated=False,physical_rotation_verified=False,
        sensor_under_pwm_qualified=False,nucleo_ram_margin_above_heap_stack=margin,
        adc_irq_stack_bytes=irq_stack,encoder_static_growth_bytes=end-baseline_end,
        encoder_static_budget_bytes=encoder_static_budget,
        ram_budget_note='80bytes new fixed state within128byte feature budget; reserved heap/stack unchanged; actual headroom reported')
    m['source_sha256']={str(f.relative_to(c)).replace('\\','/'):u.sha(f)
        for name in ('nucleo','UNOQ_MOTOR','web_hmi') for f in sorted((c/name).rglob('*'))
        if f.is_file() and not any(s in f.relative_to(c).parts for s in ('Debug','Release','__pycache__'))}
    m['build_sha256']={str(f.relative_to(c)).replace('\\','/'):u.sha(f) for f in sorted((c/'build').rglob('*')) if f.is_file()}
    m['verification_sha256']={str(f.relative_to(c)).replace('\\','/'):u.sha(f) for f in sorted((c/'verification').rglob('*')) if f.is_file()}
    u.write(c/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps({'sealed':True,'pair':p.NEW,'ram_margin':margin,'adc_irq_stack':irq_stack}))

if __name__=='__main__':main()
