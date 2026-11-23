"""Validate driver, protocol, recorded decoder compatibility and isolation."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import prepare_nucleo_as5600 as p
import prepare_current_shunt_monitor as u
from audit_production_pwm_filters import function
from current_zero_quality import ready

def main():
    c=p.OUT;out=c/'verification';checks=[]
    exe=out/'encoder_selftest.exe'
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(c/'UNOQ_MOTOR'),
        '-I',str(p.RES),str(p.RES/'selftest.cpp'),'-o',str(exe)],check=True)
    result=json.loads(subprocess.check_output([str(exe)],text=True));assert result['passed']
    u.write(out/'encoder_selftest.json',json.dumps(result,indent=2)+'\n');checks.append('Driver state machine, timeout/wrap/error recovery and encoder wire/age/CRC: '+str(result['checks']))
    for rel in ('nucleo/Src/current_shunt.c','nucleo/Src/mc_tasks.c','nucleo/Src/stm32g4xx_mc_it.c',
                'nucleo/Src/stm32g4xx_it.c','nucleo/Inc/current_core.h','nucleo/Inc/current_adc_window_plan.h',
                'nucleo/Inc/current_adc_deadline.h','nucleo/Inc/acim_vf_parameters.h'):
        assert (c/rel).read_bytes()==(p.NUC/rel).read_bytes(),rel
    old=u.read(p.NUC/'nucleo/Src/main.c');new=u.read(c/'nucleo/Src/main.c').replace(str(p.NEW[1]),str(p.OLD[1]))
    for name in ('SystemClock_Config','uno_link_poll','uno_send_reply',
                 'mic_send_break_page','mic_send_current_page','mic_send_peak_page'):
        a,b=function(old,name),function(new,name)
        assert a==b,name
    driver=u.read(c/'nucleo/Src/nucleo_encoder.c')+u.read(c/'nucleo/Inc/encoder_core.h')
    for token in ('while (','while(','__disable_irq','HAL_Delay','HAL_I2C_Mem_Read','TIM1','NVIC_'):
        assert token not in driver,token
    uno=u.read(c/'UNOQ_MOTOR/UNOQ_MOTOR.ino')
    assert 'as5600_teacher_begin();' not in uno and 'as5600_diag_select(mode)' not in uno
    for name in ('hard_stop','control_step','nucleo_send_pwm','nucleo_check_reply'):
        original=function(u.read(p.UNO/'UNOQ_MOTOR/UNOQ_MOTOR.ino'),name)
        changed=function(uno,name).replace(str(p.NEW[0]),str(p.OLD[0])).replace(str(p.NEW[1]),str(p.OLD[1]))
        assert original==changed,name
    checks.append('ADC, PWM, V/f, hardware Break, UART commands/watchdogs and MCU5s STOP unchanged; driver has no blocking waits or IRQ masking')
    f=c/'web_hmi/server.py';ast.parse(u.read(f));spec=importlib.util.spec_from_file_location('nucleo_encoder_hmi',f)
    h=importlib.util.module_from_spec(spec);sys.modules[spec.name]=h;spec.loader.exec_module(h)
    s=json.loads((p.ROOT/'artifacts/live_bench_20261026/as5600_followup_r1/poll100_aligned_magnet_5hz_r1/report.json').read_text())['before']
    assert h.with_zero_history(h.with_shunt_currents(copy.deepcopy(s)))['mc_zero_history_valid']==1
    s.update(fw_build=p.NEW[0],mc_fw_build=p.NEW[1],bp_fw_build=p.NEW[1])
    for key in ('mc_current_packet_hex','mc_current_detail_hex','mc_current_quality_hex','mc_zero_history_hex'):
        raw=bytearray.fromhex(s[key]);assert len(raw)%43==0
        for i in range(0,len(raw),43):
            raw[i+6:i+10]=p.NEW[1].to_bytes(4,'little')
            raw[i+39:i+43]=h.current_crc32c(raw[i:i+39]).to_bytes(4,'little')
        s[key]=raw.hex()
    decoded=h.with_zero_history(h.with_shunt_currents(copy.deepcopy(s)))
    assert decoded['mc_zero_history_valid']==1 and ready(decoded),decoded.get('mc_zero_history_status')
    assert not ready(dict(decoded,mc_current_flags=16))
    bad=copy.deepcopy(s);raw=bytearray.fromhex(bad['mc_zero_history_hex']);raw[15]^=1;bad['mc_zero_history_hex']=raw.hex()
    assert h.with_zero_history(bad)['mc_zero_history_valid']==0
    assert h.with_zero_history(dict(s,fw_build=2026102699))['mc_zero_history_valid']==0
    peak=json.loads((p.ROOT/'artifacts/live_bench_20261025/as5600_software_regression_r1/legacy_powered_5hz_r1/after_diagnostics.json').read_text())
    raw=bytearray.fromhex(peak['mc_adc_peak_hex']);raw[8:12]=p.NEW[1].to_bytes(4,'little');raw[60:64]=bytes(4)
    raw[60:64]=h.current_crc32c(raw).to_bytes(4,'little')
    peak.update(fw_build=p.NEW[0],mc_fw_build=p.NEW[1],mc_adc_peak_hex=raw.hex())
    assert h.with_adc_peak(peak)['mc_adc_peak_valid']==1
    stored=dict(fw_build=p.OLD[0],mc_fw_build=p.OLD[1],rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
    assert h._vbus_calibration_identity_matches(stored,dict(stored,fw_build=p.NEW[0],mc_fw_build=p.NEW[1]))
    assert h.manual_scalar_supported(dict(s,manual_scalar_capable=1))
    parsed=h.RpcBridge._parse_status_string('DATA state=SAFE mode=VF pwm=0 enc_source=nucleo_g431_i2c1 enc_peer_good=8 enc_peer_bad=0 enc_diag_mode=6 enc_diag_category_counts_available=0')
    assert parsed['enc_source']=='nucleo_g431_i2c1' and parsed['enc_peer_good']==8 and parsed['enc_diag_category_counts_available']==0
    done=dict(decoded,run_id=1,run_reason=1,run_start_ms=1000,run_stop_ms=6000,run_elapsed_ms=5000,run_limit_ms=5000)
    assert h.bounded_run_complete(done,dict(run_id=0),5)
    assert not h.bounded_run_complete(dict(done,mc_fault=1),dict(run_id=0),5)
    checks.append('Real recorded ADC/zero history/peak/calibration/manual/timed completion pipeline accepts new pair; corrupt CRC, bad zero and unknown firmware rejected')
    ui=subprocess.run(['node',str(p.ROOT/'tools/current_shunt_ui_selftest.js'),str(c/'web_hmi/static/app.js')],capture_output=True,text=True,check=True,timeout=30)
    u.write(out/'frontend.json',ui.stdout);assert json.loads(ui.stdout)['passed']
    checks.append('Web current/invalid-state tests pass; encoder source and validity retained')
    report=dict(passed=True,hardware_commands=0,checks=checks,driver_checks=result['checks'],hardware_validated=False)
    u.write(out/'report.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
