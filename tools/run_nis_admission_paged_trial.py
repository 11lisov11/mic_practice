"""Prepare one bounded FOC trial on 2101/2102. Use --verify-only on USB/OFF."""
import copy
import json
import runpy
import tempfile
from functools import partial
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import build_observer_nis_admission_release as release
import run_paged_FOC_trial as runner
from collect_foc_paged_after_stop import collect, require_stopped


def verify_release():
    out = release.OUT
    manifest = release.read_json(out/'release_manifest.json')
    installed = release.read_json(out/'installation_acceptance.json')
    timing = release.read_json(out/'post_install_idle_r1/report.json')
    cleared = release.read_json(out/'one_CLEAR_USB_r1/report.json')
    assert installed['pair']==manifest['pair']==list(release.NEW) and installed['installed']
    assert installed['native_readback_verified'] and installed['uno_readback_verified'] and installed['calibration_unchanged']
    assert timing['CPU_qualified'] and timing['OFF_fast_limit_cycles']==4000 and timing['estimate_age_limit_ms']==2
    assert 0<timing['fast_cycles']<=4000
    assert (manifest['NIS'],manifest['OFF_fast_limit_cycles'],manifest['estimate_age_ms'],
            manifest['raw_current_trip_A'],manifest['ADC_UPDATE_ticks'])==(25,4000,2,1.35,2048)
    assert cleared['CLEAR']==1 and cleared['START']==cleared['ARM']==0
    assert all(cleared[k] for k in ('UART_latch_cleared','Break_ready','RPC_stable','passed'))
    assert release.read_json(out/'verification/report.json')['passed']
    release.verify_inventory(manifest['artifacts'], out)
    clear_dir = out/'one_CLEAR_USB_r1'
    clear_seal = release.read_json(clear_dir/'sha256.json')
    release.verify_inventory(clear_seal, clear_dir)
    archives = release.read_json(clear_dir/'preserved_before_sha256.json')
    archives.update({(clear_dir/name).relative_to(release.ROOT).as_posix():h for name,h in clear_seal.items()})
    for name in ('autonomous_before_FOC_r1','powered_before_FOC_r1'):
        folder = out/name
        if (folder/'sha256.json').exists():
            seal = release.read_json(folder/'sha256.json')
            archives.update({(folder/file).relative_to(release.ROOT).as_posix():h for file,h in seal.items()})
    release.verify_inventory(archives, release.ROOT)
    return release.ROOT,archives


def test_early_page_path():
    """Replay the real page bodies with simulated early-stop metadata. No IO to boards."""
    out = release.OUT
    original = release.read_json(out/'one_CLEAR_USB_r1/after.json')
    stop = dict(original,run_id=1,run_start_ms=3010,run_stop_ms=3577,run_reason=2,
                run_limit_ms=5000,run_elapsed_ms=567,mc_adc_peak_complete=1,mc_observer_trace_complete=1)
    require_stopped(stop,stop,pair=release.NEW,allow_short_stop=True)
    for altered in (dict(pwm=1),dict(hmi_hv_armed=1),dict(run_id=2),dict(run_stop_ms=0),
                    dict(mc_age_ms=300),dict(run_elapsed_ms=568),dict(linux_boot_id='different')):
        try:
            require_stopped(dict(stop,**altered),stop,pair=release.NEW,allow_short_stop=True)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Early collection must reject '+str(altered))
    try:
        require_stopped(stop,stop,pair=release.NEW)
    except RuntimeError:
        pass
    else:
        raise AssertionError('The legacy collector admitted an early stop')
    timed = dict(stop,run_elapsed_ms=5000,run_reason=1,run_stop_ms=8010)
    require_stopped(timed,timed,pair=release.NEW)
    hmi = runpy.run_path(str(out/'web_hmi/server.py'))
    records = {'adc':(out/'verification/ADC_peak.bin').read_bytes(),
               'observer':(out/'verification/observer_trace.bin').read_bytes()}
    clock = 0.
    count = 0
    def sleep(seconds):
        nonlocal clock
        clock += seconds
    def get(route):
        nonlocal clock,count
        clock += .28
        if route=='/api/status':
            count+=1
            return {'ok':True,'data':dict(copy.deepcopy(stop),
                mc_good_cnt=stop['mc_good_cnt']+count, uno_rx_count=stop['uno_rx_count']+count)}
        url = urlparse(route)
        assert url.path=='/api/capture-page'
        query = parse_qs(url.query); kind=query['kind'][0]; page=int(query['page'][0])
        part,size = hmi['CAPTURE_PAGES'][kind]
        raw = records[kind]; crc=int.from_bytes(raw[60:64],'little')
        reply = f'CP {part} {page} {size} {release.NEW[1]} {crc} {raw[192*page:192*(page+1)].hex()}'
        return {'ok':True,'data':hmi['parse_capture_page'](reply,part,page,size)}
    with tempfile.TemporaryDirectory(prefix='mic_nis_early_') as tmp:
        capture = Path(tmp)/'capture'
        result = collect(get,hmi['receive_capture_pages'],stop,capture,monitor_samples=4,
                         clock=lambda:clock,sleep=sleep,pair=release.NEW,allow_short_stop=True)
        assert result['passed'] and result['run_elapsed_ms']==567 and len(result['records'])==2,result
        assert (capture/'ADC_peak.bin').read_bytes()==records['adc']
        assert (capture/'observer_trace.bin').read_bytes()==records['observer']
    return {'early_stop_pages_verified':16,'cross_run_or_active_rejections':8,
            '5000ms_legacy_still_accepted':True,'stand_commands':0}


def main():
    import sys

    if sys.argv[1:]==['--verify-only']:
        _, archives = verify_release()
        print(json.dumps({**test_early_page_path(),'old_files_verified':len(archives),'verified':True}))
        return 0
    runner.OUT=release.OUT
    runner.PAIR=release.NEW
    runner.verify_release=verify_release
    runner.collect=partial(collect,pair=release.NEW,allow_short_stop=True)
    runtime=runner.supervised.driver.trial
    runtime.COLLECT_PAGES_ON_EARLY_STOP=True
    runtime.REQUIRE_CLEAR_ACK=True
    try:
        return runner.main(permit_clear_option=True)
    finally:
        runtime.COLLECT_PAGES_ON_EARLY_STOP=False
        runtime.REQUIRE_CLEAR_ACK=False


if __name__=='__main__':
    raise SystemExit(main())
