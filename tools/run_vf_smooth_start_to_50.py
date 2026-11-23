"""Existing bounded staged motor test for the exact smooth V/f pair; no run on import."""
import prepare_vf_smooth_start as package
import run_uart_tx_dma_to_50 as tested
tested.common.PAIR=package.NEW
tested.runner.PROFILE='vf-smooth-start-5-to-50'
if __name__=='__main__':raise SystemExit(tested.runner.main())
