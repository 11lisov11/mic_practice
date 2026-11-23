"""Create a Nucleo-only computation diagnostic; never flash or start hardware."""
import hashlib,json,os,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261027/i2c_persistent_pe_r1'
OUT=ROOT/'artifacts/live_bench_20261027/no_switch_diag_r1'
RES=ROOT/'tools/no_switch_diag'
BUILD=2026102790
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return p.read_text(encoding='utf-8-sig')
def write(p,s):
 p.parent.mkdir(parents=True,exist_ok=True)
 # Atomic replacement breaks hard links; never overwrite an archived inode.
 t=p.with_name(p.name+'.diag-tmp');t.write_text(s,encoding='utf-8');os.replace(t,p)
def once(s,a,b):
 assert s.count(a)==1,a[:100]
 return s.replace(a,b)
def identity(s):return s.replace('2026102710','2026102790')
def main():
 assert (OUT/'preserved_live/status.json').exists()
 assert not (OUT/'nucleo').exists()
 m=json.loads(read(BASE/'manifest.json'));assert m['built'] and m['readback_verified_both']
 for table in ('source_sha256','build_sha256','verification_sha256'):
  for rel,d in m[table].items():assert sha(BASE/rel)==d,rel
 for rel,d in m['historical_records_preserved'].items():assert sha(BASE/'preserved_records'/rel)==d
 def copier(src,dst):
  rel=Path(src).relative_to(BASE/'nucleo')
  if rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dst);return dst
  return shutil.copy2(src,dst)
 shutil.copytree(BASE/'nucleo',OUT/'nucleo',copy_function=copier,ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
 for folder in ('Inc','Src'):
  for f in (OUT/'nucleo'/folder).iterdir():
   if f.is_file():
    a=read(f);b=identity(a)
    if a!=b:write(f,b)
 for name in ('load_diag.h','load_core.h'):shutil.copy2(RES/name,OUT/'nucleo/Inc'/name)
 shutil.copy2(RES/'load_diag.c',OUT/'nucleo/Src/load_diag.c')
 f=OUT/'nucleo/STM32CubeIDE/.project';s=read(f)
 s=once(s,'\t<linkedResources>','\t<linkedResources>\n\t\t<link>\n\t\t\t<name>Application/User/load_diag.c</name>\n\t\t\t<type>1</type>\n\t\t\t<locationURI>PARENT-1-PROJECT_LOC/Src/load_diag.c</locationURI>\n\t\t</link>')
 write(f,s)
 f=OUT/'nucleo/Src/main.c';s=read(f)
 s=once(s,'#include "local_stop.h"','#include "local_stop.h"\n#include "load_diag.h"')
 s=once(s,'else LL_TIM_EnableAllOutputs(timer);','else LL_TIM_DisableAllOutputs(timer); /* Diagnostic image: never enable phase outputs. */')
 s=once(s,'  if (uno_clear_frame_is_safe(frame)) {','  /* Diagnostic image cannot accept any motor ENABLE request. */\n  if ((flags & UNO_FLAG_ENABLE) != 0U) { uno_stop_motor(); return; }\n\n  if (uno_clear_frame_is_safe(frame)) {')
 s=once(s,'  /* Infinite loop */','  mic_load_init();\n\n  /* Infinite loop */')
 s=once(s,'    mic_encoder_allow_bus_clear(!uno_link.command_enabled','    mic_load_poll();\n    mic_encoder_allow_bus_clear(!mic_load_active() && !uno_link.command_enabled')
 write(f,s)
 f=OUT/'nucleo/Src/mc_tasks.c';s=read(f)
 s=once(s,'#include "mc_tasks.h"','#include "mc_tasks.h"\n#include "load_diag.h"')
 s=once(s,'__weak void TSK_MediumFrequencyTaskM1(void)\n{','__weak void TSK_MediumFrequencyTaskM1(void)\n{\n  mic_load_medium_update();')
 s=once(s,'  if (0U == LL_TIM_IsEnabledAllOutputs(pwmHandle[M1]->TIMx))\n  {\n    return bMotorNbr;','  if (0U == LL_TIM_IsEnabledAllOutputs(pwmHandle[M1]->TIMx))\n  {\n    mic_load_tim_update();\n    return bMotorNbr;')
 write(f,s)
 f=OUT/'nucleo/MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLibACIM/Any/Src/pwm.c';s=read(f)
 s=once(s,'#include "local_stop.h"','#include "local_stop.h"\n#include "load_diag.h"')
 s=once(s,'  LL_TIM_DisableIT_UPDATE(pHandle->TIMx);','  LL_TIM_DisableIT_UPDATE(pHandle->TIMx);\n  /* Keep computation IRQ only. Actual phase outputs remain disabled. */\n  if (mic_load_active()) LL_TIM_EnableIT_UPDATE(pHandle->TIMx);')
 write(f,s)
 f=OUT/'nucleo/Src/current_shunt.c';s=read(f)
 s=once(s,'#include "current_shunt.h"','#include "current_shunt.h"\n#include "load_diag.h"')
 s=once(s,'  /* Bind the completed sample to one update epoch','  mic_load_adc_enter(DWT->CYCCNT);\n  /* Bind the completed sample to one update epoch')
 s=once(s,'  uint8_t active=(uint8_t)(LL_TIM_IsEnabledAllOutputs(TIM1)!=0);','  /* Computational active path only: actual BDTR/MOE is never forged. */\n  uint8_t active=(uint8_t)(mic_load_active() || LL_TIM_IsEnabledAllOutputs(TIM1)!=0);')
 s=once(s,'    pc_push(&peak,&sample,HAL_GetTick(),active,raw_eligible,mag);\n  }\n}',
  '    pc_push(&peak,&sample,HAL_GetTick(),active,raw_eligible,mag);\n  }\n  mic_load_adc_exit(DWT->CYCCNT,eligible && a>=16 && b>=16 && a<=4079 && b<=4079);\n}\n\nuint32_t mic_current_load_quality(void) {\n return (state.zero_ready?1U:0U)|(state.zero_bad?2U:0U)|(lost_sync?4U:0U);\n}')
 s=once(s,'  packet[3]=flags;packet[38]=1;uv3_seal(packet);','  /* These zero-bus diagnostic numbers are never qualified motor amps. */\n  flags&=(uint8_t)~CM_VALID;\n  packet[3]=flags;packet[38]=1;uv3_seal(packet);')
 write(f,s)
 f=OUT/'nucleo/Src/nucleo_encoder.c';s=read(f)
 s+='''
/* Read-only export for the ST-LINK diagnostic report; no state reset. */
void mic_encoder_load_snapshot(uint32_t *v){
 v[0]=enc.reads;v[1]=enc.errors;v[2]=enc.primary_nack;v[3]=enc.timeouts;
 v[4]=enc.primary_busy;v[5]=enc.primary_arlo;v[6]=enc.berr_clears;
 v[7]=enc.forced_resets;v[8]=enc.parks;v[9]=enc.raw;v[10]=enc.status;
 v[11]=(enc.bus_ok?1U:0U)|(enc.angle_ok?2U:0U)|(enc.speed_ok?4U:0U);
 v[12]=I2C1->ISR;v[13]=I2C1->CR1;v[14]=GPIOB->IDR;
 v[15]=enc.sample_ms;v[16]=fault_ready;
}
'''
 write(f,s)
 for folder in ('build/nucleo','verification','preserved_records','restore'):(OUT/folder).mkdir(parents=True,exist_ok=True)
 # A retained immutable archive; new test files are separate and never overwrite it.
 for rel,d in m['historical_records_preserved'].items():
  dst=OUT/'preserved_records'/rel;dst.parent.mkdir(parents=True,exist_ok=True);os.link(BASE/'preserved_records'/rel,dst);assert sha(dst)==d
 for folder in ('powered_as5600_5hz_r1','powered_as5600_5hz_repeat_r1','idle_after_pwm_repeat_r1'):
  for src in (BASE/folder).iterdir():
   if src.is_file():
    dst=OUT/'preserved_records'/folder/src.name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst);assert sha(dst)==sha(src)
 stem='ACIM-NUCLEOG431RB-IPM15B-VF_OL'
 for ext in ('.hex','.bin','.elf','.build-manifest.json'):
  shutil.copy2(BASE/'build/nucleo'/(stem+ext),OUT/'restore'/(stem+ext))
 result=dict(schema='mic_ai.no_switch_compute_diag.v1',diagnostic_build=BUILD,production_restore_build=2026102710,
  built=False,installed=False,hardware_tested=False,only_nucleo_update=True,uno_update_required=False,
  main_output_enable_forbidden=True,phase_pins_forced_gpio_low=True,motor_enable_commands_rejected=True,
  protection_thresholds_unchanged=True,MC_UNDER_VOLT_not_masked=True,real_vbus_unchanged=True,
  VF_replay_normalization_v=327,sensor_feedback=False,AS5600_core_unchanged=True,
  run_limit_ms=5000,request_once_per_boot=True,no_auto_start=True,readout='ST-LINK SRAM with CRC32C and sequence validation',
  limitations=['Computation/ADC exercise with MOE=0, not physical PWM at phase pins','Zero-bus ADC samples are not motor currents','RMS processing branch coverage requires valid zero and ADC samples on target','Diagnostic image is intentionally not a normal HMI-compatible motor-control peer'],
  preserved_records={str(f.relative_to(OUT/'preserved_records')).replace('\\','/'):sha(f) for f in (OUT/'preserved_records').rglob('*') if f.is_file()},
  predecessor_manifest_sha256=sha(BASE/'manifest.json'))
 write(OUT/'manifest.json',json.dumps(result,indent=2)+'\n')
 print(json.dumps(dict(prepared=True,build=BUILD,archived_files=len(result['preserved_records']),hardware_commands=0)))
if __name__=='__main__':main()
