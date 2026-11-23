"""Actual native C/profile and unchanged protection contracts, no hardware."""
import ast,importlib.util,subprocess,shutil,json,unittest
import prepare_standstill_timing as p
from audit_production_pwm_filters import function
class Timing(unittest.TestCase):
 def test_native_first_step_prepared_off_and_profile_gate(self):
  t=ast.parse(p.read(p.ROOT/'tools/test_standstill_commissioning.py'))
  m=next(n for n in ast.walk(t) if isinstance(n,ast.FunctionDef) and n.name=='test_actual_native_driver_capture_and_uart')
  checks=ast.literal_eval(next(n for n in m.body if isinstance(n,ast.Assign) and any(isinstance(v,ast.Name) and v.id=='checks' for v in n.targets)).value)
  t=ast.parse(p.read(p.ROOT/'tools/test_multi_algorithm.py'))
  m=next(n for n in ast.walk(t) if isinstance(n,ast.FunctionDef) and n.name=='test_native_adapter_and_wire_actual_c')
  pre=ast.literal_eval(next(n for n in m.body if isinstance(n,ast.Assign) and any(isinstance(v,ast.Name) and v.id=='pre' for v in n.targets)).value)
  pre=pre.replace('return 320;','return fake_bus;').replace('static uint16_t VBS_GetAvBusVoltage_V','static uint16_t fake_bus=0;\nstatic uint16_t VBS_GetAvBusVoltage_V')
  pre+='''
#include "identify_core.h"
#include "identify_wire.h"
static int PWM_ParamsM1,off_calls;
static void PWM_SwitchOffPWM(int*){timer.BDTR=0;++off_calls;}
static uint32_t profile_ticks;static uint32_t profile_clock(){return profile_ticks+=100;}
'''
  source=p.read(p.OUT/'nucleo/Src/multi_native.c')
  profile=function(source,'mi_native_profile_off');source=source.replace(profile,profile.replace('DWT->CYCCNT','profile_clock()'))
  source='\n'.join(line for line in source.splitlines() if not line.startswith(('#include','#pragma')))
  checks=checks.replace('2026102932','2026102934')
  checks=checks.replace(' mi_config cfg=',r'''
 assert(id_profile_cycles==0&&!ma_native_request(4));
 sample.zero=1;mi_native_profile_off();
 assert(id_profile_attempted&&id_profile_cycles==100&&!id_state.active&&!id_state.ready&&!id_state.accepted);
 sample.zero=0;
 mi_config cfg=''')
  checks=checks.replace('assert(ma_native_request(4));',r'''
 uint32_t measured=id_profile_cycles;id_profile_cycles=4801;assert(!ma_native_request(4));id_profile_cycles=measured;
 assert(ma_native_request(4));''')
  checks=checks.replace('sample.zero=1;assert(ma_native_prepare());','sample.zero=1;assert(ma_native_prepare());assert(id_prepared&&!id_state.active);')
  out=p.OUT/'verification';out.mkdir(exist_ok=True);unit=out/'native_timing.cpp';p.write(unit,pre+source+checks)
  exe=unit.with_suffix('.exe');r=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
   '-I',str(p.OUT/'nucleo/Inc'),'-I',str(p.OUT/'UNOQ_MOTOR'),str(unit),'-o',str(exe)],capture_output=True,text=True)
  p.write(out/'native_compile.log',r.stdout+r.stderr);r.check_returncode();subprocess.run([str(exe)],check=True)
 def test_existing_protections_unchanged(self):
  for folder in ('nucleo/Inc','nucleo/Src'):
   for name in (('drive_parameters.h','power_stage_parameters.h','current_core.h','current_adc_window_plan.h','current_adc_deadline.h') if folder.endswith('Inc') else ('main.c','current_shunt.c','stm32g4xx_mc_it.c','stm32g4xx_hal_msp.c')):
    self.assertEqual(p.read(p.BASE/folder/name).replace('2026102932','2026102934'),p.read(p.OUT/folder/name),name)
  old=p.read(p.BASE/'nucleo/Src/multi_native.c');new=p.read(p.OUT/'nucleo/Src/multi_native.c')
  fast=function(new,'mi_native_fast')
  self.assertNotIn('mi_begin(',fast);self.assertLess(fast.index('elapsed>SystemCoreClock/16000U/2U'),fast.index('TIM1->CCR1=out.ccr'))
  profile=function(new,'mi_native_profile_off')
  for forbidden in ('CCR1=','CCR2=','CCR3=','EnableAllOutputs','DisableIRQ','__disable_irq','AcknowledgeFault','MC_StartMotor'):
   self.assertNotIn(forbidden,profile)
  for name in ('MX_TIM1_Init','MX_ADC1_Init','MX_ADC2_Init','uno_clear_frame_is_safe','uno_latch_fault','uno_update_softstart_state'):
   self.assertEqual(function(p.read(p.BASE/'nucleo/Src/main.c'),name),function(p.read(p.OUT/'nucleo/Src/main.c'),name),name)
 def test_hmi_existing_start_stop_guards_identical(self):
  def methods(folder):
   s=p.read(folder/'web_hmi/server.py').replace('2026102931','2026102933').replace('2026102932','2026102934')
   t=ast.parse(s);c=next(n for n in t.body if isinstance(n,ast.ClassDef) and n.name=='AppState')
   return {n.name:ast.dump(n,include_attributes=False) for n in c.body if isinstance(n,ast.FunctionDef)}
  a,b=methods(p.BASE),methods(p.OUT)
  for name in ('start_sequence','stop_sequence','_start_without_precharge','operator_heartbeat_fresh'):self.assertEqual(a[name],b[name],name)
if __name__=='__main__':unittest.main()
