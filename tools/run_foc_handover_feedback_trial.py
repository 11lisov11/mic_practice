"""Prepare or run the bounded I/f to FOC trial for the installed 2201/2202 pair."""

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import install_foc_handover_feedback_release as release
import run_nis_admission_paged_trial as trial
import seal_observer_nis_admission_release as pages


def verify_release():
    release.package_check()
    timing = release.read_json(release.OUT/'post_install_idle_r1/report.json')
    receipt = release.read_json(release.OUT/'installation_acceptance.json')
    assert receipt['pair'] == list(release.NEW) and receipt['installed']
    assert receipt['native_readback_verified'] and receipt['uno_readback_verified']
    assert receipt['calibration_unchanged'] and timing['CPU_qualified']
    assert 0 < timing['fast_cycles'] <= 4000 and timing['estimate_age_limit_ms'] == 2
    assert len(timing['native_rows']) >= 2 and all(
        row['fe_case']==64 and row['fe_fault']==0 and row['BKE'] and not row['MOE']
        for row in timing['native_rows'])
    clear_dir = release.OUT/'one_CLEAR_USB_r1'
    clear = release.read_json(clear_dir/'report.json')
    assert clear['CLEAR']==1 and clear['START']==clear['ARM']==0
    assert all(clear[key] for key in ('passed','UART_latch_cleared','Break_ready','RPC_stable'))
    archive = release.read_json(clear_dir/'preserved_before_sha256.json')
    for name in ('one_CLEAR_USB_r1','autonomous_before_FOC_r1','powered_before_FOC_r1','one_CLEAR_powered_r1'):
        folder = release.OUT/name
        if (folder/'sha256.json').is_file():
            seal = release.read_json(folder/'sha256.json')
            archive.update({(folder/file).relative_to(release.ROOT).as_posix():digest
                            for file,digest in seal.items()})
    release.release.base.verify_inventory(archive,release.ROOT)
    return release.ROOT,archive


def main():
    if sys.argv[1:] == ['--verify-only']:
        _, archive = verify_release()
        with tempfile.TemporaryDirectory(prefix='mic_foc_2202_') as directory:
            pages.release = SimpleNamespace(OUT=release.OUT, NEW=release.NEW, OLD=release.OLD,
                CURRENT=release.BASE/'replacement_ipm_FOC_5Hz_r1', read=release.read, write=release.write)
            result = pages.verify_page_contract(Path(directory))
        print(json.dumps({**result,'old_files_verified':len(archive),'stand_commands':0}))
        return 0
    if '--clear-once' in sys.argv:
        raise SystemExit('Use a separately authorized powered CLEAR if one is needed.')
    trial.release = release
    trial.verify_release = verify_release
    return trial.main()


if __name__ == '__main__':
    raise SystemExit(main())
