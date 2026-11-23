"""Force the exact old guard interleaving and execute old/new C bodies."""
import json,subprocess
import prepare_combined_snapshot_fix as prep
import prepare_no_switch_diag as p
from audit_production_pwm_filters import function
def main():
 v=prep.OUT/'verification'
 old=p.read(prep.OLD/'nucleo/Src/pin_pwm_diag.c');new=p.read(prep.OUT/'nucleo/Src/pin_pwm_diag.c')
 code=r'''
#include <cstdint>
#include <cstdio>
#include <cstdlib>
static void on_read();static void on_write();static void deliver();
static uint32_t mask,reads,target,fired,pending,mode;
struct Reg {uint32_t v=0x1000;operator uint32_t(){on_read();return v;}};
struct Timer {Reg BDTR;uint32_t CCER=0x555,ARR=5312,SR=0;};static Timer timer;
#define TIM1 (&timer)
#define TIM_BDTR_MOE 0x8000U
#define PIN_CC 0x555U
#define TIM_SR_BIF 128U
#define TIM_SR_B2IF 256U
#define GPIO_PIN_6 64U
struct Gpio {uint32_t IDR=64;};static Gpio ga;
#define GPIOA (&ga)
struct Dwt {uint32_t CYCCNT=170000000;};static Dwt dwt;
#define DWT (&dwt)
static uint32_t state=1,phase=1,protection=0x1000,cached_at=170000000;
static uint32_t SystemCoreClock=170000000,reason,stop,elapsed,start,local_stop;
static bool pins_ok(){return true;}
static bool mic_local_stop_blocked(){return local_stop;}
static uint32_t mic_io_guard(){return 0;}
static uint32_t __get_PRIMASK(){return mask;}
static void __disable_irq(){mask=1;}
static void __set_PRIMASK(uint32_t v){mask=v;if(!mask&&pending){pending=0;deliver();}}
static void LL_TIM_DisableAllOutputs(Timer*t){t->BDTR.v&=~TIM_BDTR_MOE;on_write();}
static void LL_TIM_DisableIT_UPDATE(Timer*){}
static void counters(unsigned){}
'''
 code+='\n'+function(old,'guard').replace('guard(void)','old_guard(void)')
 code+='\n'+function(new,'guard')
 code+='\n'+function(old,'finish').replace('finish(uint32_t','old_finish(uint32_t')
 code+='\n'+function(new,'finish')
 code+=r'''
static void deliver(){
 if(mode==1){phase=2;timer.BDTR.v|=TIM_BDTR_MOE;}
 else if(mode==2&&state==1){uint32_t b=guard();if(b){reason|=b;state=3;}}
}
static void interrupt(){if(mask)pending=1;else deliver();}
static void on_read(){++reads;if(mode==1&&reads==target&&!fired){fired=1;interrupt();}}
static void on_write(){if(mode==2&&!fired){fired=1;interrupt();}}
static void reset(){state=1;phase=1;timer.BDTR.v=0x1000;timer.SR=0;ga.IDR=64;
 cached_at=dwt.CYCCNT=170000000;mask=reads=target=fired=pending=reason=mode=0;local_stop=0;}
static unsigned checks;
static void test(bool ok){++checks;if(!ok){fprintf(stderr,"race%u\n",checks);exit(1);}}
int main(){
 reset();mode=1;target=2;test(old_guard()==32);test(phase==2&&timer.BDTR.v&0x8000);
 // The same interrupted publication is deferred until the coherent snapshot.
 reset();mode=1;target=1;test(guard()==0);test(phase==2&&timer.BDTR.v&0x8000);test(guard()==0);
 reset();mode=2;phase=2;timer.BDTR.v|=0x8000;old_finish(0);test(state==3&&reason==32);
 reset();mode=2;phase=2;timer.BDTR.v|=0x8000;finish(0);test(state==2&&reason==0);test(!(timer.BDTR.v&0x8000));
 // Real illegal output states and every pre-existing protection still trip.
 reset();phase=2;test(guard()&32);
 reset();timer.BDTR.v|=0x8000;test(guard()&32);
 reset();timer.SR=128;test(guard()&4);
 reset();ga.IDR=0;test(guard()&4);
 reset();local_stop=1;test(guard()&8);
 reset();cached_at-=850001;test(guard()&16);
 reset();timer.BDTR.v^=0x1000;test(guard()&2);
 printf("{\"passed\":true,\"checks\":%u,\"old_enable_race_reproduced\":true,\"old_stop_race_reproduced\":true,\"fixed_enable_and_stop\":true,\"real_fault_negative_controls\":7,\"hardware_calls\":0}\n",checks);
}
'''
 f=v/'forced_irq_race.cpp';p.write(f,code);exe=v/'forced_irq_race.exe'
 q=subprocess.run(['g++','-std=c++17','-O3','-Wall','-Wextra','-Werror',str(f),'-o',str(exe)],capture_output=True,text=True);p.write(v/'race_compile.log',q.stdout+q.stderr);assert q.returncode==0,q.stdout+q.stderr
 q=subprocess.run([str(exe)],capture_output=True,text=True);p.write(v/'race_run.log',q.stdout+q.stderr);assert q.returncode==0,q.stdout+q.stderr
 r=json.loads(q.stdout);p.write(v/'preemption_test.json',json.dumps(r,indent=2)+'\n');print(json.dumps(r))
if __name__=='__main__':main()
