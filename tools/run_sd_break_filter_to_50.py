"""Existing bounded staged VF test on the exact BKIN filter pair."""
import prepare_sd_break_filter_fix as package
import run_uart_tx_dma_to_50 as tested

tested.common.PAIR = package.NEW

if __name__ == '__main__':
    raise SystemExit(tested.runner.main())
