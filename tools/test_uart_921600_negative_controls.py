"""PC-only negative controls: prove the tests catch removed race/loss guards."""
import json,shutil,subprocess
import prepare_uart_921600_rx as p
def main():
 out=p.OUT/'verification/negative_controls';out.mkdir(parents=True,exist_ok=False);results=[]
 native=p.read(p.OUT/'nucleo/Inc/uart_rx_dma_native.inc');uno=p.read(p.OUT/'UNOQ_MOTOR/nucleo_buffered_serial.h')
 start=native.index(' /* DMA can run while');end=native.index('\n}\nvoid DMA1_Channel2',start)
 variants=[('DMA_postcopy_guard_removed','native',native[:start]+native[end:]),
  ('DMA_wrong_GIF_ack','native',native.replace('DMA1->IFCR=flags;','DMA1->IFCR=flags|0x10U;')),
  ('Uno_empty_FIFO_false_fault','uno',uno.replace('if(batch==32U&&(regs()->ISR&USART_ISR_RXNE_RXFNE))','if(regs()->ISR&USART_ISR_RXNE_RXFNE)')),
  ('Uno_vendor_ISR_reintroduced','uno',uno.replace('uint32_t started=k_cycle_get_32();unsigned batch=0;',
   'arduino::ZephyrSerial::IrqHandler();uint32_t started=k_cycle_get_32();unsigned batch=0;'))]
 for name,target,header in variants:
  folder=out/name;folder.mkdir();cpp=folder/'test.cpp';exe=cpp.with_suffix('.exe')
  if target=='native':
   assert header!=native;p.write(folder/'uart_rx_dma_native.inc',header)
   p.write(cpp,p.read(p.OUT/'verification/native_RX_r4/actual_dma.cpp'))
   incs=[p.OUT/'nucleo/Inc']
  else:
   assert header!=uno;p.write(folder/'nucleo_buffered_serial.h',header)
   p.write(cpp,p.read(p.OUT/'verification/Uno_RX_r3/actual_Uno.cpp'))
   incs=[p.OUT/'verification/Uno_RX_r3/stubs',p.OUT/'UNOQ_MOTOR']
  r=subprocess.run([shutil.which('g++'),'-O2','-std=c++17',*sum((['-I',str(f)] for f in incs),[]),str(cpp),'-o',str(exe)],capture_output=True,text=True)
  p.write(folder/'build.log',r.stdout+r.stderr);r.check_returncode()
  r=subprocess.run([str(exe)],capture_output=True,text=True);p.write(folder/'run.log',r.stdout+r.stderr)
  assert r.returncode!=0,'Mutation survived: '+name
  results.append(dict(name=name,rejected=True,exit_code=r.returncode))
 report=dict(passed=True,controls=results,hardware_commands=0)
 p.write(out/'report.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
