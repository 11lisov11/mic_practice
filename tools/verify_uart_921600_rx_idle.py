"""Independent readback, OFF64 DWT and clean921600 idle qualification; no writes."""
import sys,types
import prepare_uart_921600_rx as p
from verify_start_history_idle import source as previous_source

def source():
 s=previous_source()
 replacements={
  'import prepare_start_history_release as p':'import prepare_uart_921600_rx as p',
  "p.OUT/f'installation_recipe_r1/release/nucleo_{p.NEW[1]}_expected_readback.bin'":"p.OUT/f'release/nucleo_{p.NEW[1]}_expected_readback.bin'",
  "p.OUT/f'installation_recipe_r1/release/nucleo_{p.NEW[1]}_start_history.elf'":"p.OUT/f'release/nucleo_{p.NEW[1]}_uart_rx_dma.elf'",
 }
 for a,b in replacements.items():assert a in s,a;s=s.replace(a,b)
 a="        assert install['passed'] and install['calibration_unchanged']"
 assert a in s;s=s.replace(a,"        assert install['native_readback_verified'] and install['uno_readback_verified'] and install['calibration_unchanged']\n        # Runtime qualification below is independent of the installer's short RPC wait.")
 a="            uart_brr=struct.unpack('<I',read(0x4001380c,4,f'USART1_BRR_{i}'))[0]"
 assert a in s
 s=s.replace(a,a+"""
            cr1,cr2,cr3=struct.unpack('<3I',read(0x40013800,12,f'USART1_CR_{i}'))
            dma=struct.unpack('<4I',read(0x4002001c,16,f'DMA1_ch2_{i}'))
            mux=struct.unpack('<I',read(0x40020804,4,f'DMAMUX1_ch1_{i}'))[0]
            ipr=read(0xe000e400,64,f'NVIC_priorities_{i}')
            assert cr1&(1<<29) and cr1&(1<<4) and not cr1&(1<<5),'FIFO/IDLE/RXNE ownership wrong'
            assert cr3&64 and cr3&1 and not cr3&((1<<12)|(1<<13)),'DMAR/error detection wrong'
            assert dma[0]==0x20af and dma[1]<=128 and dma[2]==0x40013824 and dma[3]==symbols['mic_uart_rx_dma']
            assert mux&127==24 and ipr[12]==ipr[37]==96 and ipr[18]==64
""")
 a="                UART_BRR=uart_brr,UART_configured_baud=uart_baud,"
 assert a in s
 s=s.replace(a,a+"\n                UART_CR1=cr1,UART_CR3=cr3,RX_DMA=list(dma),RX_DMAMUX=mux,IRQ_UART=ipr[37],IRQ_RX_DMA=ipr[12],IRQ_ADC=ipr[18],\n                RX_DMA_diagnostics=list(struct.unpack_from('<5I2H',ram,symbols['mic_uart_rx_dma_diag']-0x20000000)),")
 a="            assert row['BKE'] and not row['MOE'] and not row['running']"
 assert a in s;s=s.replace(a,a+"\n            assert row['RX_DMA_diagnostics'][2:4]==[0,0],'DMA gap/error'")
 a="            assert s['observer_trace']==dict(available=False,reason='not_received')"
 assert a in s;s=s.replace(a,"            assert s['uno_uart_fifo']==1 and s['uno_rx_hw_errors']==0 and s['uno_rx_hw_flags']==0\n"+a)
 return s

def main():
 s=source();compile(s,__file__,'exec')
 if '--verify-only' in sys.argv:print('OFF-only recipe verified; no hardware access');return 0
 module=types.ModuleType('uart_OFF_verifier');module.__file__=__file__
 exec(compile(s,__file__,'exec'),module.__dict__);return module.main()

if __name__=='__main__':raise SystemExit(main())
