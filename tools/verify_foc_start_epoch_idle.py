"""OFF-only timing, zero and communication check; never START or CLEAR."""
import verify_estimated_foc_idle as verify
import prepare_foc_start_epoch_fix as package
verify.p=package
if __name__=='__main__':raise SystemExit(verify.main())
