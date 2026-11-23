"""Check frozen capture, wire integrity, existing protection code and target budgets."""
import copy
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import prepare_i2c_first_fault as p
from audit_production_pwm_filters import function

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod;spec.loader.exec_module(mod);return mod

def main():
    c=p.OUT;v=c/'verification';checks=[]
    cmd=['g++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(c/'nucleo/Inc'),
         '-I',str(c/'UNOQ_MOTOR'),'-I',str(p.RES)]
    subprocess.run(cmd+[str(p.RES/'selftest.cpp'),'-o',str(v/'first_fault_test.exe')],check=True)
    capture=json.loads(subprocess.check_output([str(v/'first_fault_test.exe')],text=True));assert capture['passed']
    checks.append('Actual capture hook executes before state/error reset, distinguishes first boot/PWM, retains records, validates pages/CRC/padding/peer/OFF contract')
    source=p.read(p.ROOT/'tools/nucleo_as5600/selftest.cpp').replace(
        'return {m,stat,begin,write,rbegin,read,clear,reset};','return {m,stat,begin,write,rbegin,read,clear,reset,nullptr};')
    test=v/'legacy_driver.cpp';p.write(test,source)
    subprocess.run(cmd+[str(test),'-o',str(v/'legacy_driver.exe')],check=True)
    legacy=json.loads(subprocess.check_output([str(v/'legacy_driver.exe')],text=True));assert legacy['passed']
    checks.append('Existing I2C and sensor wire model: '+str(legacy['checks'])+' checks')
    for rel in ('Src/current_shunt.c','Src/mc_tasks.c','Src/stm32g4xx_mc_it.c','Src/stm32g4xx_it.c',
                'Inc/current_core.h','Inc/current_adc_window_plan.h','Inc/current_adc_deadline.h','Inc/acim_vf_parameters.h'):
        assert (c/'nucleo'/rel).read_bytes()==(p.NUC/'nucleo'/rel).read_bytes(),rel
    old=p.read(p.NUC/'nucleo/Src/main.c');new=p.read(c/'nucleo/Src/main.c').replace(str(p.NEW[1]),str(p.OLD[1]))
    for name in ('SystemClock_Config','uno_link_poll','uno_send_reply','uno_tx_watchdog',
                 'mic_send_current_page','mic_send_peak_page','mic_send_break_page'):
        assert function(old,name)==function(new,name),name
    old=p.read(p.UNO/'UNOQ_MOTOR/UNOQ_MOTOR.ino');new=p.read(c/'UNOQ_MOTOR/UNOQ_MOTOR.ino')
    for name in ('hard_stop','control_step','nucleo_send_pwm','nucleo_check_reply'):
        text=function(new,name).replace(str(p.NEW[0]),str(p.OLD[0])).replace(str(p.NEW[1]),str(p.OLD[1]))
        assert function(old,name)==text,name
    assert (c/'UNOQ_MOTOR/nucleo_buffered_serial.h').read_bytes()==(p.UNO/'UNOQ_MOTOR/nucleo_buffered_serial.h').read_bytes()
    ec=p.read(c/'nucleo/Inc/encoder_core.h')
    ec=ec.replace('  void (*fault)(void*,uint8_t,uint32_t,uint32_t,uint32_t);\n','')
    ec=ec.replace('  if(cause && io->fault)io->fault(io->ctx,cause,isr,ms,cycles);\n','')
    assert ec==p.read(p.NUC/'nucleo/Inc/encoder_core.h')
    driver=p.read(c/'nucleo/Src/nucleo_encoder.c')
    for forbidden in ('__disable_irq','irq_lock','HAL_Delay','HAL_I2C_Mem_Read','->RXDR','->TXDR'):
        assert forbidden not in driver,forbidden
    sender=function(p.read(c/'nucleo/Src/main.c'),'mic_send_encoder_fault_page')
    assert 'LL_TIM_IsEnabledAllOutputs(TIM1)' in sender and 'UNO_TX_TAG_DIAG' in sender
    checks.append('PWM/ADC/SD/UART commands/protections/Uno MCU deadline and RX handoff unchanged; no new sensor recovery/filter policy')
    h=load('i2c_first_fault_hmi',c/'web_hmi/server.py')
    s=json.loads((p.UNO/'powered_5hz_r1/after_diagnostics.json').read_text())
    s.update(fw_build=p.NEW[0],mc_fw_build=p.NEW[1],bp_fw_build=p.NEW[1])
    for key in ('mc_current_packet_hex','mc_current_detail_hex','mc_current_quality_hex','mc_zero_history_hex'):
        raw=bytearray.fromhex(s[key]);assert len(raw)%43==0
        for i in range(0,len(raw),43):
            raw[i+6:i+10]=p.NEW[1].to_bytes(4,'little');raw[i+39:i+43]=h.current_crc32c(raw[i:i+39]).to_bytes(4,'little')
        s[key]=raw.hex()
    assert h.with_zero_history(h.with_shunt_currents(copy.deepcopy(s)))['mc_zero_history_valid']==1
    stored=dict(fw_build=p.OLD[0],mc_fw_build=p.OLD[1],rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
    assert h._vbus_calibration_identity_matches(stored,dict(stored,fw_build=p.NEW[0],mc_fw_build=p.NEW[1]))
    assert h.manual_scalar_supported(dict(s,manual_scalar_capable=1))
    import struct
    w=[0]*40;w[0]=0x31434649;w[1]=p.NEW[1];w[4]=11|(4<<8);w[7]=0x300;w[16]=32768;w[32]=170000000;w[26]=8;w[35]=1
    raw=struct.pack('<40I',*w)
    decoded=h.with_i2c_first_fault(dict(s,enc_fault_first_hex='-',enc_fault_pwm_hex=raw.hex()))
    assert decoded['enc_fault_decode_valid']==1 and decoded['enc_fault_records'][0]['cause']=='BUSY'
    assert decoded['enc_fault_records'][0]['errors_before']==8 and decoded['enc_fault_records'][0]['post_reset_isr']==1
    parsed=h.RpcBridge._parse_status_string('DATA state=SAFE mode=VF pwm=0 enc_fault_first_hex=- enc_fault_pwm_hex='+raw.hex()+' enc_fault_good=7 enc_fault_bad=0')
    assert parsed['enc_fault_pwm_hex']==raw.hex() and parsed['enc_fault_good']==7
    assert h.with_i2c_first_fault(dict(s,mc_fw_build=1,enc_fault_pwm_hex=raw.hex()))['enc_fault_decode_valid']==0
    assert h.with_i2c_first_fault(dict(s,enc_fault_pwm_hex='garbage'))['enc_fault_decode_valid']==0
    checks.append('Real recorded ADC/zero/calibration/manual compatibility and new HMI first-fault decoder checked; wrong firmware/malformed records rejected')
    ui=json.loads(subprocess.check_output(['node',str(p.ROOT/'tools/current_shunt_ui_selftest.js'),str(c/'web_hmi/static/app.js')],text=True));assert ui['passed']
    name='ACIM-NUCLEOG431RB-IPM15B-VF_OL';debug=c/'nucleo/STM32CubeIDE/Debug'
    manifest=json.loads(p.read(debug/(name+'.build-manifest.json')))
    assert manifest['firmware_build_id']==p.NEW[1] and manifest['build_errors']==manifest['build_warnings']==0
    def end(base):return int(re.search(r'0x([0-9a-f]+)\s+PROVIDE \(_end =',p.read(base/(name+'.map')))[1],16)
    delta=end(debug)-end(p.NUC/'nucleo/STM32CubeIDE/Debug');margin=0x20008000-end(debug)-0x600
    assert 0<delta<=512 and margin>=4016-512
    stack=p.read(debug/'Application/User/nucleo_encoder.su')
    capture_stack=int(re.search(r':capture_before_reset\s+(\d+)\s',stack)[1]);assert capture_stack<=64
    adc=int(re.search(r':mic_current_adc_irq\s+(\d+)\s',p.read(debug/'Application/User/current_shunt.su'))[1]);assert adc==376
    b=json.loads(p.read(c/'build/uno/unoq_mcsdk_scalar.build-manifest.json'));assert b['firmware_build_id']==p.NEW[0]
    assert json.loads(p.read(c/'build/uno/llext-check.json'))['pass']
    report=dict(passed=True,hardware_commands=0,checks=checks,capture_test=capture,legacy_checks=legacy['checks'],
        target_builds_verified=True,nucleo_static_growth_bytes=delta,nucleo_ram_margin_above_heap_stack=margin,
        capture_stack_bytes=capture_stack,adc_irq_stack_bytes=adc,hardware_capture_validated=False,
        non_gating_release_preflight_missing_hil_evidence=True)
    p.write(v/'report.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
