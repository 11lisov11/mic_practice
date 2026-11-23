"""Passive post-install image, SD configuration, HMI and calibration verifier."""
import verify_sd_dual_capture_install as verifier
import install_uart_clean_confirm_pair as install
install.configure()
verifier.install=install
if __name__=='__main__':raise SystemExit(verifier.main())
