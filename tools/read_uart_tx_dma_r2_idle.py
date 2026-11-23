"""Read-only archive of final TX-DMA pair 1813/1812."""
from pathlib import Path
import read_uart_resync_idle as reader
reader.C=Path(__file__).resolve().parents[1]/'artifacts/live_bench_20261018/uart_tx_dma_fix_r2'
reader.PAIR=(2026101813,2026101812)
if __name__=='__main__':raise SystemExit(reader.main())
