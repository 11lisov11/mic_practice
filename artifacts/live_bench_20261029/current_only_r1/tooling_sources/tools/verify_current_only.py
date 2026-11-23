"""Run offline gates and seal a current-only package. No board access."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import prepare_current_only as p


def main():
    assert not json.loads(p.read(p.OUT/'manifest.json'))['selftest_pass'], 'Sealed verification is immutable'
    out=p.OUT/'verification';out.mkdir(exist_ok=True)
    report=dict(passed=False,hardware_commands=0,pair=list(p.NEW),checks={})
    def run(cmd,name):
        r=subprocess.run(cmd,cwd=p.ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
        p.write(out/(name+'.log'),r.stdout+r.stderr)
        report['checks'][name]=r.returncode==0
        r.check_returncode()
    run([sys.executable,str(p.ROOT/'tools/test_current_only.py')],'regression')
    run([shutil.which('node'),'--check',str(p.OUT/'web_hmi/static/app.js')],'javascript_syntax')
    # The old harness used a fixed peer default. Supply the actual new peer to
    # the unchanged strict HMI decoder; CRC and layout checks stay enabled.
    import current_adc_apex_fix_selftest as irq
    from collect_current_peak import decoder
    irq.p.OUT=p.OUT
    def new_decoder(candidate):
        module=decoder(candidate);original=module.decode_adc_peak_hex
        module.decode_adc_peak_hex=lambda value,expected_build=p.NEW[1]:original(value,expected_build)
        return module
    irq.decoder=new_decoder
    irq.main()
    adc=json.loads(p.read(p.OUT/'apex_selftest_r1/report.json'))
    assert adc['passed'] and adc['actual_irq'] and adc['raw_capture_frames_replayed']==24
    report['checks']['actual_adc_irq_and_raw_replay']=True
    report['actual_adc_checks']=adc['checks']
    build=p.OUT/'nucleo/STM32CubeIDE/Debug'
    for f in build.iterdir():
        if f.suffix in ('.elf','.hex','.bin','.map') or f.name.endswith(('.build-manifest.json','.build.log')):
            dst=p.OUT/'build/nucleo'/f.name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dst)
    m=json.loads(p.read(p.OUT/'manifest.json'))
    nm=Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.14.3.rel1.win32_1.0.100.202602081740/tools/bin/arm-none-eabi-nm.exe')
    elf=next((p.OUT/'build/nucleo').glob('*.elf'))
    symbols=subprocess.check_output([str(nm),'-S',str(elf)],text=True)
    p.write(out/'nucleo_symbols.txt',symbols)
    assert all(name not in symbols for name in ('mic_encoder_', 'mic_i2c_wire_'))
    # The fixed MCU vector table keeps an unused weak alias to Default_Handler.
    # It must have no live DMA handler from the removed recorder.
    default=next(line.split()[0] for line in symbols.splitlines() if line.endswith(' T Default_Handler'))
    alias=[line.split() for line in symbols.splitlines() if line.endswith(' DMA2_Channel4_IRQHandler')]
    assert len(alias)==1 and alias[0][-2]=='W' and alias[0][0]==default
    assert all(name in symbols for name in ('mic_current_adc_irq','mic_bkin_capture_start','mic_bkin_ring','USART1_IRQHandler'))
    report['checks']['optional_i2c_code_absent_protected_code_present']=True
    report.update(passed=True,physical_current_scale_qualified=False,rotor_speed_estimator_qualified=False,
                  ai_control_enabled=False,old_captures_unchanged=True)
    p.write(out/'report.json',json.dumps(report,indent=2))
    m.update(built=True,selftest_pass=True)
    for key,folders in [('source_sha256',('UNOQ_MOTOR','nucleo','libraries','web_hmi')),
                        ('build_sha256',('build',)),('verification_sha256',('verification','apex_selftest_r1'))]:
        table={}
        for folder in folders:
            for f in sorted((p.OUT/folder).rglob('*')):
                if not f.is_file() or any(x in ('Debug','Release','__pycache__') for x in f.relative_to(p.OUT/folder).parts):continue
                table[str(f.relative_to(p.OUT)).replace('\\','/')]=p.sha(f)
        m[key]=table
    p.write(p.OUT/'manifest.json',json.dumps(m,indent=2))
    from install_current_only import verify_package
    verify_package()
    print(json.dumps(report))


if __name__=='__main__':main()
