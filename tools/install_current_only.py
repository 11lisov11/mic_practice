"""Install sealed current-only images on the discharged USB bench, without START/CLEAR."""
import json
import sys
from pathlib import Path

import install_current_shunt_monitor as install
import prepare_current_only as package

install.ROOT,install.C,install.OLD,install.NEW=package.ROOT,package.OUT,package.OLD,package.NEW
install.GUARD=package.read(package.ROOT/'tools/uart_resync_fix/update_guard.py').replace(
    '((2026101805,2026101804),(2026101807,2026101806))',str((package.OLD,package.NEW)))
exec(install.GUARD,install.__dict__)


def verify_package():
    m=json.loads(package.read(package.OUT/'manifest.json'))
    assert m['schema']=='mic_ai.current_only.v1' and m['pair_compatibility_ids']==list(package.NEW)
    assert m['built'] and m['selftest_pass'] and not m['as5600_enabled']
    for key in ('calibration_changed','thresholds_changed','uart_changed','motor_control_changed','adc_sampling_changed'):
        assert m[key] is False,key
    for table in ('source_sha256','build_sha256','verification_sha256','tooling_sha256','evidence_sha256'):
        for rel,digest in m.get(table,{}).items():assert package.sha(package.OUT/rel)==digest,rel
    for rel,digest in json.loads(package.read(package.OUT/'archive_references.json')).items():
        assert package.sha(package.ROOT/rel)==digest,rel
    assert json.loads(package.read(package.OUT/'verification/report.json'))['passed']
    images=[]
    for folder,name,build in [('uno','unoq_mcsdk_scalar',package.NEW[0]),('nucleo','ACIM-NUCLEOG431RB-IPM15B-VF_OL',package.NEW[1])]:
        b=json.loads((package.OUT/'build'/folder/(name+'.build-manifest.json')).read_text(encoding='utf-8-sig'))
        assert b['firmware_build_id']==build
        if folder=='nucleo':assert b['build_errors']==b['build_warnings']==0
        for item in b['artifacts']:assert package.sha(package.OUT/'build'/folder/item['file'])==item['sha256'].lower()
        images.append(package.OUT/'build'/folder/(b['flash_artifact'] if folder=='uno' else name+'.hex'))
    return tuple(images)


install.verify_package=verify_package

if __name__=='__main__':raise SystemExit(install.main())
