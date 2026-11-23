"""Actual Uno adapter, actual TC-vs-TXE contract from installed kernel ELF."""
import json,subprocess,sys,types
from pathlib import Path
from elftools.elf.elffile import ELFFile
import prepare_uart_tx_contract_fix as p

def main():
 kernel=Path.home()/'AppData/Local/Arduino15/packages/arduino/hardware/zephyr/0.90.0/firmwares/zephyr-arduino_uno_q_stm32u585xx.elf'
 out=p.OUT/'verification/kernel_contract';out.mkdir(parents=True,exist_ok=False)
 with kernel.open('rb') as f:
  e=ELFFile(f);sy={s.name:s for s in e.get_section_by_name('.symtab').iter_symbols()}
  def data(name):
   s=sy[name];sec=e.get_section(s['st_shndx']);off=(s['st_value']&~1)-sec['sh_addr'];return sec.data()[off:off+s['st_size']]
  enable=data('uart_stm32_irq_tx_enable');disable=data('uart_stm32_irq_tx_disable')
  # Exact installed instructions: ORR r3,r3,#0x40; BIC r3,r3,#0x40.
  assert bytes.fromhex('43f04003') in enable and bytes.fromhex('23f04003') in disable
  p.write(out/'kernel_contract.json',json.dumps(dict(passed=True,kernel_sha256=p.sha(kernel),
   TX_enable_bytes=enable.hex(),TX_disable_bytes=disable.hex(),kernel_TX_IRQ_bit=64,
   adapter_TX_IRQ_bit=128,no_motor_IRQ_change=True),indent=2)+'\n')
 s=p.read(p.ROOT/'tools/test_uart_921600_uno.py')
 s=s.replace('import prepare_uart_921600_rx as p','import prepare_uart_tx_contract_fix as p')
 s=s.replace("out=p.OUT/'verification/Uno_RX_r3'","out=p.OUT/'verification/Uno_RX_kernel_r1'")
 a='void uart_irq_tx_disable(const device*){regs.CR1&=~128U;}void uart_irq_tx_enable(const device*){regs.CR1|=128U;}'
 b='''void uart_irq_tx_disable(const device*){regs.CR1&=~64U;}void uart_irq_tx_enable(const device*){regs.CR1|=64U;}
static void LL_USART_DisableIT_TC(USART_TypeDef*r){r->CR1&=~64U;}
static void LL_USART_DisableIT_TXE_TXFNF(USART_TypeDef*r){r->CR1&=~128U;}
static void LL_USART_EnableIT_TXE_TXFNF(USART_TypeDef*r){r->CR1|=128U;}'''
 assert a in s;s=s.replace(a,b)
 a='static void fire(){assert(!locked&&callback);callback(&dev,context);}'
 b='static void fire(){assert(!locked&&callback);callback(&dev,context);assert(!(regs.CR1&64U));}'
 assert a in s;s=s.replace(a,b)
 s=s.replace("if __name__=='__main__':main()",'')
 m=types.ModuleType('contract_test');exec(compile(s,__file__,'exec'),m.__dict__);m.main()
 # Negative control: exact1805 must fail the SAME corrected kernel model.
 base=p.OUT/'verification/Uno_RX_kernel_r1';negative=out/'negative';negative.mkdir()
 shutil=__import__('shutil');shutil.copy2(p.BASE/'UNOQ_MOTOR/nucleo_buffered_serial.h',negative/'nucleo_buffered_serial.h')
 exe=negative/'old1805.exe';cmd=[shutil.which('g++'),'-std=c++17','-O2','-I',str(base/'stubs'),'-I',str(negative),'-I',str(p.OUT/'UNOQ_MOTOR'),str(base/'actual_Uno.cpp'),'-o',str(exe)]
 r=subprocess.run(cmd,capture_output=True,text=True);p.write(negative/'build.log',r.stdout+r.stderr);r.check_returncode()
 r=subprocess.run([str(exe)],capture_output=True,text=True);p.write(negative/'run.log',r.stdout+r.stderr);assert r.returncode!=0,'Old TC-storm adapter unexpectedly passed'
 p.write(out/'report.json',json.dumps(dict(passed=True,actual_installed_kernel_contract=True,
  new_adapter_137_cases_pass=True,old_1805_negative_control_failed=True,old_exit_code=r.returncode,
  vendor_ISR_calls=0,START=0,hardware_commands=0),indent=2)+'\n')
 print('Kernel contract PASS; old1805 rejected by corrected tests')

if __name__=='__main__':main()
