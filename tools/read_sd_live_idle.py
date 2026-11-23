"""Read/archive SD diagnostic firmware. GET only, no control or calibration writes."""
import sys
from pathlib import Path
import read_uart_resync_idle as reader

reader.C=Path(__file__).resolve().parents[1]/'artifacts/live_bench_20261018/sd_live_diagnostics_r1'
reader.PAIR=(2026101809,2026101808)
if '--existing-uart-pair' in sys.argv:
    # Read the separately deployed new HMI while the old MCU pair still runs.
    sys.argv.remove('--existing-uart-pair')
    reader.PAIR=(2026101807,2026101806)

if __name__=='__main__':
    raise SystemExit(reader.main())
