"""Archive simultaneous SD observations with GET only; no controller commands."""
import subprocess
import sys
import prepare_sd_dual_capture as package
import read_uart_resync_idle as reader

reader.C=package.OUT
reader.PAIR=package.NEW
if __name__=='__main__':
    if '--usb-transport' in sys.argv:
        sys.argv.remove('--usb-transport')
        subprocess.run(['adb','-s','3880458060','forward','tcp:18080','tcp:8080'],check=True,capture_output=True)
        reader.BASE='http://127.0.0.1:18080'
    raise SystemExit(reader.main())
