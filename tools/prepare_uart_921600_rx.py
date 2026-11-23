"""Offline1805/1806: RX DMA on G431, dedicated FIFO ISR on Uno; no device IO."""
import hashlib,json,os,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261118/observer_start_history_r1'
OUT=ROOT/'artifacts/live_bench_20261118/uart_921600_rx_r1'
NEW=(2026111805,2026111806)
def read(p):return Path(p).read_text(encoding='utf-8-sig')
def write(p,s):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def once(s,a,b):
 assert s.count(a)==1,(a[:100],s.count(a));return s.replace(a,b,1)
def main():
 assert not OUT.exists(),'Never replace packages or captures'
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  def copy(src,dst):
   parts=Path(src).relative_to(BASE/folder).parts
   if folder=='libraries' or folder=='nucleo' and parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):
    os.link(src,dst);return dst
   return shutil.copy2(src,dst)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=copy,
   ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log','backups'))
 preserved={}
 for f in BASE.rglob('*'):
  if f.is_file() and '__pycache__' not in f.parts:preserved[f.relative_to(ROOT).as_posix()]=sha(f)
 write(OUT/'preserved_inputs_sha256.json',json.dumps(preserved,indent=2)+'\n')
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    a=read(f);b=a.replace('2026111803',str(NEW[0])).replace('2026111804',str(NEW[1]))
    if a!=b:write(f,b)
 shutil.copy2(ROOT/'tools/uart_rx_dma_core.h',OUT/'nucleo/Inc/uart_rx_dma_core.h')
 shutil.copy2(ROOT/'tools/uart_dma_native.inc',OUT/'nucleo/Inc/uart_rx_dma_native.inc')
 shutil.copy2(ROOT/'tools/nucleo_fifo_serial.h',OUT/'UNOQ_MOTOR/nucleo_buffered_serial.h')
 path=OUT/'nucleo/Src/main.c';s=read(path)
 start=s.index('/* Hardware FIFO is disabled:');end=s.index('static uint32_t uno_u32le',start)
 s=s[:start]+'#include "uart_rx_dma_native.inc"\n\n'+s[end:]
 s=s.replace('HAL_NVIC_DisableIRQ(USART1_IRQn);','HAL_NVIC_DisableIRQ(USART1_IRQn);\n  HAL_NVIC_DisableIRQ(DMA1_Channel2_IRQn);')
 s=s.replace('HAL_NVIC_EnableIRQ(USART1_IRQn);','HAL_NVIC_EnableIRQ(DMA1_Channel2_IRQn);\n  HAL_NVIC_EnableIRQ(USART1_IRQn);')
 s=s.replace('Mask only USART1; ADC/TIM protection IRQs stay enabled.','Mask UART RX owners only; ADC/TIM protection IRQs stay enabled.')
 s=s.replace('one USART-only section.','one UART-owner-only section.')
 s=once(s,'HAL_UARTEx_DisableFifoMode(&huart1) != HAL_OK',
  'HAL_UARTEx_SetTxFifoThreshold(&huart1, UART_TXFIFO_THRESHOLD_1_8) != HAL_OK ||\n      HAL_UARTEx_SetRxFifoThreshold(&huart1, UART_RXFIFO_THRESHOLD_1_8) != HAL_OK ||\n      HAL_UARTEx_EnableFifoMode(&huart1) != HAL_OK')
 s=once(s,'  uno_tx_init();','  uno_tx_init();\n  uno_rx_dma_init();')
 s=once(s,'__HAL_UART_ENABLE_IT(&huart1, UART_IT_RXNE);','__HAL_UART_ENABLE_IT(&huart1, UART_IT_IDLE); /* DMA owns RDR; never RXNE IRQ. */')
 s=s.replace('RX stays IRQ.','RX owns DMA1 channel2 with IDLE/HT/TC publication.')
 write(path,s)
 # Small read-only additions, retain all existing field names/counters.
 path=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(path)
 a='  s += " uno_rx_pending="; s += String((unsigned long)rx_stats.pending);'
 b=a+'''\n  s += " uno_uart_fifo=";s += String((unsigned long)rx_stats.fifo_enabled);
  s += " uno_uart_rx_batch_max=";s += String((unsigned long)rx_stats.max_batch);
  s += " uno_uart_irq_cycles_max=";s += String((unsigned long)rx_stats.max_irq_cycles);
  s += " uno_uart_lock_cycles_max=";s += String((unsigned long)rx_stats.max_lock_cycles);
  s += " uno_uart_tx_rejected=";s += String((unsigned long)rx_stats.tx_rejected);'''
 write(path,once(s,a,b))
 path=OUT/'web_hmi/server.py';s=read(path)
 a='"uno_rx_pending",';assert s.count(a)==2
 fields='"uno_uart_fifo", "uno_uart_rx_batch_max", "uno_uart_irq_cycles_max", "uno_uart_lock_cycles_max", "uno_uart_tx_rejected"'
 write(path,s.replace(a,a+' '+fields+','))
 # No STM32 kernel rebuild or unrelated DMA ownership/interrupt-priority edits.
 for rel in ('nucleo/Src/multi_native.c','nucleo/Src/current_shunt.c','nucleo/Src/stm32g4xx_mc_it.c'):
  assert read(BASE/rel).replace('2026111803',str(NEW[0])).replace('2026111804',str(NEW[1]))==read(OUT/rel),rel
 for name in ('motor_control.h','observer_pair_noise.h','foc_experiment.h','uart_v3_transport.h','current_adc_deadline.h','local_stop.h','observer_trace_core.h','observer_start_history.h','peak_core.h'):
  assert sha(BASE/'nucleo/Inc'/name)==sha(OUT/'nucleo/Inc'/name),name
 report=dict(prepared=True,pair=NEW,built=False,installed=False,hardware_commands=0,
  uart_baud=921600,native_RX='DMA1ch2 ring128 + FIFO8 + IDLE/HT/TC',
  Uno_RX='FIFO8 + dedicated bounded ISR; no vendor semaphore RX/TX callbacks',
  no_motor_priority_or_IRQ_enable_changes=True,OFF_fast_limit_cycles=4000,estimate_age_ms=2,
  receive_error_handling='G431 DMA cannot attribute NE per byte: any NE/PE/FE/ORE trips existing UART fault; Uno losses latch until boot',
  DMA_async_API_NOT_enabled_in_Uno_kernel=True,existing_native_TX_DMA_and_TC_wait_unchanged=True,
  old_records_preserved=len(preserved),target_timing_measured=False,UART_hardware_qualified=False)
 write(OUT/'preparation.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
