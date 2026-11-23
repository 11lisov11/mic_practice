"""Full protected MCSDK application plus a bounded computation/I2C observation."""
import json, os, shutil
from pathlib import Path
import prepare_no_switch_diag as p
from audit_production_pwm_filters import function

OLD=p.ROOT/'artifacts/live_bench_20261028/combined_io_diag_r2'
REFERENCE=p.ROOT/'artifacts/live_bench_20261027/no_switch_diag_r3'
OUT=p.ROOT/'artifacts/live_bench_20261028/full_mcsdk_diag_r1'
BUILD=2026102803

def main():
 OUT.mkdir(parents=True,exist_ok=False)
 old=json.loads(p.read(OLD/'manifest.json'))
 for rel,h in old['sealed_sha256'].items(): assert p.sha(OLD/rel)==h,rel
 def copy(src,dst):
  rel=Path(src).relative_to(OLD/'nucleo')
  if rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dst);return dst
  return shutil.copy2(src,dst)
 shutil.copytree(OLD/'nucleo',OUT/'nucleo',copy_function=copy,ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
 for tree in ('build/nucleo','verification','test_resources','preserved_records','restore'):(OUT/tree).mkdir(parents=True,exist_ok=True)
 shutil.copytree(OLD/'preserved_records',OUT/'preserved_records/earlier',copy_function=os.link)
 for tree in ('run_r1','build/nucleo','install_r1'):
  shutil.copytree(OLD/tree,OUT/'preserved_records/2802'/tree,copy_function=os.link)
 for name in ('assessment.json','runtime_sha256.json','manifest.json'):
  shutil.copy2(OLD/name,OUT/'preserved_records/2802'/name)
 for f in (OLD/'restore').iterdir():shutil.copy2(f,OUT/'restore'/f.name)
 for tree in ('Src','Inc'):
  for f in (OUT/'nucleo'/tree).iterdir():
   if f.is_file():
    a=p.read(f);b=a.replace('2026102802',str(BUILD)).replace('2026102792',str(BUILD))
    if a!=b:p.write(f,b)
 # Restore the actual MCSDK boot/foreground and original interrupt routing.
 f=OUT/'nucleo/Src/main.c';s=p.read(f)
 start=s.index('static void unused_motor_main(void) __attribute__((unused));')
 end=s.index('/**\n  * @brief System Clock Configuration',start)
 ref=p.read(REFERENCE/'nucleo/Src/main.c')
 main=function(ref,'main')
 main=p.once(main,'    mic_load_poll();','    mic_load_poll();\n    mic_full_publish();')
 main=p.once(main,'  mic_load_init();','  mic_load_init();\n  mic_full_init();')
 s=s[:start]+'#include "full_mcsdk_runtime.inc"\n\n'+main+'\n\n'+s[end:]
 s=p.once(s,'#include "load_diag.h"','#include "load_diag.h"\n#include "full_mcsdk_diag.h"')
 # The complete native handler checks its original faults and bus gates first.
 # A separate, additional fixture inhibit forbids any successful motor START.
 s=p.once(s,'  /* Diagnostic image cannot accept any motor ENABLE request. */\n  if ((flags & UNO_FLAG_ENABLE) != 0U) { uno_stop_motor(); return; }\n','')
 s=p.once(s,'static void uno_handle_valid_frame(const uint8_t *frame) {','static void uno_handle_valid_frame(const uint8_t *frame) {\n  mic_full_command(frame[3],frame[4]);')
 s=p.once(s,'  const MCI_State_t start_state = MC_GetSTMStateMotor1();','  /* Extra fixture inhibit, after unchanged native validation; never authorize START. */\n  ++mic_full_fixture_denials;uno_stop_motor();return;\n  const MCI_State_t start_state = MC_GetSTMStateMotor1();')
 # Uncalled predecessor helper remains available to unused diagnostic objects.
 s=s.replace('static void mic_combined_uart_poll(void)','static void __attribute__((unused)) mic_combined_uart_poll(void)')
 p.write(f,s)
 for name in ('full_mcsdk_diag.h','full_mcsdk_runtime.inc'):
  shutil.copy2(p.ROOT/'tools'/name,OUT/'nucleo'/('Inc' if name.endswith('.h') else 'Src')/name)
 f=OUT/'nucleo/Src/stm32g4xx_mc_it.c';p.write(f,p.read(REFERENCE/'nucleo/Src/stm32g4xx_mc_it.c'))
 f=OUT/'nucleo/Src/mc_tasks.c';s=p.read(f)
 s='#include "full_mcsdk_diag.h"\n'+s
 for name,index in [('MC_RunMotorControlTasks',0),('TSK_SafetyTask',1),('TSK_MediumFrequencyTaskM1',2),('TSK_HighFrequencyTask',3)]:
  body=function(s,name);pos=body.index('{')+1
  s=p.once(s,body,body[:pos]+f'\n  mic_full_task({index});'+body[pos:])
 p.write(f,s)
 f=OUT/'nucleo/Src/load_diag.c';s=p.read(f)
 s=p.once(s,'#include "load_diag.h"','#include "load_diag.h"\n#include "full_mcsdk_diag.h"')
 s=p.once(s,'  return bad;','  return bad|mic_full_guard();')
 p.write(f,s)
 for name in ('core_test.cpp','platform_test.cpp'):shutil.copy2(REFERENCE/'test_resources'/name,OUT/'test_resources'/name)
 for name in ('load_diag.h','load_core.h'):shutil.copy2(OUT/'nucleo/Inc'/name,OUT/'test_resources'/name)
 shutil.copy2(OUT/'nucleo/Src/load_diag.c',OUT/'test_resources/load_diag.c')
 f=OUT/'test_resources/platform_test.cpp';s=p.read(f)
 s=p.once(s,'#include "load_diag.h"','static uint32_t full_bad;\nuint32_t mic_full_guard(){return full_bad;}\n#include "load_diag.h"')
 s=p.once(s,'int main(){','int main(){\n reset();full_bad=256;test(guard()&256);full_bad=0;\n')
 p.write(f,s)
 shutil.copy2(OUT/'nucleo/Inc/full_mcsdk_diag.h',OUT/'test_resources/full_mcsdk_diag.h')
 m=dict(schema='mic_ai.full_mcsdk_isolated.v1',build=BUILD,built=False,installed=False,hardware_tested=False,
  full_MCSDK_boot_scheduler_safety=True,UART_native_command_dispatch=True,
  actual_UV_and_temperature_faults_preserved=True,actual_bus_never_forged=True,
  extra_fixture_START_inhibit=True,GPIO_locked_LOW=True,MOE_always_zero=True,
  test_duration_ms=5000,AS5600_driver_unchanged=True,previous_physical_PWM_capture_preserved=True,
  limitation='Full protected OFF/FAULT application and private VF/ADC workload; no motor RUN or physical PWM edges with zero bus',
  archived={f.relative_to(OUT/'preserved_records').as_posix():p.sha(f) for f in (OUT/'preserved_records').rglob('*') if f.is_file()})
 p.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
 print(json.dumps(dict(prepared=True,build=BUILD,archived=len(m['archived']))))
if __name__=='__main__':main()
