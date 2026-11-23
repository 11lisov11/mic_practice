"""One protected first FOC5Hz5s run on repeat-Break pair; no implicit CLEAR."""
import json,sys
from pathlib import Path
import run_repeat_break_foc_runtime as trial
import run_foc_boot_capture_trial as boot
import prepare_repeat_break_capture as package
boot.package=package
assert trial.PAIR==package.NEW
if __name__=='__main__':
 rc=trial.main()
 out=Path(sys.argv[sys.argv.index('--outdir')+1]).resolve()
 verified=boot.audit_saved_trial(out)
 print(json.dumps(dict(saved_boot_audit_passed=json.loads((out/'boot_evidence_audit.json').read_text(encoding='utf-8'))['passed'],motor_commands_added_by_audit=0,passed=rc==0 and verified)))
 raise SystemExit(0 if rc==0 and verified else 1)
