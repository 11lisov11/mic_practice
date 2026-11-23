"""Bounded2792 computation diagnostic using the same verified host runner."""
import run_no_switch_diag as run
import no_switch_diag_snapshot_io as io
run.PACKAGE=io.PACKAGE
run.Probe=io.Probe
run.decode=io.decode
run.eligible=io.eligible
run.read_report=io.read_report
if __name__=='__main__':raise SystemExit(run.main())
