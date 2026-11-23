"""USB/ADB transport for the verified smooth V/f pair; no runs or CLEAR."""
import install_sd_break_filter_usb_pair as transport
import install_vf_smooth_start_pair as install
install.configure();transport.install=install
if __name__=='__main__':raise SystemExit(transport.main())
