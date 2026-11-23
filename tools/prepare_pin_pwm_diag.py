"""Minimal AS5600/TIM1 isolated fixture. No motor application is initialized."""
import json,os,shutil
from pathlib import Path
import prepare_no_switch_diag as p
from audit_production_pwm_filters import function
OLD=p.ROOT/'artifacts/live_bench_20261027/no_switch_diag_r3'
OUT=OLD.with_name('pin_pwm_diag_r1');BUILD=2026102794
def main():
 OUT.mkdir(exist_ok=False)
 old=json.loads(p.read(OLD/'manifest.json'))
 for rel,h in old['sealed_sha256'].items():assert p.sha(OLD/rel)==h,rel
 def copy(src,dst):
  rel=Path(src).relative_to(OLD/'nucleo')
  if rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dst);return dst
  return shutil.copy2(src,dst)
 shutil.copytree(OLD/'nucleo',OUT/'nucleo',copy_function=copy,ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
 for name,tree in [('pin_pwm_diag.c','Src'),('pin_pwm_diag.h','Inc')]:shutil.copy2(p.ROOT/'tools'/name,OUT/'nucleo'/tree/name)
 f=OUT/'nucleo/STM32CubeIDE/.project';s=p.read(f)
 s=p.once(s,'\t<linkedResources>','\t<linkedResources>\n\t\t<link>\n\t\t\t<name>Application/User/pin_pwm_diag.c</name>\n\t\t\t<type>1</type>\n\t\t\t<locationURI>PARENT-1-PROJECT_LOC/Src/pin_pwm_diag.c</locationURI>\n\t\t</link>');p.write(f,s)
 f=OUT/'nucleo/Src/main.c';s=p.read(f).replace('2026102792',str(BUILD))
 s=p.once(s,'int main(void)','static void unused_motor_main(void) __attribute__((unused));\nstatic void unused_motor_main(void)')
 anchor='/**\n  * @brief System Clock Configuration'
 main='''#include "pin_pwm_diag.h"
extern void mc_lock_pins(void);
int main(void){
 HAL_Init();SystemClock_Config();MX_GPIO_Init();MX_TIM1_Init();
 /* Dedicated isolated fixture: no MCSDK motor boot, ADC, UART or DMA start. */
 mic_encoder_init();mic_encoder_allow_bus_clear(false);mc_lock_pins();
 HAL_NVIC_SetPriority(TIM1_UP_TIM16_IRQn,0,0);HAL_NVIC_EnableIRQ(TIM1_UP_TIM16_IRQn);
 HAL_NVIC_SetPriority(TIM1_BRK_TIM15_IRQn,4,1);HAL_NVIC_EnableIRQ(TIM1_BRK_TIM15_IRQn);
 HAL_NVIC_SetPriority(EXTI15_10_IRQn,3,0);HAL_NVIC_EnableIRQ(EXTI15_10_IRQn);
 mic_pin_init();
 while(1){mic_pin_poll();mic_encoder_poll();}
}

'''
 s=p.once(s,anchor,main+anchor);p.write(f,s)
 f=OUT/'nucleo/Src/stm32g4xx_mc_it.c';s=p.read(f)
 s='#include "pin_pwm_diag.h"\n'+s
 for name,body in [('TIMx_UP_M1_IRQHandler','mic_pin_irq();'),('TIMx_BRK_M1_IRQHandler','mic_pin_break();'),('SysTick_Handler','HAL_IncTick();'),('HardFault_Handler','LL_TIM_DisableAllOutputs(TIM1);for(;;){}')]:
  original=function(s,name);s=p.once(s,original,'void '+name+'(void)\n{\n '+body+'\n}')
 p.write(f,s)
 # Core AS5600 platform, cleanup, timing/filter and first-fault capture are EXACT copies.
 for rel in ('Src/nucleo_encoder.c','Inc/encoder_core.h','Inc/cleanup_flags.h','Inc/bus_clear.h'):
  assert (OLD/'nucleo'/rel).read_bytes()==(OUT/'nucleo'/rel).read_bytes(),rel
 for tree in ('build/nucleo','verification','restore','preserved_records'):(OUT/tree).mkdir(parents=True,exist_ok=True)
 shutil.copytree(OLD/'preserved_records',OUT/'preserved_records/earlier',copy_function=os.link)
 for tree in ('compute5s_r1','install_usb_r1'):shutil.copytree(OLD/tree,OUT/'preserved_records/2792'/tree,copy_function=os.link)
 shutil.copytree(OLD.with_name('as5600_installed2792_idle60_r1'),OUT/'preserved_records/idle60',copy_function=os.link)
 for f in (OLD/'build/nucleo').iterdir():
  if f.is_file():shutil.copy2(f,OUT/'restore'/f.name)
 m=dict(schema='mic_ai.isolated_pin_pwm_as5600.v1',build=BUILD,built=False,installed=False,hardware_tested=False,
  physical_scope='34pin inverter cable disconnected; J1/J4 OFF; motor application not initialized',
  initialized='HAL/SystemClock/GPIO/originalTIM1/unchangedAS5600',ADC_enabled=False,UART_enabled=False,motor_commands_possible=False,
  original_TIM1_BKIN_deadtime_unchanged=True,production_sources_and_thresholds_unchanged=True,
  stages_ms=[1000,2000,2000],one_request_per_boot=True,auto_stop_ms=5000,
  archived={f.relative_to(OUT/'preserved_records').as_posix():p.sha(f) for f in (OUT/'preserved_records').rglob('*') if f.is_file()},
  limitations=['Minimal isolated logic test, not the complete motor firmware','No powered inverter or rotating motor','Saleae digital thresholds cannot establish analog signal integrity'])
 p.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(dict(prepared=True,build=BUILD,hardware_calls=0)))
if __name__=='__main__':main()
