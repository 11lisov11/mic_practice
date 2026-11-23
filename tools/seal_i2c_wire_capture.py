"""Seal reviewed native tests, target images, RAM/stack and archive references."""
import json,re,shutil,subprocess
from pathlib import Path
import prepare_i2c_wire_capture as p

def main():
    c=p.OUT;v=c/'verification';m=json.loads(p.read(c/'manifest.json'));assert not m['installed']
    n=json.loads(p.read(v/'native_report.json'));assert n['passed'] and n['protection_source_isolation']
    stem='ACIM-NUCLEOG431RB-IPM15B-VF_OL';debug=c/'nucleo/STM32CubeIDE/Debug'
    b=json.loads(p.read(debug/(stem+'.build-manifest.json')))
    assert b['firmware_build_id']==p.NEW[1] and b['build_errors']==b['build_warnings']==0
    for f in debug.iterdir():
        if f.is_file() and f.name.startswith(stem+'.'):shutil.copy2(f,c/'build/nucleo'/f.name)
    def end(folder):return int(re.search(r'0x([0-9a-f]+)\s+PROVIDE \(_end =',p.read(folder/(stem+'.map')))[1],16)
    growth=end(debug)-end(p.BASE/'nucleo/STM32CubeIDE/Debug');margin=0x20008000-end(debug)-0x600
    assert 0<=growth<=100 and margin>=3200,(growth,margin)
    def stack(folder,file,name):
        return int(re.search(':'+name+r'\s+(\d+)\s',p.read(folder/'Application/User'/(file+'.su')))[1])
    frames={name:stack(debug,'nucleo_i2c_wire',name) for name in ('mic_i2c_wire_init','mic_i2c_wire_freeze','mic_i2c_wire_service','mic_i2c_wire_packet')}
    assert frames['mic_i2c_wire_freeze']<=16 and frames['mic_i2c_wire_service']<=40 and frames['mic_i2c_wire_init']<=160
    assert stack(debug,'current_shunt','mic_current_adc_irq')==376
    assert stack(debug,'nucleo_encoder','capture_terminal')==40
    assert stack(debug,'nucleo_encoder','capture_before_reset')<=48
    for folder,name,fw in [('nucleo',stem,p.NEW[1]),('uno','unoq_mcsdk_scalar',p.NEW[0])]:
        b=json.loads(p.read(c/'build'/folder/(name+'.build-manifest.json')));assert b['firmware_build_id']==fw
        for item in b['artifacts']:assert p.sha(c/'build'/folder/item['file'])==item['sha256'].lower()
    assert json.loads(p.read(c/'build/uno/llext-check.json'))['pass']
    b=json.loads(p.read(c/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))
    for rel,digest in b['library_override_sha256'].items():assert p.sha(c/'libraries'/rel)==digest.lower()
    proof=False
    for folder in (Path.home()/'AppData/Local/arduino/sketches').iterdir():
        f=folder/'sketch/UNOQ_MOTOR.ino.cpp.d'
        if not f.is_file():continue
        text=f.read_text(encoding='utf-8').replace('\\\n','').replace('\\','/')
        if str(c/'libraries').replace('\\','/') not in text:continue
        singleton=(folder/'libraries/Arduino_RouterBridge/singletons.cpp.d').read_text(encoding='utf-8').replace('\\\n','').replace('\\','/')
        for rel in ('Arduino_RouterBridge/src/bridge.h','Arduino_RPClite/src/decoder.h'):
            target=str(c/'libraries'/rel).replace('\\','/');assert target in text and target in singleton
        p.write(v/'uno_dependencies.txt',text);p.write(v/'singleton_dependencies.txt',singleton);proof=True
    assert proof,'Verify the RPC override is used by sketch and library'
    ui=json.loads(subprocess.check_output(['node',str(p.ROOT/'tools/current_shunt_ui_selftest.js'),str(c/'web_hmi/static/app.js')],text=True));assert ui['passed']
    subprocess.run(['node','--check',str(c/'web_hmi/static/app.js')],capture_output=True,check=True)
    assert json.loads(p.read(v/'decoder_known_address_test.json'))['passed']
    assert (v/'decoder_export/wire.vcd').is_file()
    # Archive and installed working package remain byte-for-byte unchanged.
    history=json.loads(p.read(c/'preserved_records/reference_sha256.json'))
    for rel,digest in history.items():assert p.sha(p.ROOT/rel)==digest
    old=json.loads(p.read(p.BASE/'manifest.json'))
    for table in ('source_sha256','build_sha256','verification_sha256'):
        for rel,digest in old[table].items():assert p.sha(p.BASE/rel)==digest
    r=dict(passed=True,pair=list(p.NEW),hardware_commands=0,flash_commands=0,start_commands=0,
      nucleo_build_errors=0,nucleo_build_warnings=0,nucleo_ram_growth_bytes=growth,nucleo_ram_margin_above_heap_stack=margin,
      nucleo_stack_frames=frames,adc_irq_stack_bytes=376,native_hmi_checks=n['hmi_checks'],
      native_wire_checks=sum(x['checks'] for x in n['wire_native']),
      unchanged_protected_files=n['unchanged_protected_files'],i2c_recovery_timing_filters_unchanged=True,
      native_start_clear_stop_thresholds_unchanged=True,old_archives_and_installed_images_unchanged=True,
      uno_loader_pass=True,rpc_override_dependencies_verified=True,calibration_identity_compatible=True,
      waveform_crc_parent_and_epoch_tests_pass=True,known_address_nack_decoder_pass=True,
      nominal_sample_hz=8500000,nominal_history_us=4096/8.5,
      hardware_validated=False,initial_pwm_i2c_fixed_or_proven=False,
      limitations=['GPIO sampler is digital; analog voltage/rise time and DMA jitter are not measured',
        '481.9us is sufficient for the previously recorded address NACK but does not cover a full3ms BUSY timeout',
        'Sampler and SD storage change need low-bus hardware qualification before another HV run',
        'A manual frozen capture also remains immutable until MCU reset; archive before reset',
        'Native tests model peripherals; no physical START was performed for this package'])
    p.write(v/'report.json',json.dumps(r,indent=2)+'\n')
    tools=('prepare_i2c_wire_capture.py','check_i2c_wire_capture.py','seal_i2c_wire_capture.py','analyze_i2c_wire_capture.py','verify_i2c_wire_capture_package.py')
    sources={str(p.ROOT/'tools'/name):p.sha(p.ROOT/'tools'/name) for name in tools}
    sources.update({str(f):p.sha(f) for f in p.RES.iterdir() if f.is_file()})
    p.write(v/'tool_sources.json',json.dumps(sources,indent=2)+'\n')
    m.update(built=True,selftest_pass=True,nucleo_ram_growth_bytes=growth,nucleo_ram_margin_above_heap_stack=margin,
      next_physical_step_ru='Выключить J1; после подтверждения мультиметром ниже20В подключить обе платы к ПК.15В можно оставить. Двигатель остаётся снятым сJ3; AS5600/DIR/шлейф не менять; Saleae пока не нужен.',
      next_validation='Readback both exact images; verify RPC and idle sensor; qualify passive GPIO sampler at low bus before any powered test',
      production_restore=dict(path=str(p.BASE),pair=list(p.OLD),nucleo_sha256='28948cab3eca2f0df3eaa74ca2637816e4fde924d584dab9f4cb852c0b8478e7'))
    for name,trees in [('source_sha256',('nucleo','UNOQ_MOTOR','web_hmi','libraries')),('build_sha256',('build',)),('verification_sha256',('verification','preserved_records'))]:
        m[name]={str(f.relative_to(c)).replace('\\','/'):p.sha(f) for tree in trees for f in sorted((c/tree).rglob('*')) if f.is_file() and not any(x in ('Debug','Release','__pycache__') for x in f.relative_to(c).parts)}
    p.write(c/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(r))
if __name__=='__main__':main()
