"""Real ADC injected IRQs + unchanged UART ISR/DMA, AS5600 and isolated TIM1."""
import json,os,shutil
from pathlib import Path
import prepare_no_switch_diag as p
from audit_production_pwm_filters import function
OLD=p.ROOT/'artifacts/live_bench_20261027/pin_pwm_diag_r2'
OUT=p.ROOT/'artifacts/live_bench_20261028/combined_io_diag_r1';BUILD=2026102801
def configure():
 import prepare_pin_pwm_diag as base
 base.OUT=OUT;base.BUILD=BUILD
def main():
 OUT.mkdir(parents=True,exist_ok=False)
 m=json.loads(p.read(OLD/'manifest.json'))
 for rel,h in m['sealed_sha256'].items():assert p.sha(OLD/rel)==h,rel
 def copy(src,dst):
  rel=Path(src).relative_to(OLD/'nucleo')
  if rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dst);return dst
  return shutil.copy2(src,dst)
 shutil.copytree(OLD/'nucleo',OUT/'nucleo',copy_function=copy,ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
 for name,tree in [('combined_io_diag.c','Src'),('combined_io_diag.h','Inc')]:shutil.copy2(p.ROOT/'tools'/name,OUT/'nucleo'/tree/name)
 f=OUT/'nucleo/STM32CubeIDE/.project';s=p.read(f)
 s=p.once(s,'\t<linkedResources>','\t<linkedResources>\n\t\t<link>\n\t\t\t<name>Application/User/combined_io_diag.c</name>\n\t\t\t<type>1</type>\n\t\t\t<locationURI>PARENT-1-PROJECT_LOC/Src/combined_io_diag.c</locationURI>\n\t\t</link>');p.write(f,s)
 f=OUT/'nucleo/Src/main.c';s=p.read(f).replace('2026102795',str(BUILD))
 old_main=function(s,'main')
 new_main='''int main(void){
 HAL_Init();SystemClock_Config();MX_GPIO_Init();MX_ADC1_Init();MX_ADC2_Init();MX_TIM1_Init();
 /* Real ADCs, externalTIM1 trigger, identical acquisition timing and IRQ body. */
 if(HAL_ADCEx_Calibration_Start(&hadc1,ADC_SINGLE_ENDED)!=HAL_OK ||
    HAL_ADCEx_Calibration_Start(&hadc2,ADC_SINGLE_ENDED)!=HAL_OK ||
    HAL_ADCEx_InjectedStart(&hadc1)!=HAL_OK || HAL_ADCEx_InjectedStart(&hadc2)!=HAL_OK)Error_Handler();
 mic_encoder_init();mic_encoder_allow_bus_clear(false);mc_lock_pins();
 __HAL_RCC_DMAMUX1_CLK_ENABLE();uno_link_init();MX_USART1_UART_Init();
 HAL_NVIC_SetPriority(TIM1_UP_TIM16_IRQn,0,0);HAL_NVIC_EnableIRQ(TIM1_UP_TIM16_IRQn);
 HAL_NVIC_SetPriority(ADC1_2_IRQn,2,0);HAL_NVIC_EnableIRQ(ADC1_2_IRQn);
 HAL_NVIC_SetPriority(TIM1_BRK_TIM15_IRQn,4,1);HAL_NVIC_EnableIRQ(TIM1_BRK_TIM15_IRQn);
 HAL_NVIC_SetPriority(EXTI15_10_IRQn,3,0);HAL_NVIC_EnableIRQ(EXTI15_10_IRQn);
 mic_io_init();mic_current_init();mic_pin_init();
 while(1){mic_combined_uart_poll();mic_io_poll();mic_pin_poll();
  mic_encoder_allow_bus_clear(!mic_pin_active());mic_encoder_poll();}
}'''
 s=p.once(s,old_main,new_main)
 s=p.once(s,'#include "pin_pwm_diag.h"','#include "pin_pwm_diag.h"\n#include "combined_io_diag.h"\n'+p.read(p.ROOT/'tools/combined_uart.inc'))
 p.write(f,s)
 f=OUT/'nucleo/Src/pin_pwm_diag.c';s=p.read(f).replace('2026102795',str(BUILD))
 s=p.once(s,'#include "pin_pwm_diag.h"','#include "pin_pwm_diag.h"\n#include "combined_io_diag.h"')
 s=p.once(s,'  return bad;','  return bad|mic_io_guard();') if '  return bad;' in s else p.once(s,' return bad;',' return bad|mic_io_guard();')
 # Preserve ADC strobe CCR4 set by mic_current_init; no TIM/ADC trigger changes.
 p.write(f,s)
 f=OUT/'nucleo/Src/stm32g4xx_mc_it.c';s=p.read(f)
 s='#include "combined_io_diag.h"\n'+s
 s=p.once(s,' mic_pin_irq();',' mic_current_update_epoch();mic_pin_irq();')
 s=p.once(s,'  mic_current_adc_irq();','  mic_io_adc_enter();mic_current_adc_irq();mic_io_adc_exit();')
 p.write(f,s)
 for tree in ('build/nucleo','verification','restore','preserved_records'):(OUT/tree).mkdir(parents=True,exist_ok=True)
 shutil.copytree(OLD/'preserved_records',OUT/'preserved_records/earlier',copy_function=os.link)
 for tree in ('build/nucleo','install_r1','idle_confirm_r1'):
  shutil.copytree(OLD/tree,OUT/'preserved_records/2795'/tree,copy_function=os.link)
 trial=p.ROOT/'artifacts/live_bench_20261028/as5600_pin_pwm_5s_r1'
 shutil.copytree(trial,OUT/'preserved_records/2795/as5600_pin_pwm_5s_r1',copy_function=os.link)
 for f in (OLD/'restore').iterdir():shutil.copy2(f,OUT/'restore'/f.name)
 meta=dict(schema='mic_ai.isolated_combined_io.v1',build=BUILD,built=False,installed=False,hardware_tested=False,
  physical_scope='J1/J4 OFF,34pin ribbon disconnected; no motor commands; same PWM/SD/I2C probe map',
  ADC_enabled=True,UART_enabled=True,UART_command_dispatch=False,ADC_currents_qualified=False,
  AS5600_driver_unchanged=True,PWM_BKIN_deadtime_thresholds_unchanged=True,
  stages_ms=[1000,2000,2000],auto_stop_ms=5000,one_request_per_boot=True,
  archived={f.relative_to(OUT/'preserved_records').as_posix():p.sha(f) for f in (OUT/'preserved_records').rglob('*') if f.is_file()},
  limitations=['Isolated combined peripheral test, not complete motor application','ADC inputs float with disconnected inverter; no qualified amperes/RMS','No powered inverter or rotation','Digital Saleae8MS/s does not qualify sub125ns/analog disturbances'])
 p.write(OUT/'manifest.json',json.dumps(meta,indent=2)+'\n');print(json.dumps(dict(prepared=True,build=BUILD,archived=len(meta['archived']),hardware_calls=0)))
if __name__=='__main__':main()
