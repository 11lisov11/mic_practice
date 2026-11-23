"""Native actual-driver, wire, source isolation and actual HMI contract checks."""
import copy,json,shutil,subprocess
import prepare_pe_release_capture as p
from ipm_break_wifi_selftest import load_module
def norm(s):return s.replace(str(p.NEW[0]),str(p.OLD[0])).replace(str(p.NEW[1]),str(p.OLD[1]))
def run(v,name,args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=30)
 p.write(v/(name+'.log'),r.stdout+r.stderr)
 if r.returncode:print(r.stdout+r.stderr);r.check_returncode()
 return r.stdout
def main():
 c=p.OUT;v=c/'verification';mock=v/'mock';mock.mkdir(exist_ok=True)
 for f in (p.BASE/'verification/mock').iterdir():
  if f.is_file():shutil.copy2(f,mock/f.name)
 f=mock/'main.h';s=p.read(f)
 s=p.once(s,'static inline void mock_clear','static bool mock_release_scl;\nstatic inline void mock_clear')
 s=p.once(s,'test_i2c.ISR.value=1;','{test_i2c.ISR.value=1;test_i2c.CR2&=~0x400e000U;if(mock_release_scl)test_gpio.IDR|=256;}');p.write(f,s)
 compile=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-I',str(mock),'-I',str(c/'nucleo/Inc'),'-I',str(c/'nucleo/Src')]
 exe=v/'release_platform.exe';run(v,'platform_compile',compile+[str(p.RES/'platform_test.cpp'),'-o',str(exe)])
 results=[json.loads(run(v,'platform_'+mode,[str(exe),mode])) for mode in ('high','low','late','timeout','cancel')]
 h=load_module(c/'web_hmi/server.py');checks=0
 for record in results:
  raw=bytes.fromhex(record['record']);parent=bytes.fromhex(record['parent']);decoded=h.decode_i2c_release(raw,parent,p.NEW[1],1)
  assert decoded['result']==record['result'];checks+=1
  for i in range(len(raw)):
   b=bytearray(raw);b[i]^=1
   try:h.decode_i2c_release(bytes(b),parent,p.NEW[1],1)
   except ValueError:checks+=1
   else:raise AssertionError('Corruption accepted')
  try:h.decode_i2c_release(raw,parent,p.OLD[1],1)
  except ValueError:checks+=1
  else:raise AssertionError('Mixed peer accepted')
  d=h.with_i2c_first_fault(dict(mc_fw_build=p.NEW[1],enc_fault_first_hex='-',enc_fault_pwm_hex=parent.hex(),enc_release_pwm_hex=raw.hex()))
  assert d['enc_fault_decode_valid']==d['enc_release_decode_valid']==1 and d['enc_release_records'][0]['result']==record['result'];checks+=1
  stale=bytearray(parent);stale[8]^=1
  try:h.decode_i2c_release(raw,stale,p.NEW[1],1)
  except ValueError:checks+=1
  else:raise AssertionError('Wrong parent accepted')
 # The entire existing core/cleanup/limits is byte-identical.
 assert (c/'nucleo/Inc/encoder_core.h').read_bytes()==(p.BASE/'nucleo/Inc/encoder_core.h').read_bytes()
 old=p.read(p.BASE/'nucleo/Src/nucleo_encoder.c');new=norm(p.read(c/'nucleo/Src/nucleo_encoder.c'))
 new=new.replace('#include "fault_wire.h"\n#include "release_wire.h"\n'+p.read(p.RES/'driver_helpers.inc'),'#include "fault_wire.h"')
 new=new.replace('(void)I2C1->CR1;__DSB();\n  if(release_pending)release_after_park(DWT->CYCCNT);\n  I2C1->CR2=0;','(void)I2C1->CR1;__DSB();I2C1->CR2=0;')
 new=new.replace('\n    sr_arm(&release_probe[slot],cyc,gpio);release_pending|=(uint8_t)(1U<<slot);','')
 new=new.replace('void mic_encoder_poll(void){\n  release_poll();','void mic_encoder_poll(void){')
 new=new.replace('\n'+p.read(p.RES/'producer.inc'),'');assert new==old,'Unexpected production driver change'
 s=norm(p.read(c/'nucleo/Src/main.c'));s=s.replace('#include "encoder_health_wire.h"\n#include "release_wire.h"','#include "encoder_health_wire.h"').replace(p.read(p.RES/'sender.inc')+'\n','').replace('\n    mic_send_encoder_release_page(HAL_GetTick());','')
 assert s==p.read(p.BASE/'nucleo/Src/main.c'),'Unexpected control/main change'
 s=norm(p.read(c/'UNOQ_MOTOR/UNOQ_MOTOR.ino'));s=s.replace('\n#include "release_wire.h"\nstatic pr_receiver g_release_capture={};','').replace(p.read(p.RES/'uno_rx.inc')+'\n','').replace(p.read(p.RES/'uno_text.inc')+'\n','')
 assert s==p.read(p.BASE/'UNOQ_MOTOR/UNOQ_MOTOR.ino'),'Unexpected Uno control change'
 allowed={'nucleo':{'Src/nucleo_encoder.c','Src/main.c','Inc/nucleo_encoder.h'},'UNOQ_MOTOR':{'UNOQ_MOTOR.ino'},'libraries':set()}
 for folder,skip in allowed.items():
  for f in (p.BASE/folder).rglob('*'):
   rel=f.relative_to(p.BASE/folder)
   if not f.is_file() or any(x in ('Debug','Release','__pycache__','.settings') for x in rel.parts) or str(rel).replace('\\','/') in skip:continue
   g=c/folder/rel
   if f.read_bytes()!=g.read_bytes():assert norm(p.read(g))==p.read(f),str(rel)
 # Calibration/current/zero contract tests re-identify archived frames ONLY.
 fixture=json.loads(p.read(p.BASE/'runtime_usb_r1/report.json'))['last'];s=copy.deepcopy(fixture)
 s.update(fw_build=p.NEW[0],mc_fw_build=p.NEW[1],bp_fw_build=p.NEW[1])
 for key in ('mc_current_packet_hex','mc_current_detail_hex','mc_current_quality_hex','mc_zero_history_hex'):
  raw=bytearray.fromhex(s[key]);assert len(raw)%43==0
  for i in range(0,len(raw),43):raw[i+6:i+10]=p.NEW[1].to_bytes(4,'little');raw[i+39:i+43]=h.current_crc32c(raw[i:i+39]).to_bytes(4,'little')
  s[key]=raw.hex()
 assert h.with_zero_history(h.with_shunt_currents(copy.deepcopy(s)))['mc_zero_history_valid']==1
 assert h.manual_scalar_supported(dict(s,manual_scalar_capable=1))
 identity=dict(fw_build=p.OLD[0],mc_fw_build=p.OLD[1],rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
 assert h._vbus_calibration_identity_matches(identity,dict(identity,fw_build=p.NEW[0],mc_fw_build=p.NEW[1]))
 # Retain native regression of the complete unchanged I2C state machine.
 exe=v/'core_regression.exe';run(v,'core_compile',['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(c/'nucleo/Inc'),'-I',str(p.BASE/'verification'),str(p.ROOT/'tools/nucleo_i2c_stop/selftest.cpp'),'-o',str(exe)])
 core=json.loads(run(v,'core_regression',[str(exe)]));assert core['passed']
 for name,digest in json.loads(p.read(c/'preserved_records/sha256.json')).items():assert p.sha(c/'preserved_records'/name)==digest
 result=dict(passed=True,hardware_commands=0,platform=results,hmi_corruption_and_link_checks=checks,core=core,entire_control_and_recovery_sources_unchanged=True,historical_records_preserved=True,sensor_under_pwm_qualified=False)
 p.write(v/'native_report.json',json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='platform'}))
if __name__=='__main__':main()
