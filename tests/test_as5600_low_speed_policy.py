import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from run_as5600_low_speed import EncoderPolicy,sensor_healthy,summarize


def sample():
    return dict(enc_source='uno_q_i2c2',enc_bus_ok=1,enc_ok=1,enc_init_error=0,
        enc_io_error=0,enc_age_ms=2,enc_reads=200,enc_errors=12,enc_status=103,
        enc_raw=3130,enc_rpm=270.,enc_speed_ok=1,mc_break_wave_hex='-',pwm=1)


def test_sensor_preconditions_and_recorded_old_errors():
    s=sample();assert sensor_healthy(s)
    p=EncoderPolicy();p.baseline=dict(enc_reads=100,enc_errors=12);p.saved_wave='-'
    assert p.same_sensor(s)
    for change in (dict(enc_errors=13),dict(enc_reads=99),dict(enc_io_error=-5),
        dict(enc_age_ms=100),dict(enc_ok=0),dict(enc_status=55),dict(enc_status=111),
        dict(enc_rpm=float('nan')),dict(enc_rpm=650),dict(mc_break_wave_hex='1234')):
        assert not p.same_sensor({**s,**change}),change


def test_failed_base_protection_cannot_be_overridden_by_encoder():
    p=EncoderPolicy();s=sample();p.baseline=dict(enc_reads=100,enc_errors=12);p.saved_wave='-'
    assert not p.active(s,lambda s:False)


def test_motion_is_required_after_grace_and_not_retried(monkeypatch):
    p=EncoderPolicy();p.baseline=dict(enc_reads=100,enc_errors=12);p.saved_wave='-'
    s={**sample(),'enc_rpm':0}
    monkeypatch.setattr('run_as5600_low_speed.time.monotonic',lambda:100.)
    assert p.active(s,lambda s:True)
    monkeypatch.setattr('run_as5600_low_speed.time.monotonic',lambda:103.)
    assert not p.active(s,lambda s:True)


def test_results_need_actual_angle_changes_and_fresh_reads():
    rows=[dict(status={**sample(),'enc_reads':200+i,'enc_raw':100+i*500}) for i in range(5)]
    assert summarize(rows)['passed']
    assert not summarize([dict(status=sample())]*5)['passed']
    rows[-1]['status']['enc_ok']=0
    assert not summarize(rows)['passed']
