"""Independent ADC forward model: reference-only, bias-only, mixed and skew cases."""
import copy
import importlib.util
import math
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[1]/'tools/analyze_reference_noise.py'
spec=importlib.util.spec_from_file_location('reference_noise_analysis',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def fixture(reference_noise,bias_noise):
    data=dict(schema='mic_ai.reference_noise.v1',source_kind='synthetic',outputs_off=True,
              bus_low=True,same_sampling_aperture=True,vrefint_settled=True,samples=[])
    for n in range(2048):
        # Independent absolute-voltage model, quantized only at the ADC outputs.
        reference=3.25*(1+reference_noise*math.sin(2*math.pi*n/41))
        bias=1.65*(1+bias_noise*math.sin(2*math.pi*n/67+.37))
        data['samples'].append(dict(vrefint_adc=round(4095*1.21/reference),
                                    bias_adc=round(4095*bias/reference)))
    return data


def test_reference_only_is_cancelled_from_bias_ratio():
    r=module.analyze(fixture(.004,0))
    assert 2600<r['vref_relative_sd_ppm']<3000
    assert r['bias_to_bandgap_relative_sd_ppm']<300
    assert r['raw_bias_relative_sd_ppm']>2600


def test_bias_only_is_not_mislabelled_as_reference_noise():
    r=module.analyze(fixture(0,.004))
    assert r['vref_relative_sd_ppm']==0
    assert 2600<r['bias_to_bandgap_relative_sd_ppm']<3000


def test_mixed_sources_remain_separately_visible():
    r=module.analyze(fixture(.004,.003))
    assert 2600<r['vref_relative_sd_ppm']<3000
    assert 1900<r['bias_to_bandgap_relative_sd_ppm']<2300
    assert not r['automatic_control_correction']


@pytest.mark.parametrize('field',['same_sampling_aperture','vrefint_settled','outputs_off','bus_low'])
def test_missing_physical_qualification_is_rejected(field):
    c=fixture(.004,0);c[field]=False
    with pytest.raises(ValueError):module.analyze(c)


def test_original_phase_capture_cannot_be_relabelled():
    with pytest.raises(ValueError):module.analyze(dict(schema=1,samples=[{}]*512))


def test_clipped_sample_is_retained_as_error():
    c=fixture(.004,0);c['samples'][80]['bias_adc']=4095
    with pytest.raises(ValueError):module.analyze(c)
