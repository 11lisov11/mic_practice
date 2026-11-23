"""Prepare or run a single explicitly authorized FOC 5 Hz trial on 2103/2104."""

import run_nis_admission_paged_trial as paced
import build_foc_stationary_start_release as release


if __name__ == '__main__':
    paced.release = release
    raise SystemExit(paced.main())
