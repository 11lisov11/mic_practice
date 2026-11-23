"""Actual combined guard, production ADC IRQ and UART DMA/parser native tests."""
import json,re,subprocess,shutil
import prepare_combined_io_diag as prep
import prepare_no_switch_diag as p
from audit_production_pwm_filters import function
def main():
 c=prep.OUT;v=c/'verification';mock=v/'mock';mock.mkdir(exist_ok=True)
 for name in ('main.h','mc_config.h','local_stop.h','stm32g4xx_ll_tim.h'):p.write(mock/name,'')
 code=p.read(prep.OLD/'verification/actual_pin_diag_test.cpp')
 code=code.replace('struct RCCFake {uint32_t AHB2ENR=0;}', 'struct RCCFake {uint32_t AHB2ENR=0,CCIPR=0;}')
 code=p.once(code,'#include "pin_pwm_diag.c"','''
static uint32_t test_irq_mask;
static uint32_t __get_PRIMASK(){return test_irq_mask;}
static void __disable_irq(){test_irq_mask=1;}
static void __set_PRIMASK(uint32_t v){test_irq_mask=v;}
struct AdcFake {uint32_t CR=1,ISR=64,JSQR=0;};static AdcFake a1,a2;
#define ADC1 (&a1)
#define ADC2 (&a2)
#define ADC_ISR_JEOS 64U
#define ADC_ISR_JQOVF 1024U
void mic_io_uart_snapshot(uint32_t*v){for(unsigned i=0;i<16;i++)v[i]=0;v[2]=now_ms/20+1;v[6]=now_ms/20+1;v[13]=now_ms;}
#define publish_ms io_publish_ms
#include "combined_io_diag.c"
#undef publish_ms
#include "pin_pwm_diag.c"
''')
 code=p.once(code,' mic_pin_init();',''' adc_seen=200;adc_active=adc_at=adc_enter=adc_cost=adc_gap=adc_bad=adc_previous=0;
 sequence=0;uart_flags=0;uart_at=0;uart_frames=uart_completed=1;a1=AdcFake{};a2=AdcFake{};
 mic_io_init();mic_io_poll();mic_pin_init();''')
 code=p.once(code,'  if(n%8==0)mic_pin_poll();mic_pin_irq();','  mic_io_adc_enter();if(n%8==0){mic_io_poll();mic_pin_poll();}mic_pin_irq();mic_io_adc_exit();')
 # The pre-existing error tests deliberately jump time by1s; keep ADC fresh
 # so those cases continue to isolate their original guard condition.
 code=code.replace('cached_at=dwt.CYCCNT;mic_pin_irq();','cached_at=adc_at=dwt.CYCCNT;mic_io_poll();mic_pin_irq();')
 code=p.once(code,'request();test(state==2);','test(adc_active==80000);request();test(state==2);')
 code=p.once(code,' printf(','''
 reset();request();dwt.CYCCNT=170000000;cached_at=dwt.CYCCNT;adc_at=dwt.CYCCNT-850001;mic_io_poll();mic_pin_irq();test(state==3&&(reason&256));test(!(tim.BDTR&TIM_BDTR_MOE));
 reset();request();uart_flags=1;mic_pin_irq();test(state==3&&(reason&512));
 reset();request();adc_bad=1;mic_pin_irq();test(state==3&&(reason&256));
 reset();request();uart_at=0;now_ms=301;mic_pin_irq();test(state==3&&(reason&512));
 printf(''')
 p.write(v/'combined_guard_test.cpp',code)
 flags=['g++','-std=c++17','-O3','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-Wno-unused-function','-Wno-misleading-indentation']
 def run(tag,args):
  q=subprocess.run(args,capture_output=True,text=True);p.write(v/(tag+'.log'),q.stdout+q.stderr);assert q.returncode==0,q.stdout+q.stderr;return q.stdout
 exe=v/'guard.exe';run('guard_compile',flags+['-I',str(mock),'-I',str(c/'nucleo/Inc'),'-I',str(c/'nucleo/Src'),str(v/'combined_guard_test.cpp'),'-o',str(exe)])
 results=dict(guard=json.loads(run('guard',[str(exe)])))
 # Recompile the earlier actual80k ADC IRQ replay against this image's headers.
 test_source=p.ROOT/'artifacts/live_bench_20261027/no_switch_diag_r3/verification/actual_diag_adc.cpp'
 adc=p.read(c/'nucleo/Src/current_shunt.c');body=adc[adc.index('void mic_current_adc_irq(void)'):adc.index('static uint16_t ma_u')]
 assert body in p.read(test_source)
 exe=v/'adc.exe';run('adc_compile',flags+['-I',str(c/'nucleo/Inc'),'-I',str(p.BASE/'UNOQ_MOTOR'),str(test_source),'-o',str(exe)])
 results['adc']=json.loads(run('adc',[str(exe)]))
 # Full unchanged UART DMA sender, including the historical short-CRC-tail case.
 main=p.read(c/'nucleo/Src/main.c');prior=p.read(prep.OLD/'nucleo/Src/main.c')
 start=main.index('/* USART1 TX owns DMA1 channel 1');end=main.index('\nstatic bool uno_rx_push',start)
 driver=main[start:end].strip()+'\n';assert driver in prior
 p.write(v/'driver.inc',driver)
 from uart_tx_dma_selftest import body as function_body
 hal=p.read(c/'nucleo/Drivers/STM32G4xx_HAL_Driver/Src/stm32g4xx_hal_uart.c')
 p.write(v/'old_hal_transmit.inc',function_body(hal,'HAL_UART_Transmit')+'\n')
 shutil.copy2(p.ROOT/'tools/uart_tx_dma/driver_test.cpp',v/'driver_test.cpp')
 exe=v/'uart_dma.exe';run('uart_dma_compile',flags+['-I',str(c/'nucleo/Inc'),str(v/'driver_test.cpp'),'-o',str(exe)])
 results['uart_dma']=json.loads(run('uart_dma',[str(exe)]))
 exe=v/'uart_parser.exe';run('uart_parser_compile',flags+['-I',str(c/'nucleo/Inc'),'-I',str(p.BASE/'UNOQ_MOTOR'),str(p.ROOT/'tools/uart_resync_fix/contract_test.cpp'),'-o',str(exe)])
 results['uart_parser']=json.loads(run('uart_parser',[str(exe)]))
 for name in ('SystemClock_Config','MX_TIM1_Init','MX_ADC1_Init','MX_ADC2_Init','MX_USART1_UART_Init','USART1_IRQHandler'):
  assert function(prior,name)==function(main,name),name
 for rel in ('Src/nucleo_encoder.c','Inc/encoder_core.h','Inc/cleanup_flags.h','Inc/bus_clear.h','Src/current_shunt.c','Src/mc_tasks.c','Inc/drive_parameters.h'):
  assert p.sha(prep.OLD/'nucleo'/rel)==p.sha(c/'nucleo'/rel),rel
 uart=p.read(p.ROOT/'tools/combined_uart.inc')
 for forbidden in ('uno_handle_valid_frame','MC_Start','MC_Program','mic_local_stop_enable_outputs'):assert forbidden not in uart
 for rel,h in json.loads(p.read(c/'manifest.json'))['archived'].items():assert p.sha(c/'preserved_records'/rel)==h,rel
 results.update(passed=True,checks=results['guard']['checks'],hardware_calls=0,original_BKIN_ADC_UART_initializers_unchanged=True,UART_motor_dispatch_impossible=True,archives_verified=True)
 p.write(v/'native_tests.json',json.dumps(results,indent=2)+'\n');print(json.dumps(results))
if __name__=='__main__':main()
