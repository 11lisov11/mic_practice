"""Replay actual startup fault and actual C driver; no hardware access."""
import copy,json,shutil,subprocess
import prepare_sda_idle_bus_clear as p
from ipm_break_wifi_selftest import load_module
def run(name,args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=40);p.write(p.OUT/'verification'/(name+'.log'),r.stdout+r.stderr)
 if r.returncode:print(r.stdout+r.stderr);r.check_returncode()
 return r.stdout
def main():
 c=p.OUT;v=c/'verification';mock=v/'mock';mock.mkdir(exist_ok=True)
 for f in (p.BASE/'verification/mock').iterdir():
  if f.is_file():shutil.copy2(f,mock/f.name)
 f=mock/'main.h';s=p.read(f)
 s=p.once(s,'typedef struct {uint32_t IDR,MODER,OTYPER,AFR[2];} GpioRegs;',
  'static void mock_bsrr(uint32_t);\nstruct BsrrReg {void operator=(uint32_t v){mock_bsrr(v);}};\nstruct GpioRegs {uint32_t IDR=0,MODER=0,OTYPER=0,AFR[2]={},ODR=0;BsrrReg BSRR;};')
 s+='\n#define TIM_BDTR_MOE 32768U\nstatic unsigned mock_gpio_writes,mock_edges,mock_release_on=4;static bool mock_external_sda;\n'
 s+='static void mock_bsrr(uint32_t v){++mock_gpio_writes;uint32_t old=test_gpio.ODR;test_gpio.ODR=(old|(v&65535U))&~(v>>16);if((test_gpio.MODER&(15U<<16))==(5U<<16)){if(!(old&256U)&&(test_gpio.ODR&256U)&&++mock_edges>=mock_release_on)mock_external_sda=false;test_gpio.IDR=(test_gpio.IDR&~0x300U)|(test_gpio.ODR&256U)|((!mock_external_sda&&(test_gpio.ODR&512U))?512U:0U);}}\n'
 p.write(f,s)
 includes=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-I',str(mock),'-I',str(c/'nucleo/Inc'),'-I',str(c/'nucleo/Src')]
 exe=v/'bus_clear_core.exe';run('core_compile',includes+[str(p.RES/'core_test.cpp'),'-o',str(exe)]);core=json.loads(run('core_test',[str(exe)]))
 exe=v/'bus_clear_driver.exe';run('driver_compile',includes+[str(p.RES/'driver_test.cpp'),'-o',str(exe)]);drivers=[json.loads(run('driver_'+str(i),[str(exe),str(i)])) for i in range(3)]
 h=load_module(c/'web_hmi/server.py');checks=0
 old_h=load_module(p.BASE/'web_hmi/server.py')
 # Every unchanged SD flag combination keeps identical semantics for both IDs.
 for flags in range(256):
  expected=old_h.sd_live_status(dict(mc_fw_build=2026102704,mc_age_ms=20,bp_temp_flags=flags))
  for peer in (2026102706,2026102708):
   assert h.sd_live_status(dict(mc_fw_build=peer,mc_age_ms=20,bp_temp_flags=flags))==expected;checks+=1
 for peer in (2026102706,2026102708):
  z=h.break_wire_status(dict(bp_fw_build=peer,bp_age_ms=20,mc_break0_hex='00'*92,mc_break0_age_ms=100,mc_break1_hex='00'*92,mc_break1_age_ms=100))
  assert all(x['available'] and not x['captured'] for x in z['mc_break_snapshots']);checks+=1
 for r in drivers[:2]:
  d=dict(mc_fw_build=p.NEW[1],enc_fault_first_hex=r['parent'],enc_fault_decode_valid=1,enc_bus_clear_hex=r['record'])
  out=h.with_bus_clear(d);assert out['enc_bus_clear_decode_valid']==1 and out['enc_bus_clear_record'];checks+=1
  b=bytes.fromhex(r['record'])
  for n in range(43):
   bad=bytearray(b);bad[n]^=1;x=h.with_bus_clear(dict(d,enc_bus_clear_hex=bad.hex()));assert x['enc_bus_clear_decode_valid']==0;checks+=1
  for overrides in (dict(mc_fw_build=p.OLD[1]),dict(enc_fault_first_hex='00'*160),dict(enc_fault_decode_valid=0)):
   assert h.with_bus_clear(dict(d,**overrides))['enc_bus_clear_decode_valid']==0;checks+=1
 # Replay captured current fault exactly: PE0, ISR.TXE only, SDA LOW at boot.
 cap=json.loads(p.read(p.BASE/'install_20261027_r1/idle_first_capture.json'))
 parent=cap['first_records'][0];assert parent['cause']=='BUSY' and not parent['pwm_moe'] and parent['cr1']==0x200 and parent['decision_isr']==1 and parent['scl'] and not parent['sda'] and parent['cleanup_no_transfer']
 assert (c/'nucleo/Inc/encoder_core.h').read_bytes()==(p.BASE/'nucleo/Inc/encoder_core.h').read_bytes()
 # Existing core regression remains exactly unchanged (new peer fixture only).
 fixture=v/'record_fixture.h';src=p.BASE.parent/'nucleo_i2c_stop_recovery_r1/verification/record_fixture.h';p.write(fixture,p.read(src).replace('2026102704','2026102708'))
 exe=v/'old_core_regression.exe';run('old_core_compile',includes+['-I',str(v),str(p.ROOT/'tools/nucleo_i2c_stop/selftest.cpp'),'-o',str(exe)]);regression=json.loads(run('old_core_regression',[str(exe)]));assert regression['passed']
 for rel,digest in json.loads(p.read(c/'manifest.json'))['historical_records_preserved'].items():assert p.sha(c/'preserved_records'/rel)==digest
 for name in ('nucleo','UNOQ_MOTOR','libraries'):
  allow={'nucleo':{'Src/nucleo_encoder.c','Src/main.c','Inc/nucleo_encoder.h'},'UNOQ_MOTOR':{'UNOQ_MOTOR.ino'},'libraries':set()}[name]
  for f in (p.BASE/name).rglob('*'):
   rel=f.relative_to(p.BASE/name)
   if not f.is_file() or any(x in ('Debug','Release','__pycache__','.settings') for x in rel.parts) or str(rel).replace('\\','/') in allow:continue
   g=c/name/rel
   if f.read_bytes()!=g.read_bytes():assert p.read(g).replace(str(p.NEW[0]),str(p.OLD[0])).replace(str(p.NEW[1]),str(p.OLD[1]))==p.read(f),str(rel)
 def norm(s):return s.replace(str(p.NEW[0]),str(p.OLD[0])).replace(str(p.NEW[1]),str(p.OLD[1]))
 s=norm(p.read(c/'nucleo/Src/nucleo_encoder.c')).replace(p.read(p.RES/'platform.inc')+'\n','').replace('\n  if(bus_clear_service())return;','')
 assert s==p.read(p.BASE/'nucleo/Src/nucleo_encoder.c'),'Unexpected driver change'
 s=norm(p.read(c/'nucleo/Src/main.c')).replace(p.read(p.RES/'sender.inc')+'\n','').replace('\n    mic_send_bus_clear(HAL_GetTick());','')
 gate='    mic_encoder_allow_bus_clear(!uno_link.command_enabled && mic_break_start_window==0U &&\n      !LL_TIM_IsEnabledAllOutputs(TIM1) &&\n      (MC_GetSTMStateMotor1()==IDLE || MC_GetSTMStateMotor1()==FAULT_NOW || MC_GetSTMStateMotor1()==FAULT_OVER) &&\n      VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super)<20U);\n'
 s=s.replace(gate,'');assert s==p.read(p.BASE/'nucleo/Src/main.c'),'Motor/protection/main change'
 s=norm(p.read(c/'UNOQ_MOTOR/UNOQ_MOTOR.ino')).replace('\n#include "bus_clear_wire.h"\nstatic uint8_t g_bus_clear[UV3_FRAME];static bool g_bus_clear_seen;','').replace(p.read(p.RES/'uno_rx.inc')+'\n','').replace(p.read(p.RES/'uno_text.inc')+'\n','')
 assert s==p.read(p.BASE/'UNOQ_MOTOR/UNOQ_MOTOR.ino'),'Uno control changed'
 s=p.read(c/'web_hmi/static/app.js').replace('      if (data.enc_bus_clear_record) text += `; ${data.enc_bus_clear_record.summary_ru}`;\n','');assert s==p.read(p.BASE/'web_hmi/static/app.js')
 r=dict(passed=True,hardware_commands=0,core=core,production_driver=drivers,hmi_checks=checks,original_core_regression=regression,recorded_sda_low_preflight_replayed=True,original_core_unchanged=True,protected_sources_unchanged=True,historical_records_preserved=True)
 p.write(v/'native_report.json',json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='production_driver'}))
if __name__=='__main__':main()
