import copy,json,struct,os
from pathlib import Path
import numpy as np
import pytest
from motor_identification.commissioning import decode,calibrate,impedance_capture,crc32c
from motor_identification.standstill import identify
ROOT=Path(__file__).resolve().parents[1]
DATA=Path(os.environ.get('MIC_COMMISSIONING_TEST_DATA',str(ROOT/'artifacts/live_bench_20261029/standstill_commissioning_r1/model_final')))
def points(kind):return [decode(p.read_bytes(),source_kind='synthetic') for p in sorted(DATA.glob(kind+'_*.bin'))]
def calibration():return json.loads((DATA/'calibration.json').read_text(encoding='utf-8'))
def test_actual_c_capture_recovers_equivalent_parameters_without_foc_qualification():
    c=calibrate(points('dc'));assert c['accepted'] and not c['physical_amp_scale_qualified']
    result=identify(impedance_capture(points('ac'),c,rotor_stationary_verified=True))
    assert result['accepted'] and not result['eligible_for_foc_start']
    assert result['equivalent_mcsdk_model']['RR']==pytest.approx(9,rel=.03)
    assert result['equivalent_mcsdk_model']['LLS']==pytest.approx(.012,rel=.03)
    assert result['equivalent_mcsdk_model']['LMS']==pytest.approx(.3,rel=.03)
def test_hardware_requires_the_native_crc():
    raw=next(DATA.glob('dc_*.bin')).read_bytes()
    with pytest.raises(ValueError,match='CRC required'):decode(raw,source_kind='hardware')
    with pytest.raises(ValueError,match='CRC mismatch'):decode(raw,source_kind='hardware',expected_crc=crc32c(raw)^1)
    assert decode(raw,source_kind='hardware',expected_crc=crc32c(raw))['source_kind']=='hardware'
@pytest.mark.parametrize('offset,value',[(20,3),(24,0),(36,32),(100,0),(28,1)])
def test_aborted_missing_or_invalid_coverage_records_rejected(offset,value):
    raw=bytearray(next(DATA.glob('dc_*.bin')).read_bytes());struct.pack_into('<I',raw,offset,value)
    with pytest.raises(ValueError):decode(bytes(raw),source_kind='synthetic')
def test_old_twelve_sample_adc_peak_cannot_be_an_identification_capture():
    with pytest.raises(ValueError):decode(bytes(1200),source_kind='synthetic')
def test_no_mixed_provenance_or_missing_dc_validation():
    d=points('dc');d[0]['source_kind']='hardware'
    with pytest.raises(ValueError,match='provenance'):calibrate(d)
    d=[p for p in points('dc') if not np.isclose(abs(p['reference_a']),.12,atol=.003)]
    with pytest.raises(ValueError,match='validation'):calibrate(d)
def test_dc_drift_not_accepted_as_motor_resistance():
    d=points('dc');d[0]['points'][-16:,1]+=.03
    with pytest.raises(ValueError,match='not settled'):calibrate(d)
def test_stationary_rotor_and_matching_inverter_calibration_required():
    with pytest.raises(ValueError,match='stationary'):impedance_capture(points('ac'),calibration(),rotor_stationary_verified=False)
    ac=points('ac');ac[0]['calibration_crc']^=1
    with pytest.raises(ValueError,match='provenance'):impedance_capture(ac,calibration(),rotor_stationary_verified=True)
def test_independent_electrical_validation_detects_voltage_error():
    ac=points('ac')
    for p in ac:
        if round(p['frequency_hz']) in (3,8,30,80):p['points'][:,5:7]*=1.3
    result=identify(impedance_capture(ac,calibration(),rotor_stationary_verified=True))
    assert not result['accepted']
