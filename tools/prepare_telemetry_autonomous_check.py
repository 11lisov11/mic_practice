"""Retarget the GET-only autonomous check and retain actual freshness gates."""
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1]
    source=(root/'tools/verify_observer_adc_delivery_autonomous.py').read_text(encoding='utf-8')
    source=source.replace('import prepare_observer_adc_delivery as p','import prepare_telemetry_deadline as p')
    anchor="        check('calculated_profile',"
    extra="""        check('ordinary_telemetry_fresh', all(
            0 <= s.get('mc_current_age_ms',999999) < 750
            and 0 <= s.get('mc_current_detail_age_ms',999999) < 1500
            and 0 <= s.get('mc_current_quality_age_ms',999999) < 1500 for s in rows))
"""
    assert anchor in source;source=source.replace(anchor,extra+anchor)
    target=root/'tools/verify_telemetry_deadline_autonomous.py';assert not target.exists()
    compile(source,str(target),'exec');target.write_text(source,encoding='utf-8')
    print('GET-only1603/1604 check prepared; no device commands')


if __name__=='__main__':main()
