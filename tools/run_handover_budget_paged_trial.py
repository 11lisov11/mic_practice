"""Prepare or run a bounded test of the installed 2107/2108 I/f-to-FOC startup."""

import sys

import build_foc_handover_budget_release as release
import run_nis_admission_paged_trial as trial


def verify_release():
    out = release.OUT
    manifest = release.read_json(out / 'release_manifest.json')
    install = release.read_json(out / 'installation_acceptance.json')
    timing_dir = out / 'post_install_idle_r1'
    timing = release.read_json(timing_dir / 'report.json')
    clear_dir = out / 'one_CLEAR_USB_r1'
    clear = release.read_json(clear_dir / 'report.json')
    assert install['pair'] == manifest['pair'] == list(release.NEW) and install['installed']
    assert install['native_readback_verified'] and install['uno_readback_verified'] and install['calibration_unchanged']
    assert timing['CPU_qualified'] and 0 < timing['fast_cycles'] <= 4000
    assert len(timing['native_rows']) >= 2 and all(
        row['fe_case'] == 64 and row['fe_fault'] == 0 and row['BKE'] and not row['MOE']
        for row in timing['native_rows'])
    assert (manifest['NIS'], manifest['OFF_fast_limit_cycles'], manifest['estimate_age_ms'],
            manifest['raw_current_trip_A'], manifest['ADC_UPDATE_ticks']) == (25, 4000, 2, 1.35, 2048)
    assert clear['CLEAR'] == 1 and clear['START'] == clear['ARM'] == 0
    assert clear['Break_ready'] and clear['RPC_stable']
    if not clear['UART_latch_cleared']:
        # The stopped USB attempt documented an actual undervoltage. This
        # historical outcome is evidence only. The powered runner still
        # requires freshly zero fault masks, clean transport and SD/BIE.
        ack = clear['clear_recovery']
        assert ack['result'] == 'MCSDK_ACK_REJECTED' and ack['current_faults_at_attempt'] == 4
        assert clear['after']['mc_fault_current_mask'] == 4 and clear['after']['bp_vdc'] < 20
    assert release.read_json(out / 'verification/report.json')['passed']
    release.verify_inventory(manifest['artifacts'], out)
    archive = release.read_json(clear_dir / 'preserved_before_sha256.json')
    for folder, seal in ((clear_dir, 'sha256.json'), (timing_dir, 'saved_files_sha256.json'),
                         (out / 'autonomous_before_FOC_r1', 'sha256.json'),
                         (out / 'powered_before_FOC_r1', 'sha256.json'),
                         (out / 'one_CLEAR_powered_r1', 'sha256.json')):
        if (folder / seal).exists():
            archive.update({(folder / name).relative_to(release.ROOT).as_posix(): sha
                            for name, sha in release.read_json(folder / seal).items()})
    release.verify_inventory(archive, release.ROOT)
    return release.ROOT, archive


if __name__ == '__main__':
    if '--clear-once' in sys.argv:
        raise SystemExit('Perform and verify a separately authorized powered CLEAR before invoking this runner.')
    trial.release = release
    trial.verify_release = verify_release
    raise SystemExit(trial.main())
