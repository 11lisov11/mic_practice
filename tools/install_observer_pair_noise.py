"""Install1715/1716 after observed USB/OFF/low-bus proof. No motor commands.

Backs up old RAM/flash/records and calibration, updates matching HMI, verifies
both images by readback. --verify-only checks files, never reads a device.
"""
import json
from pathlib import Path
import sys,time,types
import prepare_observer_pair_noise as p


def package_check():
 assert not (p.OUT/'installation_acceptance.json').exists(),'Already installed: do not flash twice'
 m=json.loads(p.read(p.OUT/'manifest.json'))
 assert m['built'] and not m['installed'] and m['pair']==list(p.NEW)
 assert m['NIS_safety_guard_retained'] and m['NIS_limits']==[25,50]
 assert (m['current_trip_A'],m['OFF_fast_limit_cycles'],m['estimate_age_ms'],m['ADC_UPDATE_ticks'])==(1.35,4000,2,2048)
 assert m['full_RUN_existing_limit_cycles']==5312
 for file in ('pair_kernel_report.json','pair_model_report.json','adapter_report.json',
              'wire_guard_report.json','pair_replay_report.json','replay_header_guards.json','release_CLI_replay.json'):
  assert json.loads(p.read(p.OUT/'verification'/file))['passed'],file
 for manifest,base in ((p.OUT/'source_hashes.json',p.OUT),(p.OUT/'release/sha256.json',p.OUT/'release'),
                       (p.OUT/'preserved_inputs_sha256.json',p.ROOT)):
  for rel,h in json.loads(p.read(manifest)).items():assert p.sha(base/rel)==h,rel
 for rel,h in m['artifacts'].items():assert p.sha(p.OUT/rel)==h,rel
 for rel in ('nucleo/Inc/foc_experiment.h','nucleo/Inc/current_adc_window_plan.h',
             'nucleo/Inc/current_adc_deadline.h','nucleo/Inc/local_stop.h','nucleo/Inc/first_break_snapshot.h'):
  assert p.sha(p.OUT/rel)==p.sha(p.BASE/rel),rel
 if '--verify-only' not in sys.argv:
  proof=p.OUT/'USB_readiness_r1/SWD/report.json';r=json.loads(p.read(proof))
  assert time.time()-proof.stat().st_mtime<600,'Refresh the actual hardware proof'
  assert r['passed'] and r['flash_writes']==r['reset_commands']==r['halt_commands']==0
  assert all(0<=row['bus_volts']<20 and row['moe'] is False for row in r['rows'])
 return m


def main():
 source=p.read(p.ROOT/'tools/install_observer_current_window.py')
 replacements={
  'import prepare_observer_current_window as p':'import prepare_observer_pair_noise as p',
  'OLD=(2026111609,2026111606)':'OLD=(2026111713,2026111714)',
  '_observer_mean16.hex':'_pair_noise.hex',
  '_observer_schema3.elf-zsk.bin':'_schema5.elf-zsk.bin',
  '--confirmed-j1-off-bus-below20-both-pc-usb':'--observed-fresh-low-bus-both-usb',
  'a.confirmed_j1_off_bus_below20_both_pc_usb':'a.observed_fresh_low_bus_both_usb',
  'Existing operator preparation confirmation required':'Fresh USB/low-bus/OFF proof required',
  "operator_confirmation='J1 OFF, meter below20V, both boards PCUSB; 15V and wiring unchanged; no START/CLEAR'":
   "programming_evidence='User preparation and observed USB identities, fresh HMI/SWD low bus and MOE0; no invented meter reading'",
  "'/tmp/mic_window1612_'":"'/tmp/mic_pairnoise1716_'",
  "'window_1612_'":"'pairnoise_1716_'",
 }
 for old,new in replacements.items():
  assert old in source,old;source=source.replace(old,new)
 source=source.replace("if __name__=='__main__':raise SystemExit(main())",'')
 module=types.ModuleType('checked_pair_noise_installer');module.__file__=str(Path(__file__).resolve())
 exec(compile(source,module.__file__,'exec'),module.__dict__);module.package_check=package_check
 return module.main()


if __name__=='__main__':raise SystemExit(main())
