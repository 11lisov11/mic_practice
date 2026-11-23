"""Read-only archive for the BKIN filter pair; no START/CLEAR/reset/flash."""
import prepare_sd_break_filter_fix as package
import read_uart_resync_idle as reader
import subprocess
import sys

reader.C = package.OUT
reader.PAIR = package.NEW

if __name__ == '__main__':
    if '--usb-transport' in sys.argv:
        sys.argv.remove('--usb-transport')
        subprocess.run(['adb', '-s', '3880458060', 'forward', 'tcp:18080', 'tcp:8080'],
                       check=True, capture_output=True)
        reader.BASE = 'http://127.0.0.1:18080'
    raise SystemExit(reader.main())
