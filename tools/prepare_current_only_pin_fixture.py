"""Isolated five-second pin test; no AS5600, motor application or power-stage use."""
import json,os,re,shutil
from pathlib import Path
import prepare_current_only as p
from audit_production_pwm_filters import function

OUT=p.ROOT/'artifacts/live_bench_20261029/current_only_pin_fixture_r1'
BUILD=2026102990

def main():
    from install_current_only import verify_package
    verify_package()
    assert not OUT.exists()
    def copy(src,dst):
        rel=Path(src).relative_to(p.OUT/'nucleo')
        if rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dst);return dst
        return shutil.copy2(src,dst)
    shutil.copytree(p.OUT/'nucleo',OUT/'nucleo',copy_function=copy,ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
    source=p.read(p.ROOT/'tools/pin_pwm_diag.c')
    source=source.replace('#include "load_diag.h"\n','').replace('#define PIN_BUILD 2026102794U',f'#define PIN_BUILD {BUILD}U')
    source=source.replace('static ACIM_VF_Handle_t replay;\nstatic RampExtMngr_Handle_t ramp;\n','')
    source=p.once(source,function(source,'counters'),'static void counters(unsigned offset) {(void)offset;}')
    source=p.once(source,' mic_encoder_load_snapshot(v+28);',' /* No encoder in this fixture. */')
    source=p.once(source,' TIM1->CCR1=TIM1->CCR2=TIM1->CCR3=TIM1->ARR/2;',
                  ' TIM1->CCR1=TIM1->ARR/4;TIM1->CCR2=TIM1->ARR/2;TIM1->CCR3=3*TIM1->ARR/4;')
    a=source.index(' if(updates%32U==0)');b=source.index(' ++updates;',a)
    source=source[:a]+source[b:]
    a=source.index('    replay=*pACIM_VF_Component_M1;');b=source.index('\n   }',a)
    source=source[:a]+'''    phase=2;start=DWT->CYCCNT;__DMB();state=1;
    LL_TIM_ClearFlag_UPDATE(TIM1);LL_TIM_EnableIT_UPDATE(TIM1);
    TIM1->BDTR|=TIM_BDTR_MOE;
    if(guard())finish(guard());'''+source[b:]
    source=source.replace(' * AS5600 driver is unchanged; no motor-control scheduler/UART/ADC is started.',
                          ' * No AS5600 code or motor-control scheduler/UART/ADC is started.')
    p.write(OUT/'nucleo/Src/pin_pwm_diag.c',source)
    for name,origin in [('pin_pwm_diag.h','tools/pin_pwm_diag.h'),('load_core.h','tools/no_switch_diag/load_core.h')]:
        shutil.copy2(p.ROOT/origin,OUT/'nucleo/Inc'/name)
    f=OUT/'nucleo/STM32CubeIDE/.project';s=p.read(f)
    s=p.once(s,'\t<linkedResources>','\t<linkedResources>\n\t\t<link>\n\t\t\t<name>Application/User/pin_pwm_diag.c</name>\n\t\t\t<type>1</type>\n\t\t\t<locationURI>PARENT-1-PROJECT_LOC/Src/pin_pwm_diag.c</locationURI>\n\t\t</link>')
    p.write(f,s)
    f=OUT/'nucleo/Src/main.c';s=p.read(f)
    s=p.once(s,'2026102902UL',str(BUILD)+'UL')
    s=p.once(s,'int main(void)','static void unused_motor_main(void) __attribute__((unused));\nstatic void unused_motor_main(void)')
    anchor='/**\n  * @brief System Clock Configuration'
    body='''#include "pin_pwm_diag.h"
/* Dedicated isolated fixture: only GPIO/TIM1/SysTick. No motor boot. */
int main(void) {
  HAL_Init();SystemClock_Config();MX_GPIO_Init();MX_TIM1_Init();
  CoreDebug->DEMCR|=CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CYCCNT=0;DWT->CTRL|=DWT_CTRL_CYCCNTENA_Msk;
  HAL_NVIC_SetPriority(TIM1_UP_TIM16_IRQn,0,0);HAL_NVIC_EnableIRQ(TIM1_UP_TIM16_IRQn);
  HAL_NVIC_SetPriority(TIM1_BRK_TIM15_IRQn,4,1);HAL_NVIC_EnableIRQ(TIM1_BRK_TIM15_IRQn);
  mic_pin_init();
  while(1)mic_pin_poll();
}

'''
    s=p.once(s,anchor,body+anchor);p.write(f,s)
    f=OUT/'nucleo/Src/stm32g4xx_mc_it.c';s='#include "pin_pwm_diag.h"\n'+p.read(f)
    for name,body in [('TIMx_UP_M1_IRQHandler','mic_pin_irq();'),('TIMx_BRK_M1_IRQHandler','mic_pin_break();'),
                      ('SysTick_Handler','HAL_IncTick();'),('HardFault_Handler','LL_TIM_DisableAllOutputs(TIM1);for(;;){}')]:
        s=p.once(s,function(s,name),'void '+name+'(void)\n{\n '+body+'\n}')
    p.write(f,s)
    p.write(OUT/'manifest.json',json.dumps(dict(build=BUILD,scope='isolated_pin_wiring_only',
       production_pair=list(p.NEW),restore_image=str(next((p.OUT/'build/nucleo').glob('*.hex'))),
       boot_outputs_enabled=False,one_request_per_boot=True,duration_ms=5000,
       inverter_ribbon_must_be_disconnected=True,j1_j4_must_be_off=True,
       changes_production_thresholds=False,as5600_enabled=False),indent=2))
    print(OUT)

if __name__=='__main__':main()
