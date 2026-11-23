"""Seal checked parked-idle I2C sources, libraries and both target images."""
import json
import shutil
import prepare_nucleo_i2c_idle as p
def main():
    c=p.OUT;m=json.loads(p.read(c/'manifest.json'));assert not m['installed']
    report=json.loads(p.read(c/'verification/report.json'));assert report['passed']
    stem='ACIM-NUCLEOG431RB-IPM15B-VF_OL';debug=c/'nucleo/STM32CubeIDE/Debug'
    for f in debug.iterdir():
        if f.is_file() and f.name.startswith(stem+'.'):shutil.copy2(f,c/'build/nucleo'/f.name)
    for folder,name,build in [('uno','unoq_mcsdk_scalar',p.NEW[0]),('nucleo',stem,p.NEW[1])]:
        b=json.loads(p.read(c/'build'/folder/(name+'.build-manifest.json')));assert b['firmware_build_id']==build
        for item in b['artifacts']:assert p.sha(c/'build'/folder/item['file'])==item['sha256'].lower()
    m.update(built=True,selftest_pass=True,
        nucleo_static_growth_bytes=report['nucleo_static_growth_bytes'],
        nucleo_ram_margin_above_heap_stack=report['nucleo_ram_margin_above_heap_stack'],
        adc_irq_stack_bytes=report['adc_irq_stack_bytes'],capture_stack_bytes=report['capture_stack_bytes'],
        programming_state_required='J1 OFF, independent DMM<20V, both USB toPC; 15V may remainON, motor/sensor wiring unchanged')
    for name,trees in [('source_sha256',('nucleo','UNOQ_MOTOR','web_hmi','libraries')),
                       ('build_sha256',('build',)),('verification_sha256',('verification',))]:
        m[name]={str(f.relative_to(c)).replace('\\','/'):p.sha(f) for tree in trees for f in sorted((c/tree).rglob('*'))
            if f.is_file() and not any(x in ('Debug','Release','__pycache__') for x in f.relative_to(c).parts)}
    p.write(c/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(json.dumps(dict(sealed=True,pair=p.NEW,ram_margin=report['nucleo_ram_margin_above_heap_stack'],installed=False)))
if __name__=='__main__':main()
