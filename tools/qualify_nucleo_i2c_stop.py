"""Offline isolation, target memory, transport/HMI and loader audit."""
import copy,json,re,subprocess
from pathlib import Path
import prepare_nucleo_i2c_stop as p
from ipm_break_wifi_selftest import load_module
from audit_production_pwm_filters import function
def norm(s):return s.replace(str(p.NEW[0]),str(p.OLD[0])).replace(str(p.NEW[1]),str(p.OLD[1]))
def main():
 c=p.OUT;v=c/'verification';checks=[]
 core=json.loads(p.read(v/'core_report.json'));assert core['passed'] and core['platform']['passed']
 allowed={'nucleo':{'Inc/encoder_core.h','Inc/fault_wire.h','Inc/nucleo_encoder.h','Src/nucleo_encoder.c','Src/main.c'},'UNOQ_MOTOR':{'UNOQ_MOTOR.ino','fault_wire.h'}}
 for folder in allowed:
  for f in (p.BASE/folder).rglob('*'):
   rel=f.relative_to(p.BASE/folder)
   if not f.is_file() or any(x in ('Debug','Release','__pycache__','.settings') for x in rel.parts):continue
   if str(rel).replace('\\','/') in allowed[folder]:continue
   new=c/folder/rel
   if new.read_bytes()!=f.read_bytes():assert norm(p.read(new))==p.read(f),str(rel)
 for folder in ('libraries','web_hmi/static'):
  for f in (p.BASE/folder).rglob('*'):
   if f.is_file():assert f.read_bytes()==(c/folder/f.relative_to(p.BASE/folder)).read_bytes(),str(f)
 # Remove ONLY the explicit new diagnostic additions; remaining entire files
 # must match the installed version including every motor/control function.
 s=norm(p.read(c/'nucleo/Src/main.c'))
 s=s.replace('#include "fault_wire.h"\n#include "encoder_health_wire.h"','#include "fault_wire.h"')
 s=s.replace(p.read(p.RES/'health_sender.inc')+'\n','')
 s=s.replace('\n    mic_send_encoder_health_page(HAL_GetTick());','')
 assert s==p.read(p.BASE/'nucleo/Src/main.c'),'main control source isolation'
 s=norm(p.read(c/'UNOQ_MOTOR/UNOQ_MOTOR.ino'))
 s=s.replace('\n#include "encoder_health_wire.h"\nstatic eh_receiver g_encoder_health={};','')
 s=s.replace(p.read(p.RES/'health_rx.inc')+'\n','')
 s=s.replace(p.read(p.RES/'health_text.inc'),'    s += " enc_diag_category_counts_available=0";')
 for name,index in [('berr_count',7),('arlo_count',3),('busy_count',2),('graceful_cleanups',8),('nack_count',0)]:
  s=s.replace('String((unsigned long)(health_valid?g_encoder_health.values['+str(index)+']:0))','String((unsigned long)g_as5600.diag_'+name+')')
 s=s.replace('\n  if(g_pwm_enabled || (g_bp_status&0x22U) || !g_bp_mcsdk_telemetry || g_bp_fw_build!=EH_PEER || (uint32_t)(poll_ms-g_bp_last_rsp_ms)>=300U){g_encoder_health.valid=false;g_encoder_health.mask=0;}','')
 # A replacement resource ends in LF, while the old replaced line did not.
 assert s.replace('\n\n    s += " enc_bus_ok=', '\n    s += " enc_bus_ok=')==p.read(p.BASE/'UNOQ_MOTOR/UNOQ_MOTOR.ino'),'Uno control/timed-stop isolation'
 for name in ('ec_track','ec_speed_reset','ec_init'):
  assert function(p.read(c/'nucleo/Inc/encoder_core.h'),name)==function(p.read(p.BASE/'nucleo/Inc/encoder_core.h'),name),name
 for name in ('mic_encoder_init','mic_encoder_packet','mic_encoder_fault_packet','config_ok'):
  assert norm(function(p.read(c/'nucleo/Src/nucleo_encoder.c'),name))==function(p.read(p.BASE/'nucleo/Src/nucleo_encoder.c'),name),name
 checks.append('Whole motor/PWM/ADC/Break/watchdog/control-UART/timed-stop sources match installed version after removing explicit diagnostics and build IDs; feedback validity/continuity unchanged')
 h=load_module(c/'web_hmi/server.py')
 capture=json.loads(p.read(p.BASE/'powered_first_fault_5hz_r1/trial/first_i2c_capture.json'))
 old=bytes.fromhex(capture['pwm_hex']);assert h.decode(old,p.OLD[1],1)['cause']=='NACK'
 raw=bytearray(old);raw[4:8]=p.NEW[1].to_bytes(4,'little');meta=int.from_bytes(raw[16:20],'little')|(9<<26);raw[16:20]=meta.to_bytes(4,'little')
 d=h.decode(raw,p.NEW[1],1);assert d['cleanup_stop_seen'] and d['cleanup_stop_requested'] and 'post_reset_isr' not in d
 assert d['received_bytes']==0 and d['cause']=='NACK'
 try:h.decode(old,p.NEW[1],1)
 except ValueError:pass
 else:raise AssertionError('mixed peer record accepted')
 s=copy.deepcopy(json.loads(p.read(p.BASE/'powered_first_fault_5hz_r1/trial/report.json'))['final_status'])
 s.update(fw_build=p.NEW[0],mc_fw_build=p.NEW[1],bp_fw_build=p.NEW[1])
 for key in ('mc_current_packet_hex','mc_current_detail_hex','mc_current_quality_hex','mc_zero_history_hex'):
  raw=bytearray.fromhex(s[key]);assert len(raw)%43==0
  for i in range(0,len(raw),43):raw[i+6:i+10]=p.NEW[1].to_bytes(4,'little');raw[i+39:i+43]=h.current_crc32c(raw[i:i+39]).to_bytes(4,'little')
  s[key]=raw.hex()
 assert h.with_zero_history(h.with_shunt_currents(copy.deepcopy(s)))['mc_zero_history_valid']==1
 assert h.manual_scalar_supported(dict(s,manual_scalar_capable=1))
 identity=dict(fw_build=p.OLD[0],mc_fw_build=p.OLD[1],rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
 assert h._vbus_calibration_identity_matches(identity,dict(identity,fw_build=p.NEW[0],mc_fw_build=p.NEW[1]))
 ui=json.loads(subprocess.check_output(['node',str(p.ROOT/'tools/current_shunt_ui_selftest.js'),str(c/'web_hmi/static/app.js')],text=True));assert ui['passed']
 checks.append('Actual HMI old/new capture semantics, mixed-peer rejection, re-identified current/autozero contracts, calibration compatibility and current UI pass; re-identified bytes are contract tests, not hardware data')
 stem='ACIM-NUCLEOG431RB-IPM15B-VF_OL';debug=c/'nucleo/STM32CubeIDE/Debug'
 build=json.loads(p.read(debug/(stem+'.build-manifest.json')));assert build['firmware_build_id']==p.NEW[1] and build['build_errors']==build['build_warnings']==0
 def end(base):return int(re.search(r'0x([0-9a-f]+)\s+PROVIDE \(_end =',p.read(base/(stem+'.map')))[1],16)
 delta=end(debug)-end(p.BASE/'nucleo/STM32CubeIDE/Debug');margin=0x20008000-end(debug)-0x600
 assert 0<=delta<=256 and margin>=3384,(delta,margin)
 stack=p.read(debug/'Application/User/nucleo_encoder.su')
 capture_stack=int(re.search(r':capture_before_reset\s+(\d+)\s',stack)[1]);terminal_stack=int(re.search(r':capture_terminal\s+(\d+)\s',stack)[1]);assert max(capture_stack,terminal_stack)<=64
 adc=int(re.search(r':mic_current_adc_irq\s+(\d+)\s',p.read(debug/'Application/User/current_shunt.su'))[1]);assert adc==376
 b=json.loads(p.read(c/'build/uno/unoq_mcsdk_scalar.build-manifest.json'));assert b['firmware_build_id']==p.NEW[0]
 for rel,digest in b['library_override_sha256'].items():assert p.sha(c/'libraries'/rel)==digest.lower()
 assert json.loads(p.read(c/'build/uno/llext-check.json'))['pass']
 proof=False
 for folder in (Path.home()/'AppData/Local/arduino/sketches').iterdir():
  dep=folder/'sketch/UNOQ_MOTOR.ino.cpp.d'
  if not dep.is_file():continue
  text=dep.read_text().replace('\\\n','').replace('\\','/')
  if str(c/'libraries').replace('\\','/') not in text:continue
  st=(folder/'libraries/Arduino_RouterBridge/singletons.cpp.d').read_text().replace('\\\n','').replace('\\','/')
  for rel in ('Arduino_RouterBridge/src/bridge.h','Arduino_RPClite/src/decoder.h'):
   path=str(c/'libraries'/rel).replace('\\','/');assert path in text and path in st,rel
  p.write(v/'uno_dependencies.txt',text);p.write(v/'singleton_dependencies.txt',st);proof=True
 assert proof
 checks.append('Both target builds pass; Nucleo zero warnings, RAM/stack budgets, packaged RPC headers for BOTH compilation units and loader relocation checks pass')
 result=dict(passed=True,hardware_commands=0,core=core,checks=checks,nucleo_static_growth_bytes=delta,nucleo_ram_margin_above_heap_stack=margin,capture_stack_bytes=capture_stack,terminal_stack_bytes=terminal_stack,adc_irq_stack_bytes=adc,hardware_validated=False,sensor_under_pwm_qualified=False)
 p.write(v/'report.json',json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
