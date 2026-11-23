"""Native fault/deadline tests, actual ADC IRQ replay and source isolation."""
import json,re,shutil,subprocess
import prepare_no_switch_diag as p
import current_shunt_irq_selftest as irq
import current_peak_capture_selftest as peak
from prepare_current_zero_noise import REPORT_DECL
from audit_production_pwm_filters import function

def run(v,tag,args):
 q=subprocess.run(args,capture_output=True,text=True,timeout=60)
 p.write(v/(tag+'.log'),q.stdout+q.stderr)
 if q.returncode:print(q.stdout+q.stderr);q.check_returncode()
 return q.stdout
ADC_TEST=r'''
#include <cmath>
int main(){
 cm_init(&state);state.zero_ready=1;state.zero_stable=3;state.zero_attempts=3;
 for(unsigned i=0;i<4;++i)state.offset[i]=2067;
 pc_init(&peak);peak_sealed=0;lost_sync=0;initialized=1;
 pending_valid=1;pending_active=0;pending_epoch=1;peak_epoch=0;
 timer={2656,2656,2656,4928,110,0,5312,0};bus=10;
 diag=true;
 for(unsigned n=0;n<80000;n++){
  uint32_t c[4]={timer.CCR1,timer.CCR2,timer.CCR3,timer.CCR4};
  timer.CNT=110;timer.CR1=0;mic_current_update_epoch();
  float angle=6.283185307f*5.0f*n/16000.0f;
  timer.CCR1=unsigned(2655+325*std::sin(angle));
  timer.CCR2=unsigned(2655+325*std::sin(angle+2.0943951f));
  timer.CCR3=unsigned(2655+325*std::sin(angle+4.1887902f));
  tick=1000+n/16;dwt.CYCCNT=n*10625U;
  timer.CNT=c[3]-50;timer.CR1=TIM_CR1_DIR;
  unsigned a=cm_path1(pending_pair),b=cm_path2(pending_pair);
  adc1.JDR1=(state.offset[a]-78)<<4;adc2.JDR1=(state.offset[b]+39)<<4;
  adc1.ISR=adc2.ISR=1;adc1.JSQR=adc2.JSQR=0;
  unsigned before[3]={timer.CCR1,timer.CCR2,timer.CCR3};
  mic_current_adc_irq();
  check(timer.BDTR==0);check(timer.CCR1==before[0]&&timer.CCR2==before[1]&&timer.CCR3==before[2]);
  check(timer.CCR4<=5184&&timer.CCR4>0);
 }
 check(entered==80000&&exited==80000);check(accepted>79000);
 check(state.published.n>1000);check(!lost_sync);check(mic_current_load_quality()==1);
 // Physical pins/MOE stayed OFF while the active timing/reconstruction branch ran.
 check(state.zero_ready&&state.zero_stable==3);check(timer.BDTR==0);check(packets==0);
 printf("{\"passed\":true,\"checks\":%u,\"adc_calls\":%u,\"accepted\":%u,\"actual_target_irq_body\":true,\"physical_MOE\":0}\n",checks,entered,accepted);
}
'''
def main():
 c=p.OUT;v=c/'verification';v.mkdir(exist_ok=True);mock=v/'mock';mock.mkdir(exist_ok=True)
 for name in ('main.h','mc_config.h','mc_api.h','local_stop.h','stm32g4xx_ll_tim.h'):p.write(mock/name,'')
 flags=['g++','-std=c++17','-O3','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers']
 results={}
 for tag in ('core','platform'):
  exe=v/(tag+'.exe');run(v,tag+'_compile',flags+['-I',str(mock),'-I',str(p.RES),str(p.RES/(tag+'_test.cpp')),'-o',str(exe)])
  results[tag]=json.loads(run(v,tag,[str(exe)]))
 source=p.read(c/'nucleo/Src/current_shunt.c')
 globals_=source[source.index('static cm_core state;'):source.index('void mic_current_init(void)')]
 adc=source[source.index('void mic_current_adc_irq(void)'):source.index('static uint16_t ma_u')]
 pre=irq.PREAMBLE.replace('#include "current_core.h"',REPORT_DECL+'#include "current_core.h"\n#include "current_adc_window_plan.h"\n#include "current_adc_deadline.h"')
 pre=pre.replace('enum {CM_SETTLE_TICKS=771};','enum {CM_SETTLE_TICKS=771,CM_BEFORE_TOP=128,CM_IDLE_BEFORE_TOP=384,CM_ACQUIRE_TICKS=112};')
 pre+='''
static bool diag;static unsigned entered,exited,accepted;
static bool mic_load_active(){return diag;}
static void mic_load_adc_enter(uint32_t){++entered;}
static void mic_load_adc_exit(uint32_t,unsigned good){++exited;accepted+=good?1:0;}
static void LL_TIM_OC_SetCompareCH4(Timer*t,uint32_t v){t->CCR4=v;}
'''
 code=pre+peak.EXTRA+globals_+adc+ADC_TEST
 p.write(v/'actual_diag_adc.cpp',code)
 exe=v/'adc.exe';run(v,'adc_compile',flags+['-I',str(c/'nucleo/Inc'),'-I',str(p.BASE/'UNOQ_MOTOR'),str(v/'actual_diag_adc.cpp'),'-o',str(exe)])
 results['adc']=json.loads(run(v,'adc',[str(exe)]))
 # Exercise the unchanged full platform I2C driver, including physical MMIO hooks.
 imock=v/'i2c_mock';imock.mkdir(exist_ok=True)
 for f in (p.BASE/'verification/mock').iterdir():
  if f.is_file():shutil.copy2(f,imock/f.name)
 exe=v/'i2c.exe';run(v,'i2c_compile',flags+['-I',str(imock),'-I',str(c/'nucleo/Inc'),'-I',str(c/'nucleo/Src'),str(p.ROOT/'tools/i2c_persistent_pe/platform_test.cpp'),'-o',str(exe)])
 results['i2c']=[json.loads(run(v,'i2c_'+mode,[str(exe),mode])) for mode in ('normal','lost_pe','missing_hook')]
 changed=[]
 allowed={'Src/main.c','Src/mc_tasks.c','Src/current_shunt.c','Src/nucleo_encoder.c','STM32CubeIDE/.project','MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLibACIM/Any/Src/pwm.c'}
 for f in (p.BASE/'nucleo').rglob('*'):
  if not f.is_file() or any(x in ('Debug','Release','.settings') for x in f.parts):continue
  rel=f.relative_to(p.BASE/'nucleo').as_posix();g=c/'nucleo'/rel
  if f.read_bytes()!=g.read_bytes() and p.identity(p.read(f))!=p.read(g):
   assert rel in allowed,rel;changed.append(rel)
 assert set(changed)==allowed,changed
 a=p.read(p.BASE/'nucleo/Src/main.c');b=p.read(c/'nucleo/Src/main.c')
 for name in ('SystemClock_Config','MX_NVIC_Init','MX_TIM1_Init','MX_ADC1_Init','MX_ADC2_Init','uno_rearm_break_irq','uno_capture_diagnostics'):
  assert function(a,name)==function(b,name),name
 a=p.read(p.BASE/'nucleo/Src/mc_tasks.c');b=p.read(c/'nucleo/Src/mc_tasks.c')
 for name in ('TSK_SafetyTask','TSK_SafetyTask_PWMOFF','TSK_SafetyTask_LSON'):
  if re.search(r'\b'+name+r'\(',a):assert function(a,name)==function(b,name),name
 assert 'return faults &' not in p.read(c/'nucleo/Src/load_diag.c')
 assert p.read(c/'nucleo/Inc/encoder_core.h')==p.read(p.BASE/'nucleo/Inc/encoder_core.h')
 for rel,sha in json.loads(p.read(c/'manifest.json'))['preserved_records'].items():assert p.sha(c/'preserved_records'/rel)==sha,rel
 # Complete predecessor sealing, including its installed images, stays intact.
 m=json.loads(p.read(p.BASE/'manifest.json'))
 for table in ('source_sha256','build_sha256','verification_sha256'):
  for rel,sha in m[table].items():assert p.sha(p.BASE/rel)==sha,rel
 results.update(passed=True,hardware_calls=0,changed_existing_files=sorted(changed),protection_functions_unchanged=True,clocks_timer_ADC_initializers_unchanged=True,old_images_and_captures_unchanged=True)
 p.write(v/'native_tests.json',json.dumps(results,indent=2)+'\n');print(json.dumps(results))
if __name__=='__main__':main()
