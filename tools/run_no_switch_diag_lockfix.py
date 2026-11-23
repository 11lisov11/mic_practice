"""Use the tested bounded host runner with the sealed2791 report identity."""
import run_no_switch_diag as run
import no_switch_diag_lockfix_io as io
run.PACKAGE=io.PACKAGE
run.Probe=io.Probe
run.decode=io.decode
run.eligible=io.eligible
run.read_report=io.read_report
if __name__=='__main__':raise SystemExit(run.main())
