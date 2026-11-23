"""Execute the actual isolated pin state machine with fake registers; seal its build."""
import json,re,shutil,subprocess,tempfile
from pathlib import Path
import prepare_current_only as p
import prepare_current_only_pin_fixture as fixture
from audit_production_pwm_filters import function

PRE=r'''
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include "load_core.h"
struct Timer {uint32_t BDTR,CCER,ARR,CCR1,CCR2,CCR3,EGR,SR,CR1,DIER,RCR,PSC,AF1,SMCR;};
struct Gpio {uint32_t MODER,AFR[2],IDR;};
struct Counter {uint32_t CYCCNT;};struct Clocks {uint32_t AHB2ENR;};struct Tick {uint32_t LOAD;};
static Timer timer;static Gpio ga,gb;static Counter dwt;static Clocks rcc;static Tick systick;
#define TIM1 (&timer)
#define GPIOA (&ga)
#define GPIOB (&gb)
#define DWT (&dwt)
#define RCC (&rcc)
#define SysTick (&systick)
#define GPIO_PIN_6 64U
#define TIM_BDTR_MOE 32768U
#define TIM_BDTR_BKE 4096U
#define TIM_BDTR_AOE 16384U
#define TIM_SR_BIF 128U
#define TIM_SR_B2IF 256U
#define TIM_CR1_CEN 1U
#define TIM_EGR_UG 1U
static uint32_t SystemCoreClock=170000000U;
static volatile uint32_t mic_local_stop_latched;
static bool mic_local_stop_blocked(){return mic_local_stop_latched!=0;}
static uint32_t HAL_GetTick(){return dwt.CYCCNT/170000U;}
static void __DMB(){}
static void LL_TIM_DisableAllOutputs(Timer*t){t->BDTR&=~TIM_BDTR_MOE;}
static void LL_TIM_DisableIT_UPDATE(Timer*t){t->DIER&=~1U;}
static void LL_TIM_EnableIT_UPDATE(Timer*t){t->DIER|=1U;}
static void LL_TIM_DisableIT_BRK(Timer*t){t->DIER&=~128U;}
static void LL_TIM_EnableIT_BRK(Timer*t){t->DIER|=128U;}
static void LL_TIM_ClearFlag_UPDATE(Timer*t){t->SR&=~1U;}
static void check(bool ok){if(!ok)std::abort();}
'''
CASES=r'''
int main(int argc,char**argv){
 unsigned c=argc>1?unsigned(std::atoi(argv[1])):0;
 timer.BDTR=TIM_BDTR_BKE|0x9050;timer.ARR=5312;
 ga.MODER=(2U<<14)|(2U<<16)|(2U<<18)|(2U<<20);ga.AFR[0]=6U<<28;ga.AFR[1]=0x666;
 gb.MODER=10;gb.AFR[0]=0x66;ga.IDR=GPIO_PIN_6;systick.LOAD=169999;
 mic_pin_init();check(!(timer.BDTR&TIM_BDTR_MOE));
 if(c==4)SystemCoreClock=160000000;
 mic_pin_request=PIN_REQUEST;mic_pin_poll();
 if(c==4){check(state==4 && !(timer.BDTR&TIM_BDTR_MOE));return 0;}
 check(state==1 && (timer.BDTR&TIM_BDTR_MOE));
 check(timer.CCR1==1328 && timer.CCR2==2656 && timer.CCR3==3984);
 if(c==1){mic_pin_request=PIN_CANCEL;mic_pin_poll();check(state==3 && reason==128);}
 if(c==2){ga.IDR=0;mic_pin_irq();check(state==3 && (reason&4));}
 if(c==3){dwt.CYCCNT+=850001;mic_pin_irq();check(state==3 && (reason&16));}
 if(c==5){mic_local_stop_latched=1;mic_pin_irq();check(state==3 && (reason&8));}
 if(c==0){
  for(unsigned i=0;i<80010 && state==1;i++){dwt.CYCCNT+=10624;mic_pin_poll();mic_pin_irq();}
  check(state==2 && reason==0 && elapsed>=850000000 && elapsed<850011000);
  mic_pin_request=PIN_REQUEST;mic_pin_poll();check(state==2 && attempted==1);
 }
 check(!(timer.BDTR&TIM_BDTR_MOE));return 0;
}
'''

def main():
    c=fixture.OUT;v=c/'verification';v.mkdir(exist_ok=True)
    src=p.read(c/'nucleo/Src/pin_pwm_diag.c')
    assert 'mic_encoder_' not in src and 'AS5600 driver is unchanged' not in src
    assert 'ACIM_VF_' not in src and 'replay.' not in src
    for name in ('MX_TIM1_Init','mic_local_stop_blocked'):
        assert function(p.read(c/'nucleo/Src/main.c'),name)==function(p.read(p.OUT/'nucleo/Src/main.c'),name)
    unit=PRE+re.sub(r'^#include.*$','',src,flags=re.M)+CASES
    p.write(v/'actual_pin_state_machine.cpp',unit)
    with tempfile.TemporaryDirectory(prefix='pin_test_') as d:
        exe=Path(d)/'pin.exe'
        r=subprocess.run([shutil.which('g++'),'-std=c++17','-Wall','-Wextra','-Werror','-I',str(c/'nucleo/Inc'),str(v/'actual_pin_state_machine.cpp'),'-o',str(exe)],capture_output=True,text=True)
        p.write(v/'host_build.log',r.stdout+r.stderr);r.check_returncode()
        for case in range(6):subprocess.run([str(exe),str(case)],check=True,timeout=10)
    b=c/'nucleo/STM32CubeIDE/Debug';bm=json.loads(p.read(next(b.glob('*.build-manifest.json'))))
    assert bm['firmware_build_id']==fixture.BUILD and bm['build_errors']==bm['build_warnings']==0
    for item in bm['artifacts']:assert p.sha(b/item['file'])==item['sha256'].lower()
    gnu=Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.14.3.rel1.win32_1.0.100.202602081740/tools/bin')
    lines=subprocess.check_output([str(gnu/'arm-none-eabi-nm.exe'),'-S','-n',str(next(b.glob('*.elf')))],text=True)
    symbols={}
    for line in lines.splitlines():
        a=line.split()
        if len(a)==4 and a[3] in ('mic_pin_request','mic_pin_report'):
            symbols[a[3]]=dict(address=int(a[0],16),bytes=int(a[1],16))
    assert symbols['mic_pin_request']['bytes']==4 and symbols['mic_pin_report']['bytes']==256
    assert 'mic_encoder_' not in lines and 'mic_i2c_wire_' not in lines
    p.write(v/'symbols.json',json.dumps(symbols,indent=2))
    report=dict(passed=True,actual_C_state_machine_cases=6,target_errors=0,target_warnings=0,
       default_off=True,native_auto_stop_5s=True,one_attempt_only=True,
       cancel_break_clock_local_stop_and_stall_tested=True,as5600_code_absent=True,
       production_timer_and_break_config_unchanged=True,hardware_commands=0)
    p.write(v/'report.json',json.dumps(report,indent=2))
    m=json.loads(p.read(c/'manifest.json'));m.update(built=True,offline_verified=True)
    m['sealed_sha256']={str(f.relative_to(c)).replace('\\','/'):p.sha(f) for folder in ('nucleo','verification') for f in (c/folder).rglob('*') if f.is_file() and not any(x in ('Debug','Release','__pycache__') for x in f.relative_to(c).parts)}
    m['image_sha256']=p.sha(next(b.glob('*.hex')))
    p.write(c/'manifest.json',json.dumps(m,indent=2));print(json.dumps(report))

if __name__=='__main__':main()
