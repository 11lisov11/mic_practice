"""Read/archive current TX-DMA pair. GET only, no actuation."""
from pathlib import Path
import read_uart_resync_idle as reader
reader.C=Path(__file__).resolve().parents[1]/'artifacts/live_bench_20261018/uart_tx_dma_fix_r1'
reader.PAIR=(2026101811,2026101810)
if __name__=='__main__':raise SystemExit(reader.main())
