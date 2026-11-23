"""Check actual captures/protocol, motor-code isolation, target RAM/stack."""
import copy
import json
import re
import subprocess
from pathlib import Path
import prepare_nucleo_i2c_idle as p
from ipm_break_wifi_selftest import load_module
from audit_production_pwm_filters import function

def normalized(s):return s.replace(str(p.NEW[0]),str(p.OLD[0])).replace(str(p.NEW[1]),str(p.OLD[1]))
def main():
    c=p.OUT;v=c/'verification';checks=[]
    replay=json.loads(p.read(v/'driver_replay.json'));assert replay['passed'] and replay['platform_test']['passed']
    for folder,base,allowed in [
        ('nucleo',p.NUC,{'Inc/encoder_core.h','Inc/encoder_wire.h','Src/nucleo_encoder.c'}),
        ('UNOQ_MOTOR',p.UNO,{'encoder_wire.h','uno_encoder_adapter.h'})]:
        for f in (base/folder).rglob('*'):
            rel=f.relative_to(base/folder)
            if not f.is_file() or any(x in ('Debug','Release','__pycache__','.settings') for x in rel.parts):continue
            if str(rel).replace('\\','/') in allowed:continue
            new=c/folder/rel
            if new.read_bytes()!=f.read_bytes():assert normalized(p.read(new))==p.read(f),str(rel)
    for f in (p.UNO/'libraries').rglob('*'):
        if f.is_file():assert f.read_bytes()==(c/'libraries'/f.relative_to(p.UNO/'libraries')).read_bytes(),str(f)
    for f in (p.UNO/'web_hmi/static').rglob('*'):
        if f.is_file():assert f.read_bytes()==(c/'web_hmi/static'/f.relative_to(p.UNO/'web_hmi/static')).read_bytes()
    checks.append('Every motor/PWM/ADC/Break/deadtime/watchdog/control-UART source unchanged except build identity; display, UI and qualified local RPC libraries byte-identical')
    old=p.read(p.NUC/'nucleo/Src/nucleo_encoder.c');new=p.read(c/'nucleo/Src/nucleo_encoder.c')
    for name in ('capture_before_reset','capture_after_reset','mic_encoder_fault_packet','mic_encoder_packet'):
        # Wire constants are in headers; the actual producer/capture code is unchanged.
        assert normalized(function(new,name))==function(old,name),name
    checks.append('First-fault callback and160B capture ordering, frozen slots and OFF-only page producer preserved')
    # Compile original first-fault and43-byte corruption checks against new headers.
    test=p.read(p.ROOT/'tools/i2c_first_fault/selftest.cpp').replace(
        'capture_before_reset};','capture_before_reset,nullptr,nullptr,nullptr,nullptr};')
    p.write(v/'capture_test.cpp',test)
    cmd=['g++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(c/'nucleo/Inc'),
        '-I',str(p.ROOT/'tools/i2c_first_fault'),str(v/'capture_test.cpp'),'-o',str(v/'capture_test.exe')]
    subprocess.run(cmd,check=True,capture_output=True,text=True)
    cap=json.loads(subprocess.check_output([str(v/'capture_test.exe')],text=True));assert cap['passed']
    h=load_module(c/'web_hmi/server.py')
    r=json.loads(p.read(p.UNO/'powered_first_fault_5hz_r1/trial/report.json'));s=copy.deepcopy(r['final_status'])
    original_capture=json.loads(p.read(p.UNO/'powered_first_fault_5hz_r1/trial/first_i2c_capture.json'))
    original=h.decode(bytes.fromhex(original_capture['pwm_hex']),p.OLD[1],1)
    assert original['cause']=='BUSY' and original['pwm_moe']
    s.update(fw_build=p.NEW[0],mc_fw_build=p.NEW[1],bp_fw_build=p.NEW[1])
    # Re-identify recorded frames only to test the compatible protocol contract.
    # These bytes are never presented as new hardware measurements.
    for key in ('mc_current_packet_hex','mc_current_detail_hex','mc_current_quality_hex','mc_zero_history_hex'):
        raw=bytearray.fromhex(s[key]);assert len(raw)%43==0
        for i in range(0,len(raw),43):
            raw[i+6:i+10]=p.NEW[1].to_bytes(4,'little');raw[i+39:i+43]=h.current_crc32c(raw[i:i+39]).to_bytes(4,'little')
        s[key]=raw.hex()
    assert h.with_zero_history(h.with_shunt_currents(copy.deepcopy(s)))['mc_zero_history_valid']==1
    assert h.manual_scalar_supported(dict(s,manual_scalar_capable=1))
    identity=dict(fw_build=p.OLD[0],mc_fw_build=p.OLD[1],rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
    assert h._vbus_calibration_identity_matches(identity,dict(identity,fw_build=p.NEW[0],mc_fw_build=p.NEW[1]))
    raw=bytearray.fromhex(original_capture['pwm_hex']);raw[4:8]=p.NEW[1].to_bytes(4,'little')
    decoded=h.with_i2c_first_fault(dict(s,enc_fault_first_hex='-',enc_fault_pwm_hex=raw.hex()))
    assert decoded['enc_fault_decode_valid']==1 and decoded['enc_fault_records'][0]['cause']=='BUSY'
    assert h.with_i2c_first_fault(dict(s,enc_fault_pwm_hex=original_capture['pwm_hex']))['enc_fault_decode_valid']==0
    checks.append('Actual HMI decodes old captured record; compatible re-identified zero/current/capture contracts pass; mixed peer rejects; calibration identity retained')
    ui=json.loads(subprocess.check_output(['node',str(p.ROOT/'tools/current_shunt_ui_selftest.js'),str(c/'web_hmi/static/app.js')],text=True));assert ui['passed']
    stem='ACIM-NUCLEOG431RB-IPM15B-VF_OL';debug=c/'nucleo/STM32CubeIDE/Debug'
    manifest=json.loads(p.read(debug/(stem+'.build-manifest.json')))
    assert manifest['firmware_build_id']==p.NEW[1] and manifest['build_errors']==manifest['build_warnings']==0
    def end(base):return int(re.search(r'0x([0-9a-f]+)\s+PROVIDE \(_end =',p.read(base/(stem+'.map')))[1],16)
    delta=end(debug)-end(p.NUC/'nucleo/STM32CubeIDE/Debug');margin=0x20008000-end(debug)-0x600
    assert 0<=delta<=128 and margin>=3500
    stacks=p.read(debug/'Application/User/nucleo_encoder.su')
    capture_stack=int(re.search(r':capture_before_reset\s+(\d+)\s',stacks)[1]);assert capture_stack<=64
    adc=int(re.search(r':mic_current_adc_irq\s+(\d+)\s',p.read(debug/'Application/User/current_shunt.su'))[1]);assert adc==376
    b=json.loads(p.read(c/'build/uno/unoq_mcsdk_scalar.build-manifest.json'));assert b['firmware_build_id']==p.NEW[0]
    for rel,digest in b['library_override_sha256'].items():assert p.sha(c/'libraries'/rel)==digest.lower()
    cache=Path.home()/'AppData/Local/arduino/sketches';dependency_proof=False
    for folder in cache.iterdir():
        dep=folder/'sketch/UNOQ_MOTOR.ino.cpp.d'
        if not dep.is_file():continue
        text=dep.read_text().replace('\\\n','').replace('\\','/')
        if str(c/'libraries').replace('\\','/') not in text:continue
        singleton=folder/'libraries/Arduino_RouterBridge/singletons.cpp.d'
        st=singleton.read_text().replace('\\\n','').replace('\\','/')
        for rel in ('Arduino_RouterBridge/src/bridge.h','Arduino_RPClite/src/decoder.h'):
            path=str(c/'libraries'/rel).replace('\\','/')
            assert path in text and path in st,rel
        p.write(v/'uno_dependencies.txt',text);p.write(v/'singleton_dependencies.txt',st)
        dependency_proof=True
    assert dependency_proof,'Both sketch and Bridge singleton must use the packaged RPC headers'
    assert json.loads(p.read(c/'build/uno/llext-check.json'))['pass']
    checks.append('Both target builds pass, Nucleo zero warnings; fixed RAM/stack budgets and loader relocation constraints retained')
    result=dict(passed=True,hardware_commands=0,checks=checks,capture_test=cap,replay=replay,
        nucleo_static_growth_bytes=delta,nucleo_ram_margin_above_heap_stack=margin,
        capture_stack_bytes=capture_stack,adc_irq_stack_bytes=adc,
        hardware_validated=False,sensor_under_pwm_qualified=False)
    p.write(v/'report.json',json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
