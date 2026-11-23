"""Strict OFF acceptance: fresh boot/Break epochs, UART and actual stack waterline."""
import types
import prepare_boot_stack_integrity as p
from verify_uart_921600_rx_idle import source

def main():
 s=source().replace('import prepare_uart_921600_rx as p','import prepare_boot_stack_integrity as p')
 s=s.replace("nucleo_{p.NEW[1]}_uart_rx_dma.elf","nucleo_{p.NEW[1]}_stack_guard.elf")
 a="            assert row['BKE'] and not row['MOE'] and not row['running']"
 assert a in s
 s=s.replace(a,"""
            stack_begin=symbols['__StackLimit']-0x20000000
            unused=0
            for offset in range(stack_begin,32768,4):
                if struct.unpack_from('<I',ram,offset)[0]!=0xa5a55a5a:break
                unused+=4
            row['unused_stack_bytes']=unused
            row['used_stack_high_water_bytes']=4096-unused
            row['stack_guard_failed']=val('mic_stack_guard_failed')
            assert row['stack_guard_failed']==0 and unused>=512
"""+a)
 s=s.replace('for i in range(12):','for i in range(60):')
 a="            assert s['repeat_break']['available'] and s['repeat_break']['fresh']"
 assert a in s;s=s.replace(a,a+"\n            assert s['native_boot']['fresh'] and s['repeat_break']['epoch_matches']")
 # Preserve exact recipe that actually runs; never relax1500ms TTL/CRC/epoch.
 p.write(p.OUT/'verification/OFF_qualification_recipe.py',s)
 m=types.ModuleType('stack_OFF_verifier');m.__file__=__file__
 exec(compile(s,__file__,'exec'),m.__dict__);return m.main()

if __name__=='__main__':raise SystemExit(main())
