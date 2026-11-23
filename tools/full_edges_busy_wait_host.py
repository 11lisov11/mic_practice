import full_mcsdk_edges_host as run
from prepare_full_edges_busy_wait import OUT,BUILD
run.PACKAGE=OUT;run.BUILD=BUILD
if __name__=='__main__':raise SystemExit(run.main())
