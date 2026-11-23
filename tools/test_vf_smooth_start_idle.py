"""Exercise frequency settings on the new pair, continuously SAFE/PWM0."""
import test_idle_frequency_commands as test
import prepare_vf_smooth_start as package
test.PAIR=package.NEW
if __name__=='__main__':raise SystemExit(test.main())
