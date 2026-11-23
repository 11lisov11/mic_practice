"""Passive flash/register/HMI/calibration verification after smooth V/f install."""
import verify_sd_dual_capture_install as verifier
import install_vf_smooth_start_pair as install
install.configure();verifier.install=install
if __name__=='__main__':raise SystemExit(verifier.main())
