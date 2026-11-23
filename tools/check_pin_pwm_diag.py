"""Native execution of the actual isolated fixture plus unchanged AS5600 model."""
import json,re,subprocess,shutil
from pathlib import Path
import prepare_pin_pwm_diag as prep
import prepare_no_switch_diag as p
from audit_production_pwm_filters import function
def main():
 c=prep.OUT;v=c/'verification';mock=v/'mock';mock.mkdir(exist_ok=True)
 for name in ('main.h','mc_config.h','local_stop.h','stm32g4xx_ll_tim.h'):p.write(mock/name,'')
 original=p.read(prep.OLD.with_name('logic_edges_diag_r1')/'test_resources/platform_test.cpp')
 prefix=original[:original.index('#include "load_diag.h"')]
 prefix=prefix.replace('struct ACIM_VF_Handle_t {','struct ACIM_VF_Handle_t {int bVF_Mode=0;')
 prefix+='''
#define VF_OL 1
struct RCCFake {uint32_t AHB2ENR=0;};static RCCFake rcc;
#define RCC (&rcc)
struct SysFake {uint32_t LOAD=169999;};static SysFake syst;
#define SysTick (&syst)
static void LL_TIM_EnableIT_BRK(Timer*t){t->DIER|=128;}
static void LL_TIM_DisableIT_BRK(Timer*t){t->DIER&=~128U;}
void mic_encoder_load_snapshot(uint32_t*v){std::memset(v,0,17*4);v[0]=now_ms/5;v[11]=7;}
#include "pin_pwm_diag.c"
static unsigned checks;
static void test(bool v){++checks;if(!v){fprintf(stderr,"pin_check%u\\n",checks);exit(1);}}
static void reset(){
 tim=Timer{};pa=GPIO{};pb=GPIO{};dwt={};now_ms=0;mic_local_stop_latched=0;
 state=reason=attempted=start=stop=elapsed=phase=updates=cached_at=max_cost=max_gap=break_sr=0;
 previous_irq=previous_poll=max_poll_gap=seq=publish_ms=0;fail_math=0;
 for(unsigned i=7;i<=10;i++)pa.MODER|=2U<<(2*i);
 pa.AFR[0]=6U<<28;pa.AFR[1]=0x666;pa.IDR=64;pb.MODER=10;pb.AFR[0]=0x66;
 mic_pin_init();
}
static void request(){mic_pin_request=PIN_REQUEST;mic_pin_poll();}
int main(){
 reset();test(!state);test(!(tim.BDTR&TIM_BDTR_MOE));request();test(state==1);
 for(unsigned n=1;n<=80000;n++){
  dwt.CYCCNT=n*10625U;now_ms=dwt.CYCCNT/170000;
  if(n%8==0)mic_pin_poll();mic_pin_irq();
  if(n<16000){test(phase==1);test(!(tim.BDTR&TIM_BDTR_MOE));}
  if(n>=16000&&n<48000){test(phase==2);test(tim.BDTR&TIM_BDTR_MOE);test(tim.CCR1==1328&&tim.CCR2==2656&&tim.CCR3==3984);}
  if(n>=48000&&n<80000){test(phase==3);test(tim.BDTR&TIM_BDTR_MOE);}
 }
 test(state==2&&reason==0&&elapsed==850000000);test(!(tim.BDTR&TIM_BDTR_MOE));test(!(tim.DIER&1));
 test(boundaries[2]-boundaries[0]==200);test(boundaries[4]-boundaries[2]==400);test(boundaries[6]-boundaries[4]==400);
 request();test(state==2);test(!(tim.BDTR&TIM_BDTR_MOE));
 now_ms+=50;mic_pin_poll();uint32_t words[64];for(unsigned i=0;i<64;i++)words[i]=mic_pin_report[i];
 test(words[4]==words[61]&&!(words[4]&1));test(ld_crc(words+5,56)==words[62]);
 for(unsigned why=0;why<7;why++){
  reset();request();dwt.CYCCNT=170000000;cached_at=dwt.CYCCNT;mic_pin_irq();test(phase==2);
  if(why==0)pa.IDR=0;
  if(why==1)mic_local_stop_latched=1;
  if(why==2)tim.BDTR^=TIM_BDTR_BKE;
  if(why==3)tim.SR|=TIM_SR_BIF;
  if(why==4)cached_at-=850001;
  if(why==5)tim.BDTR&=~TIM_BDTR_MOE;
  if(why==6)fail_math=1;
  mic_pin_irq();test(state==3&&reason);test(!(tim.BDTR&TIM_BDTR_MOE));test(!(tim.DIER&1));
 }
 reset();pa.MODER=0;request();test(state==4&&reason);test(!(tim.BDTR&TIM_BDTR_MOE));
 reset();request();mic_pin_request=PIN_CANCEL;mic_pin_poll();test(state==3&&reason==128);
 reset();request();mic_pin_break();test(state==3&&reason==4);test(!(tim.BDTR&TIM_BDTR_MOE));
 printf("{\\"passed\\":true,\\"checks\\":%u,\\"actual_hardware_calls\\":0}\\n",checks);
}
'''
 # Python's literal above intentionally contains C escapes only.
 prefix=prefix.replace('static struct {int _Super;} BusVoltageSensor_M1;','')
 file=v/'actual_pin_diag_test.cpp';p.write(file,prefix)
 exe=v/'pin_test.exe';q=subprocess.run(['g++','-std=c++17','-O3','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-misleading-indentation','-Wno-missing-field-initializers','-I',str(mock),'-I',str(c/'nucleo/Inc'),'-I',str(c/'nucleo/Src'),str(file),'-o',str(exe)],capture_output=True,text=True)
 p.write(v/'pin_compile.log',q.stdout+q.stderr);assert q.returncode==0,q.stdout+q.stderr
 q=subprocess.run([str(exe)],capture_output=True,text=True);p.write(v/'pin_test.log',q.stdout+q.stderr);assert q.returncode==0,q.stdout+q.stderr
 result=json.loads(q.stdout)
 for name in ('SystemClock_Config','MX_TIM1_Init'):
  assert function(p.read(prep.OLD/'nucleo/Src/main.c'),name)==function(p.read(c/'nucleo/Src/main.c'),name)
 for rel in ('Src/nucleo_encoder.c','Inc/encoder_core.h','Inc/cleanup_flags.h','Src/mc_tasks.c','Inc/drive_parameters.h'):
  assert p.sha(prep.OLD/'nucleo'/rel)==p.sha(c/'nucleo'/rel),rel
 main=function(p.read(c/'nucleo/Src/main.c'),'main')
 for text in ('MX_MotorControl_Init','MX_ADC','MX_USART','MX_DMA','uno_link_init'):assert text not in main,text
 assert 'HAL_IncTick();' in function(p.read(c/'nucleo/Src/stm32g4xx_mc_it.c'),'SysTick_Handler')
 for rel,h in json.loads(p.read(c/'manifest.json'))['archived'].items():assert p.sha(c/'preserved_records'/rel)==h,rel
 # Reuse the unchanged actual I2C adapter model, not a replacement driver.
 imock=v/'i2c_mock';shutil.copytree(p.BASE/'verification/mock',imock)
 q=subprocess.run(['g++','-std=c++17','-O3','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-I',str(imock),'-I',str(c/'nucleo/Inc'),'-I',str(c/'nucleo/Src'),str(p.ROOT/'tools/i2c_persistent_pe/platform_test.cpp'),'-o',str(v/'i2c.exe')],capture_output=True,text=True)
 p.write(v/'i2c_compile.log',q.stdout+q.stderr);assert q.returncode==0,q.stdout+q.stderr
 checks=[]
 for mode in ('normal','lost_pe','missing_hook'):
  q=subprocess.run([str(v/'i2c.exe'),mode],capture_output=True,text=True);assert q.returncode==0,q.stdout+q.stderr;checks.append(json.loads(q.stdout))
 result.update(I2C=checks,original_TIM1_initializer_unchanged=True,AS5600_driver_unchanged=True,motor_application_not_booted=True)
 p.write(v/'native_tests.json',json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
