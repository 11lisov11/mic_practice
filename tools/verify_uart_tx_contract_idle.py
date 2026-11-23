"""OFF-only1807/1806 qualification using exact installed images; no motor calls."""
import types
import prepare_uart_tx_contract_fix as p
from verify_uart_921600_rx_idle import source

def main():
 s=source().replace('import prepare_uart_921600_rx as p','import prepare_uart_tx_contract_fix as p')
 p.write(p.OUT/'verification/OFF_qualification_recipe.py',s)
 m=types.ModuleType('tx_contract_OFF');m.__file__=__file__
 exec(compile(s,__file__,'exec'),m.__dict__);return m.main()

if __name__=='__main__':raise SystemExit(main())
