"""Read-only SD/UART archive for the smooth V/f pair."""
import subprocess
import sys
import read_uart_resync_idle as reader
import prepare_vf_smooth_start as package
reader.C=package.OUT;reader.PAIR=package.NEW
if __name__=='__main__':
    if '--usb-transport' in sys.argv:
        sys.argv.remove('--usb-transport')
        subprocess.run(['adb','-s','3880458060','forward','tcp:18080','tcp:8080'],check=True,capture_output=True)
        reader.BASE='http://127.0.0.1:18080'
    raise SystemExit(reader.main())
