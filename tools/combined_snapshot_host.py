"""Same bounded combined runner, selecting the coherent snapshot image2802."""
import combined_io_host as run
from prepare_combined_snapshot_fix import OUT,OLD,BUILD
run.PACKAGE=OUT;run.OLD=OLD;run.BUILD=BUILD
if __name__=='__main__':raise SystemExit(run.main())
