"""Read-only SD/UART evidence reader for the clean-confirmation pair."""
import read_uart_resync_idle as reader
import prepare_uart_clean_confirm as package
import subprocess
import sys
reader.C=package.OUT
reader.PAIR=package.NEW
if __name__=='__main__':
    if '--usb-transport' in sys.argv:
        sys.argv.remove('--usb-transport')
        subprocess.run(['adb','-s','3880458060','forward','tcp:18080','tcp:8080'],check=True,capture_output=True)
        reader.BASE='http://127.0.0.1:18080'
    raise SystemExit(reader.main())
