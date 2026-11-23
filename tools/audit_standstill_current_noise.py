"""Prove unchanged protections and isolate the new current-publication/idle ADC code."""
import ast
import hashlib
import json
import prepare_standstill_current_noise as p
from audit_production_pwm_filters import function

def main():
 a,b=p.BASE/'nucleo',p.OUT/'nucleo'
 unchanged=[]
 for rel in ['Inc/drive_parameters.h','Inc/power_stage_parameters.h','Inc/identify_core.h',
  'Inc/current_adc_window_plan.h','Inc/current_adc_deadline.h','Inc/peak_core.h',
  'Src/multi_native.c','Src/stm32g4xx_mc_it.c','Src/stm32g4xx_hal_msp.c','Src/regular_conversion_manager.c']:
  old=p.read(a/rel).replace('2026102938','2026102940')
  assert old==p.read(b/rel),rel
  unchanged.append(rel)
 # No changes to ADC clocks, sampling times, active aperture, power PWM, or CLEAR.
 old,new=p.read(a/'Src/main.c'),p.read(b/'Src/main.c')
 functions=['MX_TIM1_Init','MX_ADC1_Init','MX_ADC2_Init','SystemClock_Config',
  'uno_clear_frame_is_safe','uno_latch_fault','uno_update_softstart_state']
 for name in functions:assert function(old,name)==function(new,name),name
 old=p.read(a/'Src/current_shunt.c');new=p.read(b/'Src/current_shunt.c')
 for name in ['mic_current_packet','mic_current_peak_packet','mic_zero_packet','mic_current_update_epoch']:
  assert function(old,name)==function(new,name),name
 assert 'CM_ACQUIRE_TICKS=112U' in new and 'CM_BEFORE_TOP=128U' in new
 assert 's->offset[cm_path1(pair)]' in p.read(b/'Inc/current_core.h')
 # Check the full original monitor/calibration functions, ignoring only the new helper.
 core_old=p.read(a/'Inc/current_core.h');core_new=p.read(b/'Inc/current_core.h')
 helper=function(core_new,'cm_reconstruct')
 assert core_new.replace('\n/* Instantaneous feedback is independent of RMS window rollover/publication. */\nstatic inline '+helper,'')==core_old
 def methods(folder):
  t=ast.parse(p.read(folder/'web_hmi/server.py'))
  c=next(n for n in t.body if isinstance(n,ast.ClassDef) and n.name=='AppState')
  return {n.name:ast.dump(n,include_attributes=False) for n in c.body if isinstance(n,ast.FunctionDef)}
 h0,h1=methods(p.BASE),methods(p.OUT)
 for name in ['start_sequence','stop_sequence','_start_without_precharge','operator_heartbeat_fresh']:
  assert h0[name]==h1[name],name
 assert (p.BASE/'libraries/Arduino_RouterBridge/src/bridge.h').read_bytes()==(p.OUT/'libraries/Arduino_RouterBridge/src/bridge.h').read_bytes()
 for f in ('noise_core.h','noise_wire.h'):
  text=p.read(b/'Inc'/f)
  for forbidden in ['CCR1=','CCR2=','CCR3=','MC_StartMotor','AcknowledgeFault','__disable_irq','EnableAllOutputs']:
   assert forbidden not in text
 evidence={}
 for folder in ['first_dc_point_r1','powered_preflight_r1','off_after_current_abort_r1']:
  for f in (p.BASE/folder).rglob('*'):
   if f.is_file():evidence[str(f.relative_to(p.ROOT))]=hashlib.sha256(f.read_bytes()).hexdigest()
 out=p.OUT/'verification';out.mkdir(exist_ok=True)
 p.write(out/'preserved_latest_evidence.json',json.dumps(evidence,indent=2))
 report=dict(passed=True,hardware_commands=0,unchanged_files=unchanged,unchanged_main_functions=functions,
  calibration_and_raw_guards_unchanged=True,active_adc_clock_and_sampling_unchanged=True,
  no_filter_in_raw_protection=True,latest_preserved_evidence_files=len(evidence),
  current_noise_cause_identified=False,physical_noise_reduction_verified=False)
 p.write(out/'protection_audit.json',json.dumps(report,indent=2));print(json.dumps(report))

if __name__=='__main__':main()
