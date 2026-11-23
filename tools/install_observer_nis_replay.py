"""Install sealed1713/1714 only with freshly observed USB/low-bus/OFF proof.

Reuses the existing backup/calibration/flash/readback/atomic-HMI installer.
Never sends START/CLEAR/ARM. Does not invent an operator meter confirmation.
"""
import json
from pathlib import Path
import time
import types

import prepare_observer_nis_replay as p


def package_check():
    assert not (p.OUT/'installation_acceptance.json').exists(),'Installed release receipt exists; do not flash again'
    m=json.loads(p.read(p.OUT/'manifest.json'))
    assert m['built'] and not m['installed'] and m['pair']==list(p.NEW)
    assert m['observer_math_unchanged'] and m['protections_and_limits_unchanged']
    for report in ('capture_report.json','ARM_math_identity.json','adapter_report.json','release_CLI_replay.json'):
        assert json.loads(p.read(p.OUT/'verification'/report))['passed'],report
    for manifest,base in ((p.OUT/'source_hashes.json',p.OUT),
                          (p.OUT/'release/sha256.json',p.OUT/'release'),
                          (p.BASE/'preserved_all_hashes.json',p.ROOT)):
        for rel,h in json.loads(p.read(manifest)).items():assert p.sha(base/rel)==h,rel
    for rel in m['unchanged_modules']:assert p.sha(p.OUT/rel)==p.sha(p.BASE/rel),rel
    proof=p.OUT/'USB_readiness_r1/SWD/report.json'
    r=json.loads(p.read(proof))
    assert time.time()-proof.stat().st_mtime<600,'Direct proof expired; refresh before installing'
    assert r['passed'] and r['flash_writes']==r['reset_commands']==r['halt_commands']==0
    assert all(0<x['bus_volts']<20 and x['moe'] is False for x in r['rows'])
    return m


def main():
    source=p.read(p.ROOT/'tools/install_observer_current_window.py')
    replacements={
        'import prepare_observer_current_window as p':'import prepare_observer_nis_replay as p',
        'OLD=(2026111609,2026111606)':'OLD=(2026111611,2026111612)',
        '_observer_mean16.hex':'_NIS_replay.hex',
        '_observer_schema3.elf-zsk.bin':'_NIS_schema4.elf-zsk.bin',
        '--confirmed-j1-off-bus-below20-both-pc-usb':'--observed-fresh-low-bus-both-usb',
        'a.confirmed_j1_off_bus_below20_both_pc_usb':'a.observed_fresh_low_bus_both_usb',
        'Existing operator preparation confirmation required':'Fresh read-only USB/SWD/HMI OFF and low-bus evidence required',
        "operator_confirmation='J1 OFF, meter below20V, both boards PCUSB; 15V and wiring unchanged; no START/CLEAR'":
        "programming_evidence='Observed USB identities, fresh HMI10V SAFE/PWM0 and independent SWD10.12/10.16V MOE0; no new operator meter assertion'",
        "'/tmp/mic_window1612_'":"'/tmp/mic_NIS1714_'",
        "'window_1612_'":"'NIS_replay_1714_'",
    }
    for old,new in replacements.items():
        assert old in source,old
        source=source.replace(old,new)
    source=source.replace("if __name__=='__main__':raise SystemExit(main())",'')
    module=types.ModuleType('checked_nis_installer');module.__file__=str(Path(__file__).resolve())
    exec(compile(source,module.__file__,'exec'),module.__dict__)
    module.package_check=package_check
    return module.main()


if __name__=='__main__':raise SystemExit(main())
