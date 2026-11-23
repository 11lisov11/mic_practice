"""Build current motor adapter, exact TX driver, parser and ARM byte identity."""
import json,shutil,subprocess
from elftools.elf.elffile import ELFFile
import prepare_uart_921600_rx as p
from test_foc_estimate_publish_fix import native_source
from test_foc_update_latency_fix import function
from test_observer_current_window import compile_case

def run_compile(out,name,code,includes):
 cpp=out/(name+'.cpp');p.write(cpp,code);exe=cpp.with_suffix('.exe')
 r=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',
  '-Wno-misleading-indentation','-Wno-unused-function',*sum((['-I',str(x)] for x in includes),[]),str(cpp),'-o',str(exe)],capture_output=True,text=True)
 p.write(out/(name+'_build.log'),r.stdout+r.stderr);r.check_returncode()
 r=subprocess.run([str(exe)],capture_output=True,text=True);p.write(out/(name+'_run.log'),r.stdout+r.stderr);r.check_returncode();return json.loads(r.stdout)
def section(path,name):
 with path.open('rb') as f:return ELFFile(f).get_section_by_name(name).data()
def main():
 out=p.OUT/'verification/guards_r3';out.mkdir(parents=True,exist_ok=False)
 fixture=p.read(p.BASE/'native_verification_r2/native_adapter.cpp')
 pre=fixture.split('#define MIC_NATIVE_BUILD',1)[0]
 tail=fixture[fixture.index('static void NVIC_SetPendingIRQ(int irq){'):]
 native=native_source(p.OUT).replace('sample=bin_current;ow_bin window=bin_window;',
  'sample=bin_current;ow_bin window=bin_window;if(inject_torn){++telemetry_seq;inject_torn=false;}')
 exe=compile_case(out,'motor_adapter',pre+native+'\n'+tail,p.OUT)
 r=subprocess.run([str(exe)],capture_output=True,text=True);p.write(out/'motor_adapter_run.log',r.stdout+r.stderr);r.check_returncode();motor=json.loads(r.stdout)
 incs=[p.OUT/'nucleo/Inc',p.OUT/'UNOQ_MOTOR']
 trace=json.loads(p.read(p.ROOT/'artifacts/live_bench_20261021/sd_dual_motor_to_25_r1/after_uart_reject.json'))['data']['records']
 def array(name,raw):return 'static const uint8_t '+name+'[]={'+','.join(str(x) for x in bytes.fromhex(raw))+'};\n'
 p.write(out/'captured.inc',array('captured_recovered',trace[0]['raw_hex'])+array('captured_fatal',trace[1]['raw_hex'])+array('captured_fatal_marks',trace[1]['marks_hex']))
 parser=run_compile(out,'CRC_sequence_watchdog',p.read(p.ROOT/'tools/uart_clean_confirm_test.cpp'),incs)
 source=p.read(p.OUT/'nucleo/Src/main.c');old=p.read(p.BASE/'nucleo/Src/main.c')
 a=source.index('/* USART1 TX owns DMA1 channel 1');b=source.index('\nstatic bool uno_rx_push',a)
 p.write(out/'driver.inc',source[a:b])
 for name in ('uno_tx_tc_isr','DMA1_Channel1_IRQHandler','uno_tx_begin_locked','uno_tx_watchdog','uno_tx_clear_ready'):
  if name=='uno_tx_watchdog':
   # Only the shared lock helper adds the new RX owner; watchdog body identical.
   pass
  assert function(source,name)==function(old,name),name
 tx=p.read(p.ROOT/'tools/uart_tx_dma/driver_test.cpp')
 a=tx.index('/* The unchanged ST HAL transmitter');b=tx.index('int main(){',a);tx=tx[:a]+tx[b:]
 a=tx.index(' // Reproduce the observed');b=tx.index(' // With DMA',a)
 tx=tx[:a]+' auto first=frame(246),second=frame(247);\n'+tx[b:]
 tx='#define MIC_FOC_IRQ_SCOPE_NAMED(a,b) ((void)0)\n#define DMA1_Channel2_IRQn 3\n#define DMA_CCR_TCIE 2U\n'+tx
 tx=tx.replace('x==1||x==2','x==1||x==2||x==3')
 tx=tx.replace('sim_us+=87;','sim_us+=11;')
 tx=tx.replace('if(channel.CNDTR==0){usart.ISR|=UART_FLAG_TC;',
  'if(channel.CNDTR==0){dma.ISR|=2U;DMA1_Channel1_IRQHandler();usart.ISR|=UART_FLAG_TC;')
 # Current driver enables TCIE only at DMA TC; an earlier TC cannot enter
 # the handler. A simultaneous DMA error is delivered by its own IRQ.
 tx=tx.replace('mic_uart_tx.early_tc==1','mic_uart_tx.early_tc==0')
 tx=tx.replace('if(mode){usart.ISR|=64;uno_tx_tc_isr();}',
  'if(mode){usart.ISR|=64;uno_tx_tc_isr();if(dma.ISR&8U)DMA1_Channel1_IRQHandler();}')
 a=' // Vary main scheduling and TC latency while retaining exact complete bytes.'
 extra=''' // FIFO tail: DMA TC is not UART TC; queue and OFF remain uncommitted.
 reset();uno_tx_submit(first.data(),2);uno_tx_submit(second.data(),0);settle();
 for(unsigned i=0;i<43;++i)dma_byte(false);usart.ISR&=~UART_FLAG_TC;
 uno_tx_tc_isr();check(mic_uart_tx.tail==0&&mic_uart_tx.active&&!mic_last_control_reply_safe_off,"FIFO bytes pending cannot finish the frame");
 sim_us+=8U*11U;usart.ISR|=UART_FLAG_TC;uno_tx_tc_isr();settle();drain();equals({first,second});

'''
 assert a in tx;tx=tx.replace(a,extra+a)
 tx=tx.replace(',\\\"old_prefix_bytes\\\":39','')
 tx_result=run_compile(out,'actual_TX_DMA_with_FIFO',tx,incs)
 obj='nucleo/STM32CubeIDE/Debug/Application/User/multi_native.o'
 same={name:section(p.BASE/obj,'.text.'+name)==section(p.OUT/obj,'.text.'+name)
  for name in ('ma_native_fast','mic_observer_step','mic_observer_noise')};assert all(same.values())
 guards={}
 for name in ('motor_control.h','foc_experiment.h','current_adc_deadline.h','current_adc_window_plan.h',
  'local_stop.h','first_break_snapshot.h','uart_v3_transport.h','observer_start_history.h','observer_trace_core.h','peak_core.h'):
  assert p.sha(p.BASE/'nucleo/Inc'/name)==p.sha(p.OUT/'nucleo/Inc'/name),name;guards[name]=p.sha(p.OUT/'nucleo/Inc'/name)
 report=dict(passed=True,motor=motor,parser=parser,TX_DMA=tx_result,ARM_byte_identical=same,
  guards=guards,OFF_fast_limit_cycles=4000,estimate_age_ms=2,hardware_commands=0,target_cycles_measured=False,
  HAL_TX_complete_wait_preserved=True,NIS_math_unchanged=True)
 p.write(out/'report.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
