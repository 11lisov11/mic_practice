"""Use proven USB tunnel/readback installer for the UART confirmation update."""
import install_sd_break_filter_usb_pair as transport
import install_uart_clean_confirm_pair as install
install.configure()
transport.install=install
if __name__=='__main__':raise SystemExit(transport.main())
