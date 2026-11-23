import verify_foc_runtime_idle as check
import prepare_foc_observer_schedule_fix as package
check.package = package
check.verify.p = package
if __name__ == '__main__':
    raise SystemExit(check.main())
