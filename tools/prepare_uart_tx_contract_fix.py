"""Uno1807 only: exact installed Zephyr TX API uses TC, not TXE. No board IO."""
import json,shutil,os
from pathlib import Path
import prepare_uart_921600_rx as old
ROOT=old.ROOT
BASE=old.OUT
OUT=ROOT/'artifacts/live_bench_20261118/uart_921600_tx_contract_r1'
NEW=(2026111807,2026111806)
read,write,sha=old.read,old.write,old.sha

def main():
 assert not OUT.exists()
 for folder in ('UNOQ_MOTOR','web_hmi','libraries'):
  shutil.copytree(BASE/folder,OUT/folder,copy_function=os.link if folder=='libraries' else shutil.copy2,
   ignore=shutil.ignore_patterns('__pycache__','*.pyc','backups'))
 for folder in ('UNOQ_MOTOR','web_hmi'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    s=read(f);t=s.replace('2026111805','2026111807')
    if s!=t:write(f,t)
 path=OUT/'UNOQ_MOTOR/nucleo_buffered_serial.h';s=read(path)
 s=s.replace('uart_irq_tx_enable(uart)','LL_USART_EnableIT_TXE_TXFNF(regs())')
 s=s.replace('uart_irq_tx_disable(uart)','LL_USART_DisableIT_TXE_TXFNF(regs())')
 a='    uart_irq_rx_disable(uart);LL_USART_DisableIT_TXE_TXFNF(regs());uart_irq_err_disable(uart);'
 assert a in s;s=s.replace(a,a+'\n    LL_USART_DisableIT_TC(regs()); /* Installed Zephyr TX API controls TC, not TXE. */')
 assert 'uart_irq_tx_' not in s
 write(path,s)
 (OUT/'release').mkdir()
 m=json.loads(read(BASE/'release_manifest.json'))
 for rel,h in m['artifacts'].items():
  if '/nucleo_' in rel:assert sha(BASE/rel)==h;shutil.copy2(BASE/rel,OUT/rel)
 write(OUT/'preserved_inputs_sha256.json',json.dumps({f.relative_to(ROOT).as_posix():sha(f) for f in BASE.rglob('*') if f.is_file() and '__pycache__' not in f.parts},indent=2)+'\n')
 write(OUT/'preparation.json',json.dumps(dict(pair=NEW,native_image_unchanged=True,
  correction='LL TXE/TXFNF IRQ ownership; explicitly disable TC IRQ; compiled kernel API toggles TC bit6',
  OFF_fast_limit_cycles=4000,estimate_age_ms=2,START=0,CLEAR=0,ARM=0),indent=2)+'\n')
 print('Prepared Uno1807, exact native1806 retained; no board access')

if __name__=='__main__':main()
