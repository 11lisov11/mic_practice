"""Reuse verified USB/ADB and pinned SSH transport for the dual SD update."""
import install_sd_break_filter_usb_pair as transport
import install_sd_dual_capture_pair as install
install.configure()
transport.install=install
if __name__=='__main__':raise SystemExit(transport.main())
