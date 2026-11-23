"""Offline separation of coherent VREFINT/bias ADC pairs; never controls hardware.

Measurement model: x = B/R, y = M/R. B is the internal bandgap, R the
ADC reference and M the external1.65V bias. y/x removes the common denominator.
Only a future, explicitly coherent capture can use this analysis. Existing
phase/phase captures do NOT contain VREFINT and cannot be substituted.
"""
import argparse
import json
import math
from pathlib import Path
import statistics


def analyze(capture):
    if capture.get('schema')!='mic_ai.reference_noise.v1':
        raise ValueError('A dedicated reference-noise capture is required')
    if capture.get('outputs_off') is not True or capture.get('bus_low') is not True:
        raise ValueError('Only OFF/low-bus diagnostic measurements are supported')
    if capture.get('same_sampling_aperture') is not True:
        raise ValueError('Different sampling instants cannot separate fast reference noise')
    if capture.get('vrefint_settled') is not True:
        raise ValueError('Internal reference stabilization and sampling time not confirmed')
    if capture.get('source_kind') not in ('hardware','synthetic'):
        raise ValueError('Explicit data provenance required')
    rows=capture.get('samples',[])
    if len(rows)<128:
        raise ValueError('At least128 coherent, unfiltered pairs are required')
    x=[];y=[]
    for row in rows:
        a,b=row['vrefint_adc'],row['bias_adc']
        if type(a) is not int or type(b) is not int or not(16<=a<=4079 and 16<=b<=4079):
            raise ValueError('Clipped, invalid or missing ADC sample; do not silently discard it')
        x.append(a);y.append(b)
    mx,my=statistics.mean(x),statistics.mean(y)
    reference_relative=[mx/a for a in x]
    bias_to_bandgap=[b/a for a,b in zip(x,y)]
    mb=statistics.mean(bias_to_bandgap)
    bias_relative=[v/mb for v in bias_to_bandgap]
    # Report relative excursions; absolute DC calibration and physical amperes
    # are deliberately not inferred. Bandgap noise and ADC quantization remain.
    common_cov=sum((a-mx)*(b-my) for a,b in zip(x,y))/(len(x)-1)
    denom=statistics.stdev(x)*statistics.stdev(y)
    return dict(schema='mic_ai.reference_noise.analysis.v1',source_kind=capture['source_kind'],
        samples=len(rows),vrefint_mean_adc=mx,bias_mean_adc=my,
        vref_relative_sd_ppm=statistics.stdev(reference_relative)*1e6,
        bias_to_bandgap_relative_sd_ppm=statistics.stdev(bias_relative)*1e6,
        raw_bias_relative_sd_ppm=statistics.stdev(y)/my*1e6,
        raw_pair_correlation=common_cov/denom if denom else None,
        automatic_control_correction=False,protection_thresholds_changed=False,
        limitations=['VREFINT noise, ADC quantization and residual coupling are included.',
            'Coherent sampling and stable internal bandgap must be established by the acquisition firmware.',
            'Sequentially sampled phase data and multimeter DC readings cannot replace this capture.',
            'This diagnostic does not qualify current scale, RMS, inductance or FOC.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    result=analyze(json.loads(a.capture.read_text(encoding='utf-8')))
    with a.out.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2)
    print(json.dumps(result))


if __name__=='__main__':main()
