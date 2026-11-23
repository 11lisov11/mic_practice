"""Execute the actual ADC IRQ C body against fake registers, never hardware."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import prepare_current_shunt_monitor as package

PREAMBLE=r'''
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include "current_core.h"
struct Timer {uint32_t CCR1,CCR2,CCR3,CCR4,CNT,CR1,ARR,BDTR;};
struct Adc {uint32_t JSQR,JDR1,ISR;};
static Timer timer;static Adc adc1,adc2;
#define TIM1 (&timer)
#define ADC1 (&adc1)
#define ADC2 (&adc2)
#define TIM_CR1_DIR 16U
#define ADC_JSQR_JSQ1_Pos 8
#define LL_ADC_INJ_TRIG_EXT_TIM1_TRGO 4U
#define LL_ADC_INJ_TRIG_EXT_RISING 1U
enum {CM_SETTLE_TICKS=771};
static uint32_t tick;
static uint16_t bus;
static struct {int _Super;} BusVoltageSensor_M1;
static uint32_t HAL_GetTick(){return tick;}
static uint16_t VBS_GetAvBusVoltage_V(int*){return bus;}
static uint32_t LL_TIM_IsEnabledAllOutputs(Timer *t){return t->BDTR&32768;}
static unsigned LL_ADC_IsActiveFlag_JEOS(Adc *a){return a->ISR&1;}
static void LL_ADC_ClearFlag_JEOS(Adc *a){a->ISR&=~1U;}
static unsigned checks;
static void check(bool okay){++checks;if(!okay){fprintf(stderr,"IRQ check %u failed\n",checks);exit(1);}}
'''
CASES=r'''
static const uint16_t zero[4]={2048,2051,2043,2045};
static void conversion(uint32_t ms,int u=0,int v=0,int w=0,bool second=true) {
 tick=ms;int current[3]={u,v,w};
 unsigned p=cm_path1(pending_pair),q=cm_path2(pending_pair);
 unsigned x=pending_pair==2?1:0,y=pending_pair==0?1:2;
 adc1.JDR1=(zero[p]-current[x])<<4;adc2.JDR1=(zero[q]-current[y])<<4;
 adc1.ISR=1;adc2.ISR=second?1:0;
 mic_current_adc_irq();
 check(timer.CCR1==2656 && timer.CCR2==2656 && timer.CCR3==2656 && timer.CCR4==4928);
 check((adc1.JSQR>>8)==(pending_pair==2?7U:1U));
 check((adc2.JSQR>>8)==(pending_pair==0?7U:6U));
}
int main() {
 cm_init(&state);initialized=1;timer={2656,2656,2656,4928,5000,0,5312,0};
 for(unsigned i=0;i<10000;++i)conversion(i/16);
 check(state.zero_ready && !state.zero_bad);
 for(unsigned i=0;i<4;++i)check(state.offset[i]==zero[i]);
 timer.BDTR=32768;bus=323;
 for(unsigned i=0;i<4000;++i)conversion(1000+i/16,100,-40,-60);
 check(cm_window_valid(&state.published));
 check(state.window.last[0]==100 && state.window.last[1]==-40 && state.window.last[2]==-60);
 unsigned rejected=state.window.bad;
 timer.CR1=TIM_CR1_DIR;conversion(1250,100,-40,-60);
 timer.CR1=0;conversion(1251,100,-40,-60);
 check(state.window.bad>rejected);
 conversion(1252,100,-40,-60,false);check(lost_sync);
 unsigned n=state.window.n;
 for(unsigned i=0;i<100;++i)conversion(1253+i/16,100,-40,-60);
 check(state.window.n==n); // a prior ADC2 result can never become a fresh sample
 timer.BDTR=0;conversion(1260);
 check(!state.was_active && (state.published.flags&CM_FROZEN));
 check(packets==0);
 printf("{\"passed\":true,\"checks\":%u,\"power_pwm_registers_unchanged\":true,\"physical_measurements\":false}",checks);
}
'''

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--candidate',type=Path)
    args=p.parse_args()
    if args.candidate:package.OUT=args.candidate.resolve()
    out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    source=(package.OUT/'nucleo/Src/current_shunt.c').read_text()
    globals_=source[source.index('static cm_core state;'):source.index('void mic_current_init(void)')]
    irq=source[source.index('void mic_current_adc_irq(void)'):source.index('static uint16_t ma_u')]
    unit=out/'actual_irq.cpp';unit.write_text(PREAMBLE+globals_+irq+CASES)
    r=dict(passed=False,hardware_commands=0,physical_measurements=False)
    try:
        with tempfile.TemporaryDirectory() as folder:
            exe=Path(folder)/'irq.exe'
            b=subprocess.run([shutil.which('g++'),'-std=c++17','-Wall','-Wextra','-Werror','-I',str(package.OUT/'nucleo/Inc'),str(unit),'-o',str(exe)],capture_output=True,text=True,timeout=60)
            (out/'compile.log').write_text(b.stdout+b.stderr);assert b.returncode==0,'IRQ harness compilation failed'
            t=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30);assert t.returncode==0,t.stderr
            r.update(json.loads(t.stdout))
    except Exception as exc:r.update(passed=False,error=str(exc))
    (out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r));return 0 if r['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
