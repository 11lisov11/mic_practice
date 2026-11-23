"""1611/1612 GET-only powerbank/OFF verification; no CLEAR/START/ARM/reset."""
import inspect
import prepare_observer_current_window as p
import verify_telemetry_deadline_autonomous as prior
def main():
    source=inspect.getsource(prior.main)
    source=source.replace("and rows[-1]['mc_good_cnt'] > rows[0]['mc_good_cnt'])",
        "and rows[-1]['uno_rx_count'] > rows[0]['uno_rx_count'])")
    source=source.replace("good_frame_increase=rows[-1]['mc_good_cnt']-rows[0]['mc_good_cnt']",
        "good_frame_increase=rows[-1]['uno_rx_count']-rows[0]['uno_rx_count']")
    source=source.replace("p.OUT/'preserved_capture_hashes.json'","p.OUT/'preserved_all_hashes.json'")
    old="manifest['installed'] and manifest['pair'] == list(p.NEW) and manifest['diagnostic_ADC_first_NIS_loss_trigger'] and manifest['OFF_bulk_round_robin'] and manifest['CPU_probe_budget_cycles'] == 4000 and manifest['estimate_limit_ms'] == 2"
    new="manifest['installed'] and manifest['pair'] == list(p.NEW) and manifest['control_and_observer_Q_R_math_unchanged'] and manifest['OFF_fast_budget_cycles'] == 4000 and manifest['estimate_age_limit_ms'] == 2 and manifest['raw_trip_A'] == 1.35 and manifest['ADC_UPDATE_limit_ticks'] == 2048"
    assert old in source;source=source.replace(old,new)
    # Empty recorders must be real, current schema3 receiver state, with the
    # exact installed release verified separately by the immutable source hashes.
    anchor="        report.update(checks=checks, passed=all(checks.values()), pair=list(p.NEW), samples=len(rows),"
    extra="""        latest=p.OUT/'one_CLEAR_after_RPC_recovery_r1'
        for name,digest in json.loads(p.read(latest/'acceptance_files_sha256.json')).items():
            assert p.sha(latest/name)==digest,name
        for name,digest in json.loads(p.read(p.OUT/'source_hashes.json')).items():
            assert p.sha(p.OUT/name)==digest,name
"""
    assert anchor in source;source=source.replace(anchor,extra+anchor)
    # Ordinary Linux boot may still be completing after the power-source change.
    source=source.replace("        rows = []\n        for i in range(20):", """        startup=[];deadline=time.monotonic()+45
        while True:
            try:
                initial=get('/api/status');assert initial.get('ok') is True
                break
            except Exception as error:
                startup.append(dict(error=repr(error),at=time.monotonic()))
                if time.monotonic()>=deadline:raise
                time.sleep(1)
        save('startup_attempts.json',startup)
        rows = []
        for i in range(20):""")
    scope=dict(prior.__dict__,p=p);exec(compile(source,__file__,'exec'),scope)
    return scope['main']()
if __name__=='__main__':raise SystemExit(main())
