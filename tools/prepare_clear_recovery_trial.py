"""Validate installed1605/1606 test routing offline, preserve all captures."""
import ast,json
import prepare_clear_recovery as p


def main():
    out=p.OUT/'FOC_trial_preparation_r1';out.mkdir(exist_ok=False)
    m=json.loads(p.read(p.OUT/'manifest.json'))
    assert m['installed'] and m['OFF_CPU_qualified'] and m['measured_OFF_fast_cycles']<=4000
    assert m['pair']==list(p.NEW) and m['CPU_probe_budget_cycles']==4000 and m['estimate_limit_ms']==2
    assert m['trip_A']==1.35 and m['ADC_guard_ticks']==2048 and not m['thresholds_changed']
    assert m['diagnostic_ADC_first_NIS_loss_trigger'] and m['runlimit_ms']==5000 and m['frequency_max_hz']==5
    for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert p.sha(p.OUT/rel)==h,rel
    for rel,h in m['artifacts'].items():assert p.sha(p.OUT/rel)==h,rel
    preserved=json.loads(p.read(p.OUT/'one_CLEAR_idle_r1/preserved_before_sha256.json'))
    for f in (p.OUT/'one_CLEAR_idle_r1').rglob('*'):
        if f.is_file():preserved[f.relative_to(p.ROOT).as_posix()]=p.sha(f)
    for rel,h in preserved.items():assert p.sha(p.ROOT/rel)==h,rel
    p.write(out/'preserved_before_sha256.json',json.dumps(preserved,indent=2)+'\n')
    # Importing wrappers must not open a network connection or issue a command.
    import socket
    from unittest.mock import patch
    with patch.object(socket.socket,'connect',side_effect=AssertionError('Offline preparation forbids network')):
        import run_clear_recovery_trial as t
        import verify_clear_recovery_autonomous as a
        assert t.runner.p is p and t.runner.driver.package is p
        assert t.runner.driver.trial.PAIR==p.NEW and t.runner.driver.boot.package is p
        assert t.runner.driver.capture.package is p and a.checker.p is p
        old=json.loads(p.read(p.BASE/'powered_FOC_NIS_5Hz_r1/selection_before.json'))['data']
        assert not t.runner.driver.trial.profile_config(old),'Wrong firmware pair accepted'
        record=(p.BASE/'powered_before_NIS_FOC_r1/SD_before_START.bin').read_bytes()
        assert len(record)==320  # Only local evidence; never delete frozen SD.
    src=p.read(p.ROOT/'tools/run_observer_input_epoch_runtime.py')
    for needle in ("'SET RUNLIMIT 5'","'SET FREQ 5'","'runlimit_s':5.0","One CLEAR did not restore protections; no retry"):
        assert needle in src,needle
    for needle in ('<=4000','<=85000','0<=s.get(\'mc_age_ms\',9999)<300'):
        assert needle in src,needle
    helper=p.read(p.ROOT/'tools/run_telemetry_deadline_trial.py')
    assert 'guard=prepare_rpc_guard' in helper and 'driver.trial.RPC_GUARD=guard' in helper
    for f in ('run_clear_recovery_trial.py','verify_clear_recovery_autonomous.py'):
        ast.parse(p.read(p.ROOT/'tools'/f))
    report=dict(passed=True,pair=list(p.NEW),installed_images_verified=True,
        OFF_CPU_previously_measured=3618,CPU_budget=4000,estimate_limit_ms=2,
        native_NIS_ADC_trigger=True,bounded_FOC_Hz=5,runlimit_ms=5000,
        release_observer_decoder_bound=True,single_RPC_baseline=True,
        repeat_CLEAR_and_START_not_automatic=True,preserved_files_verified=len(preserved),
        hardware_commands=0,START=0,CLEAR=0,ARM=0,RESET=0,flash=0,
        scope='Offline test preparation, no current powered readiness claim')
    p.write(out/'report.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
