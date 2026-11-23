"""1605/1606 GET-only autonomous/powered preflight; never CLEAR or START."""
import prepare_clear_recovery as package
import verify_telemetry_deadline_autonomous as checker

checker.p=package

if __name__=='__main__':raise SystemExit(checker.main())
