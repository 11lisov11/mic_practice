"""Native tests of the exact recorder/driver/receiver and HMI replay. No I/O."""
import copy,json,shutil,subprocess
import prepare_i2c_wire_capture as p
from ipm_break_wifi_selftest import load_module

def run(name,args,cwd=None):
    r=subprocess.run(args,capture_output=True,text=True,timeout=45,cwd=cwd)
    p.write(p.OUT/'verification'/(name+'.log'),r.stdout+r.stderr)
    if r.returncode:print(r.stdout+r.stderr);r.check_returncode()
    return r.stdout

def main():
    c=p.OUT;v=c/'verification';mock=v/'mock';mock.mkdir(exist_ok=True)
    for f in (p.BASE/'verification/mock').iterdir():
        if f.is_file():shutil.copy2(f,mock/f.name)
    p.write(mock/'main.h',p.read(mock/'main.h')+'\n'+p.read(p.RES/'mock_wire_hw.h'))
    compiler=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers']
    inc=['-I',str(mock),'-I',str(c/'nucleo/Inc'),'-I',str(c/'nucleo/Src'),'-I',str(c/'UNOQ_MOTOR')]
    p.write(v/'wire_test.cpp',p.read(p.RES/'wire_test.cpp'))
    exe=v/'wire_test.exe';run('wire_compile',compiler+inc+[str(v/'wire_test.cpp'),'-o',str(exe)])
    wire=[json.loads(run('wire_'+mode,[str(exe),mode],v)) for mode in ('normal','early','clock','conflict','dma_fail')]
    # Add ONLY recorder initialization and assertions to the previous exact
    # successful-read / NACK / STOP-timeout test; use the new real adapter.
    s=p.read(p.ROOT/'tools/i2c_persistent_pe/platform_test.cpp')
    s=p.once(s,'#include "nucleo_encoder.c"','#include "nucleo_encoder.c"\n#include "nucleo_i2c_wire.c"')
    s=p.once(s,' mic_encoder_init();assert(enc.configured',
      ' mic_i2c_wire_init();DMA2->ISR=0x2000;DMA2_Channel4->CNDTR=4090;\n mic_encoder_init();assert(enc.configured')
    s=p.once(s,' assert(fault_ready==3&&fault_record[0][36]',
      ' assert(wire.state==WC_FROZEN&&wire.parent==fault_record[1]);\n assert(fault_ready==3&&fault_record[0][36]')
    s=p.once(s,' printf("{\\"passed',
      ' TIM1->BDTR=0;mic_i2c_wire_service(false);assert(wire.state==WC_READY);\n assert(wire.header[4]==uv3_crc32c((const uint8_t*)fault_record[1],160));\n printf("{\\"passed')
    p.write(v/'platform.cpp',s);exe=v/'platform.exe'
    run('platform_compile',compiler+inc+[str(v/'platform.cpp'),'-o',str(exe)])
    platform=[json.loads(run('platform_'+mode,[str(exe),mode])) for mode in ('normal','lost_pe','missing_hook')]
    p.write(v/'wire_stub.cpp','#include <stdint.h>\nvoid mic_i2c_wire_freeze(const uint32_t*,uint32_t){}\n')
    exe=v/'bus_clear_driver.exe'
    run('bus_driver_compile',compiler+inc+[str(p.ROOT/'tools/sda_idle_bus_clear/driver_test.cpp'),str(v/'wire_stub.cpp'),'-o',str(exe)])
    bus=[json.loads(run('bus_driver_'+str(i),[str(exe),str(i)])) for i in range(3)]
    for name,source in [('bus_core',p.ROOT/'tools/sda_idle_bus_clear/core_test.cpp'),('regression',p.BASE/'verification/regression.cpp')]:
        p.write(v/'record_fixture.h',p.identity(p.read(p.BASE/'verification/record_fixture.h')))
        exe=v/(name+'.exe');run(name+'_compile',compiler+inc+['-I',str(v),str(source),'-o',str(exe)])
        result=json.loads(run(name,[str(exe)]))
        p.write(v/(name+'.json'),json.dumps(result,indent=2)+'\n')
    h=load_module(c/'web_hmi/server.py');old=load_module(p.BASE/'web_hmi/server.py');checks=0
    raw=(v/'wire_fixture.bin').read_bytes();parent=(v/'wire_parent.bin').read_bytes()
    record=h.decode_i2c_wire(raw,parent);assert record['digital_record_valid'] and record['samples']==4096;checks+=1
    # Invalid/mismatched fault parent, timestamp, peer and every record-byte corruption.
    base=dict(mc_fw_build=p.NEW[1],enc_fault_decode_valid=1,enc_fault_pwm_hex=parent.hex(),enc_wire_hex=raw.hex(),enc_wire_crc=f'{h.crc32c(raw):08x}')
    assert h.with_i2c_wire(base)['enc_wire_decode_valid']==1;checks+=1
    for i in range(len(raw)):
        b=bytearray(raw);b[i]^=1
        assert h.with_i2c_wire(dict(base,enc_wire_hex=b.hex()))['enc_wire_decode_valid']==0;checks+=1
    for key,value in [('mc_fw_build',p.OLD[1]),('enc_fault_decode_valid',0),('enc_fault_pwm_hex','-'),('enc_wire_crc','123'),('enc_wire_hex','f')]:
        assert h.with_i2c_wire(dict(base,**{key:value}))['enc_wire_decode_valid']==0;checks+=1
    # Independently specified digital START / address0x36W / NACK / STOP.
    samples=[3]*500+[1]*48
    for bit in [(0x6c>>b)&1 for b in range(7,-1,-1)]+[1]:
        samples += [bit*2]*48+[bit*2+1]*48
    samples += [0]*48+[1]*48+[3]*48
    samples += [3]*(4096-len(samples))
    fixture=bytearray(raw)
    for j in range(1024):fixture[48+j]=sum(samples[4*j+k]<<(2*k) for k in range(4))
    saved=dict(base,enc_fault_first_hex='-',enc_wire_hex=fixture.hex(),enc_wire_crc=f'{h.crc32c(fixture):08x}')
    decoded=h.with_i2c_first_fault(saved)
    assert decoded['enc_fault_decode_valid']==decoded['enc_wire_decode_valid']==1
    expected=[dict(sample=500+48+8*96+48,value=0x6c,ack=False)]
    assert decoded['enc_wire_record']['bytes']==expected
    assert decoded['enc_wire_record']['starts']==[500] and decoded['enc_wire_record']['stops']==[1508];checks+=1
    p.write(v/'synthetic_address_nack_status.json',json.dumps(saved,indent=2)+'\n')
    p.write(v/'decoder_known_address_test.json',json.dumps(dict(passed=True,synthetic=True,decoded_bytes=expected,hardware_commands=0),indent=2)+'\n')
    for flags in range(256):
        assert h.sd_live_status(dict(mc_fw_build=p.NEW[1],mc_age_ms=20,bp_temp_flags=flags))==old.sd_live_status(dict(mc_fw_build=p.OLD[1],mc_age_ms=20,bp_temp_flags=flags));checks+=1
    s=json.loads(p.read(p.BASE/'preserved_records/runtime_idle_r2/report.json'))['last']
    assert h.with_i2c_first_fault(copy.deepcopy(s))['enc_fault_decode_valid']==1;checks+=1
    # New-pair calibration identity and all current/zero packet decoders.
    s=copy.deepcopy(s);s.update(fw_build=p.NEW[0],mc_fw_build=p.NEW[1],bp_fw_build=p.NEW[1])
    for key in ('mc_current_packet_hex','mc_current_detail_hex','mc_current_quality_hex','mc_zero_history_hex'):
        b=bytearray.fromhex(s[key]);assert len(b)%43==0
        for i in range(0,len(b),43):
            b[i+6:i+10]=p.NEW[1].to_bytes(4,'little');b[i+39:i+43]=h.current_crc32c(b[i:i+39]).to_bytes(4,'little')
        s[key]=b.hex()
    assert h.with_zero_history(h.with_shunt_currents(s))['mc_zero_history_valid']==1;checks+=1
    assert h.manual_scalar_supported(dict(s,manual_scalar_capable=1));checks+=1
    assert h._vbus_calibration_identity_matches(dict(fw_build=p.OLD[0],mc_fw_build=p.OLD[1],rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1),dict(fw_build=p.NEW[0],mc_fw_build=p.NEW[1],rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1));checks+=1
    # Decoder extension must not silently change any older supported identity.
    for peer in (2026102604,2026102702,2026102704,2026102706,2026102708,p.OLD[1]):
        b=bytearray(parent);b[0:4]=(0x31434649).to_bytes(4,'little');b[4:8]=peer.to_bytes(4,'little');b[16:20]=(2).to_bytes(4,'little');b[128:132]=(170000000).to_bytes(4,'little')
        h.decode(bytes(b),peer,1);checks+=1
    # All protection, PWM, ADC, stop, I2C core and RPC sources identical apart
    # from version IDs. Only explicitly enumerated diagnostic files may differ.
    allowed={'nucleo':{'Src/main.c','Src/nucleo_encoder.c','Inc/nucleo_encoder.h','STM32CubeIDE/.project'},
       'UNOQ_MOTOR':{'UNOQ_MOTOR.ino'},'web_hmi':{'server.py'},'libraries':set()}
    protected=0
    for folder in allowed:
        for f in (p.BASE/folder).rglob('*'):
            rel=f.relative_to(p.BASE/folder);key=str(rel).replace('\\','/')
            if not f.is_file() or any(x in ('Debug','Release','__pycache__','.settings') for x in rel.parts):continue
            g=c/folder/rel
            if key in allowed[folder]:continue
            if f.read_bytes()!=g.read_bytes():assert p.read(g)==p.identity(p.read(f)),str(g)
            protected+=1
    # Adapter differs exactly by the passive hook and the readiness getter.
    s=p.read(c/'nucleo/Src/nucleo_encoder.c').replace('#include "nucleo_i2c_wire.h"\n','')
    s=s.replace('  if(wanted&2U)mic_i2c_wire_freeze(fault_record[1],cycles);\n','').replace('bool mic_encoder_pwm_fault_ready(void){return (fault_ready&2U)!=0;}\n','')
    assert s==p.identity(p.read(p.BASE/'nucleo/Src/nucleo_encoder.c'))
    # Reconstruct the original complete main.c after removing the explicitly
    # reviewed diagnostic additions, so no START/CLEAR/STOP/protection body is
    # silently exempted by the changed-file allowlist.
    s=p.read(c/'nucleo/Src/main.c')
    s=s.replace('#include "nucleo_i2c_wire.h"\n#include "wire_capture.h"\n','')
    s=s.replace('volatile uint8_t mic_bkin_ring','volatile uint16_t mic_bkin_ring')
    s=s.replace('  /* Unchanged WORD GPIO read; retain low byte containing PA4 and PA6.\n     All8192 samples, sample rate and SD pulse processing are unchanged. */\n  hdma_mic_bkin.Init.MemDataAlignment=DMA_MDATAALIGN_BYTE;',
      '  /* GPIO is read as a word; DMA stores its low 16 bits, including PA6. */\n  hdma_mic_bkin.Init.MemDataAlignment=DMA_MDATAALIGN_HALFWORD;')
    begin=s.index('static void mic_send_i2c_wire_page(');end=s.index('static void mic_send_encoder_page(',begin)
    s=s[:begin]+s[end:]
    s=s.replace('  mic_i2c_wire_init();\n','').replace('    mic_i2c_wire_service(off_low_bus);\n    mic_send_i2c_wire_page(HAL_GetTick());\n','')
    s=s.replace('    const bool off_low_bus=!uno_link.command_enabled','    mic_encoder_allow_bus_clear(!uno_link.command_enabled')
    s=s.replace('<20U;\n    mic_encoder_allow_bus_clear(off_low_bus);','<20U);')
    assert s==p.identity(p.read(p.BASE/'nucleo/Src/main.c'))
    for rel,d in json.loads(p.read(c/'preserved_records/reference_sha256.json')).items():assert p.sha(p.ROOT/rel)==d
    result=dict(passed=True,hardware_commands=0,wire_native=wire,platform=platform,bus_driver=bus,
       hmi_checks=checks,unchanged_protected_files=protected,protection_source_isolation=True,
       adc_pwm_thresholds_unchanged=True,i2c_cleanup_unchanged=True,old_records_preserved=True,
       hardware_sampling_latency_qualified=False)
    p.write(v/'native_report.json',json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
