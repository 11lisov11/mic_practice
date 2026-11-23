"""Exercise actual bounded guard/math and check native safety/command preservation."""
import json, subprocess
import prepare_no_switch_diag as p
import prepare_full_mcsdk_diag as prep
from audit_production_pwm_filters import function

def main():
 c=prep.OUT;v=c/'verification';mock=v/'mock';mock.mkdir(exist_ok=True)
 for name in ('main.h','mc_config.h','mc_api.h','local_stop.h','stm32g4xx_ll_tim.h'):p.write(mock/name,'')
 results={}
 flags=['g++','-std=c++17','-O3','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers']
 def run(tag,src,extra=()):
  exe=v/(tag+'.exe');q=subprocess.run(flags+list(extra)+[str(src),'-o',str(exe)],capture_output=True,text=True,timeout=60)
  p.write(v/(tag+'_compile.log'),q.stdout+q.stderr);assert q.returncode==0,q.stderr
  q=subprocess.run([str(exe)],capture_output=True,text=True,timeout=60);p.write(v/(tag+'.log'),q.stdout+q.stderr)
  assert q.returncode==0,q.stderr;results[tag]=json.loads(q.stdout)
 for name in ('core','platform'):
  run(name,c/'test_resources'/(name+'_test.cpp'),['-I',str(mock),'-I',str(c/'test_resources')])
 # Test the new actual counter/transport guard bodies, including wrap and latched faults.
 src=p.read(c/'nucleo/Src/full_mcsdk_runtime.inc')
 code='''#include <cstdint>
#include <cstdio>
#include <cstdlib>
static bool active;
static bool mic_load_active(){return active;}
enum {UNO_MODE_OFF=0,UNO_FLAG_ENABLE=1,UNO_FLAG_CLEAR_FAULT=8,UNO_LINK_TIMEOUT_MS=300};
static uint32_t tick;static uint32_t HAL_GetTick(){return tick;}
static uint32_t uno_rx_errors,uno_rx_overflow,full_uart_faults;
static struct {uint32_t last_valid_ms,bad_count;bool link_seen;}uno_link;
static struct {uint32_t fault;}uno_transport;
static struct {uint32_t timeouts,dma_errors,full_errors;}mic_uart_tx;
static volatile uint32_t full_tasks[4],full_commands[2];
'''
 for name in ('mic_full_task','mic_full_command','mic_full_guard'):code+=function(src,name)+'\n'
 code+='''static unsigned checks;static void test(bool b){++checks;if(!b)std::exit(1);}
int main(){
 uno_link.link_seen=true;uno_link.last_valid_ms=100;tick=399;test(mic_full_guard()==0);
 tick=400;test(mic_full_guard()==0);tick=401;test(mic_full_guard()==256);
 tick=100;test(mic_full_guard()==256);full_uart_faults=0;
 uno_link.last_valid_ms=0xfffffff0U;tick=0x10;test(mic_full_guard()==0);
 for(unsigned k=0;k<7;k++){
  full_uart_faults=0;uno_rx_errors=uno_rx_overflow=uno_link.bad_count=uno_transport.fault=0;
  mic_uart_tx={};uint32_t*fields[]={&uno_rx_errors,&uno_rx_overflow,&uno_link.bad_count,&uno_transport.fault,&mic_uart_tx.timeouts,&mic_uart_tx.dma_errors,&mic_uart_tx.full_errors};
  *fields[k]=1;test(mic_full_guard()==256);
 }
 for(unsigned n=0;n<10000;n++){active=n<5000;for(unsigned i=0;i<4;i++)mic_full_task(i);}
 for(unsigned i=0;i<4;i++){test(full_tasks[i]==5000);}
 active=true;mic_full_command(0,0);mic_full_command(1,1);mic_full_command(8,0);mic_full_command(2,0);
 test(full_commands[0]==4&&full_commands[1]==4);
 printf("{\\\"passed\\\":true,\\\"checks\\\":%u}\\n",checks);
}
'''.replace('\\\"','\\"')
 p.write(v/'actual_full_guard.cpp',code);run('full_guard',v/'actual_full_guard.cpp')
 p.OUT=c
 import no_switch_diag_math_test as math
 math.main();results['math']=json.loads(p.read(v/'math_report.json'))
 oldmain=p.read(prep.OLD/'nucleo/Src/main.c');main=p.read(c/'nucleo/Src/main.c')
 for name in ('SystemClock_Config','MX_ADC1_Init','MX_ADC2_Init','MX_TIM1_Init','MX_USART1_UART_Init','USART1_IRQHandler','uno_link_poll','uno_transport_result','uno_rearm_break_irq'):
  assert function(oldmain,name)==function(main,name),name
 native=function(oldmain,'uno_handle_valid_frame').replace('  /* Diagnostic image cannot accept any motor ENABLE request. */\n  if ((flags & UNO_FLAG_ENABLE) != 0U) { uno_stop_motor(); return; }\n','')
 actual=function(main,'uno_handle_valid_frame').replace('\n  mic_full_command(frame[3],frame[4]);','').replace('  /* Extra fixture inhibit, after unchanged native validation; never authorize START. */\n  ++mic_full_fixture_denials;uno_stop_motor();return;\n','')
 assert native==actual,'Original command validation changed'
 oldtasks=p.read(prep.OLD/'nucleo/Src/mc_tasks.c');tasks=p.read(c/'nucleo/Src/mc_tasks.c')
 for name,i in [('MC_RunMotorControlTasks',0),('TSK_SafetyTask',1),('TSK_MediumFrequencyTaskM1',2),('TSK_HighFrequencyTask',3)]:
  assert function(oldtasks,name)==function(tasks,name).replace(f'\n  mic_full_task({i});',''),name
 assert function(oldtasks,'TSK_SafetyTask_PWMOFF')==function(tasks,'TSK_SafetyTask_PWMOFF')
 assert p.read(c/'nucleo/Src/stm32g4xx_mc_it.c')==p.read(prep.REFERENCE/'nucleo/Src/stm32g4xx_mc_it.c')
 for rel in ('Src/nucleo_encoder.c','Src/current_shunt.c','Inc/encoder_core.h','Inc/bus_clear.h','Inc/cleanup_flags.h','Inc/drive_parameters.h','Inc/parameters_conversion.h'):
  assert p.sha(c/'nucleo'/rel)==p.sha(prep.OLD/'nucleo'/rel),rel
 assert 'mic_load_prepare_pins();\n  MX_MotorControl_Init();' in main
 assert 'else LL_TIM_DisableAllOutputs(timer);' in main
 for rel,h in json.loads(p.read(c/'manifest.json'))['archived'].items():assert p.sha(c/'preserved_records'/rel)==h,rel
 results.update(passed=True,hardware_calls=0,native_safety_and_command_validation_unchanged=True,ADC_I2C_sources_unchanged=True,full_MCSDK_routing_restored=True,archives_verified=True)
 p.write(v/'native_tests.json',json.dumps(results,indent=2)+'\n');print(json.dumps(results))
if __name__=='__main__':main()
