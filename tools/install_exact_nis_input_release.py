"""Install sealed1801/1802 after fresh USB/OFF/<20V evidence; no START/CLEAR.

--verify-only is strictly offline. A prior programming attempt blocks a new
automatic flash even if post-install RPC is pending; resume must be reviewed.
"""
import json,sys,time,types
from pathlib import Path
import prepare_exact_nis_input_release as p


def package_check():
    m=json.loads(p.read(p.OUT/'manifest.json'))
    assert m['built'] and not m['installed'] and m['pair']==list(p.NEW)
    assert m['observer_math_unchanged'] and m['protections_and_limits_unchanged'] and m['NIS_safety_guard_retained']
    assert (m['current_trip_A'],m['OFF_fast_limit_cycles'],m['estimate_age_ms'],m['ADC_UPDATE_ticks'],m['full_RUN_existing_limit_cycles'])==(1.35,4000,2,2048,5312)
    assert m['NIS_limits']==[25,50]
    for rel in ('verification/capture/capture_report.json','verification/adapter/native_report.json',
                'verification/protocol_guards.json','verification/release_ARM_math_identity.json','verification/release_CLI_replay.json'):
        assert json.loads(p.read(p.OUT/rel))['passed'],rel
    for inventory,base in [('source_hashes.json',p.OUT),('release/sha256.json',p.OUT/'release'),('preserved_inputs_sha256.json',p.ROOT)]:
        for rel,h in json.loads(p.read(p.OUT/inventory)).items():assert p.sha(base/rel)==h,rel
    for rel,h in m['artifacts'].items():assert p.sha(p.OUT/rel)==h,rel
    for rel,h in json.loads(p.read(p.OUT/'installation_assets.json')).items():assert p.sha(p.ROOT/rel)==h,rel
    for rel in ('nucleo/Inc/motor_control.h','nucleo/Inc/foc_experiment.h','nucleo/Inc/observer_pair_noise.h',
                'nucleo/Inc/current_adc_window_plan.h','nucleo/Inc/current_adc_deadline.h','nucleo/Inc/local_stop.h'):
        assert p.sha(p.OUT/rel)==p.sha(p.BASE/rel),rel
    if '--verify-only' not in sys.argv:
        assert not (p.OUT/'installation_acceptance.json').exists(),'Already programmed: do not flash again'
        previous=p.OUT/'hardware_install_r1/report.json'
        if previous.exists():
            r=json.loads(p.read(previous));assert not r.get('nucleo_flash_commands') and not r.get('uno_flash_commands'),'Prior flash attempt requires reviewed resume, not another install'
        proof=p.OUT/'USB_readiness_r1/SWD/report.json';r=json.loads(p.read(proof))
        assert time.time()-proof.stat().st_mtime<600,'Refresh actual USB/SWD programming evidence'
        assert r['passed'] and r['flash_writes']==r['reset_commands']==r['halt_commands']==0
        assert all(0<=row['bus_volts']<20 and row['moe'] is False for row in r['rows'])
    return m


def main():
    if '--verify-only' not in sys.argv:
        assert '--outdir' in sys.argv
        out=Path(sys.argv[sys.argv.index('--outdir')+1]).resolve()
        assert out==(p.OUT/'hardware_install_r1').resolve(),'Use canonical first-install evidence directory'
    source=p.read(p.ROOT/'tools/install_observer_current_window.py')
    replacements={
        'import prepare_observer_current_window as p':'import prepare_exact_nis_input_release as p',
        'OLD=(2026111609,2026111606)':'OLD=(2026111715,2026111716)',
        '_observer_mean16.hex':'_exact_source.hex',
        '_observer_schema3.elf-zsk.bin':'_exact_source.elf-zsk.bin',
        '--confirmed-j1-off-bus-below20-both-pc-usb':'--observed-fresh-low-bus-both-usb',
        'a.confirmed_j1_off_bus_below20_both_pc_usb':'a.observed_fresh_low_bus_both_usb',
        'Existing operator preparation confirmation required':'Current preparation and observed USB/OFF/low-bus evidence required',
        "operator_confirmation='J1 OFF, meter below20V, both boards PCUSB; 15V and wiring unchanged; no START/CLEAR'":
        "programming_evidence='User preparation plus observed USB identities, fresh valid HMI/SWD low bus and MOE0; no invented meter reading'",
        "'/tmp/mic_window1612_'":"'/tmp/mic_exactinput1802_'",
        "'window_1612_'":"'exactinput_1802_'",
    }
    for old,new in replacements.items():assert old in source,old;source=source.replace(old,new)
    source=source.replace("if __name__=='__main__':raise SystemExit(main())",'')
    module=types.ModuleType('checked_exact_input_installer');module.__file__=__file__
    exec(compile(source,__file__,'exec'),module.__dict__);module.package_check=package_check
    result=module.main()
    path=p.OUT/'hardware_install_r1/report.json'
    if '--verify-only' not in sys.argv and path.exists():
        r=json.loads(p.read(path))
        if r.get('native_readback_verified') and r.get('uno_readback_verified'):
            receipt=dict(pair=p.NEW,installed=True,native_readback_verified=True,uno_readback_verified=True,
                runtime_verified=bool(r.get('passed')),calibration_unchanged=r.get('calibration_unchanged'),
                target_timing_qualified=False,START=0,CLEAR=0,ARM=0,
                note='Images programmed once. Pending RPC or qualification must never trigger reflash.')
            p.write(p.OUT/'installation_acceptance.json',json.dumps(receipt,indent=2)+'\n')
    return result


if __name__=='__main__':raise SystemExit(main())
