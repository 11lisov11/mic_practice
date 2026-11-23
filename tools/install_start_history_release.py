"""Install1803/1804 only after confirmed J1OFF and fresh USB/OFF/low-bus proof.

--verify-only is offline. Uno is written and HELD before native baud changes;
only independent Uno verification finally restarts it. No START/CLEAR/ARM.
"""
import json,sys,time,types
from pathlib import Path
import prepare_start_history_release as p

RECIPE=p.OUT/'installation_recipe_r1'

def package_check():
 m=json.loads(p.read(p.OUT/'release_manifest.json'))
 assert m['offline_acceptance_passed'] and not m['installed'] and m['pair']==list(p.NEW)
 assert m['control_and_observer_math_unchanged'] and m['UART_baud']==921600
 assert (m['OFF_fast_limit_cycles'],m['estimate_age_ms'],m['raw_current_trip_A'],m['ADC_UPDATE_ticks'])==(4000,2,1.35,2048)
 for rel in m['tests'].values():assert json.loads(p.read(p.OUT/rel))['passed'],rel
 for name,root in [('evidence_sha256.json',p.ROOT),('preserved_inputs_sha256.json',p.ROOT)]:
  for rel,h in json.loads(p.read(p.OUT/name)).items():assert p.sha(root/rel)==h,rel
 for rel,h in json.loads(p.read(RECIPE/'assets_sha256.json')).items():assert p.sha(p.ROOT/rel)==h,rel
 for rel,h in m['artifacts'].items():assert p.sha(p.OUT/rel)==h,rel
 if '--verify-only' not in sys.argv:
  assert '--confirmed-j1-off-current-usb-low-bus' in sys.argv,'Physical J1OFF confirmation required'
  assert not (p.OUT/'installation_acceptance.json').exists(),'Already written: never reflash for RPC recovery'
  previous=p.OUT/'hardware_install_r1/report.json'
  if previous.exists():
   r=json.loads(p.read(previous));assert not r.get('nucleo_flash_commands') and not r.get('uno_flash_commands'),'Partial install: reviewed resume required'
  proof=p.OUT/'USB_readiness_r1/SWD/report.json';r=json.loads(p.read(proof))
  assert time.time()-proof.stat().st_mtime<600 and r['passed'],'Refresh programming readiness'
  assert r['flash_writes']==r['reset_commands']==r['halt_commands']==r['motor_commands']==0
  assert r['fresh_live_bus_valid'] and all(0<=row['bus_volts']<20 and not row['moe'] for row in r['rows'])
 return m

def adapted_source():
 s=p.read(p.ROOT/'tools/install_observer_current_window.py')
 replacements={
  'import prepare_observer_current_window as p':'import prepare_start_history_release as p',
  'OLD=(2026111609,2026111606)':'OLD=(2026111801,2026111802)',
  '--confirmed-j1-off-bus-below20-both-pc-usb':'--confirmed-j1-off-current-usb-low-bus',
  'a.confirmed_j1_off_bus_below20_both_pc_usb':'a.confirmed_j1_off_current_usb_low_bus',
  "operator_confirmation='J1 OFF, meter below20V, both boards PCUSB; 15V and wiring unchanged; no START/CLEAR'":
   "operator_confirmation='J1 OFF explicitly confirmed; exact PCUSB identities and fresh valid low-bus ADC/SWD observed; 15V and wiring unchanged; no START/CLEAR'",
  "p.OUT/f'release/nucleo_{NEW[1]}_observer_mean16.hex'":"p.OUT/f'installation_recipe_r1/release/nucleo_{NEW[1]}_start_history.hex'",
  "p.OUT/f'release/nucleo_{NEW[1]}_expected_readback.bin'":"p.OUT/f'installation_recipe_r1/release/nucleo_{NEW[1]}_expected_readback.bin'",
  "p.OUT/f'release/uno_{NEW[0]}_observer_schema3.elf-zsk.bin'":"p.OUT/f'installation_recipe_r1/release/uno_{NEW[0]}_start_history.elf-zsk.bin'",
  "'/tmp/mic_window1612_'":"'/tmp/mic_history1804_'",
  "'window_1612_'":"'history_1804_'",
 }
 for old,new in replacements.items():assert old in s,old;s=s.replace(old,new)
 start=s.index("  r['nucleo_flash_commands']=1;save()")
 route=s.index('  def route(action):',start)
 image=s.index('  image=p.OUT/',route)
 verify=s.index("  run(upload+['--upload-property','build.variant.path='",image)
 finish=s.index("  route('open');router_closed=False",verify)
 native=s[start:route];router=s[route:image];uno=s[image:verify];checked=s[verify:finish]
 original="r['uno_flash_commands']=1;save();run(upload,'flash_uno',90)"
 replacement="r['uno_flash_commands']=1;save();run(upload+['--upload-property','build.variant.path='+str(p.ROOT/'tools'),'--upload-property','openocd_cfg=flash_verify_unoq_history_hold.cfg'],'flash_uno',90)\n  assert 'VERIFIED AND HELD' in p.read(out/'flash_uno.log')\n  r['uno_held_for_paired_baud_change']=True;save()"
 assert original in uno;uno=uno.replace(original,replacement)
 s=s[:start]+router+uno+native+checked+s[finish:]
 s=s.replace("if __name__=='__main__':raise SystemExit(main())",'')
 return s

def main():
 if '--verify-only' not in sys.argv:
  assert '--outdir' in sys.argv
  assert Path(sys.argv[sys.argv.index('--outdir')+1]).resolve()==(p.OUT/'hardware_install_r1').resolve()
 s=adapted_source();module=types.ModuleType('history_installer');module.__file__=__file__
 exec(compile(s,__file__,'exec'),module.__dict__);module.package_check=package_check
 code=module.main()
 path=p.OUT/'hardware_install_r1/report.json'
 if '--verify-only' not in sys.argv and path.exists():
  r=json.loads(p.read(path))
  if r.get('native_readback_verified') and r.get('uno_readback_verified'):
   receipt=dict(pair=p.NEW,installed=True,native_readback_verified=True,uno_readback_verified=True,
    runtime_verified=bool(r.get('passed')),calibration_unchanged=r.get('calibration_unchanged'),
    OFF_timing_qualified=False,UART921600_qualified=False,START=0,CLEAR=0,ARM=0,
    uno_held_until_native_updated=r.get('uno_held_for_paired_baud_change'),
    note='Both images written once and independently verified. Pending RPC must never cause another flash.')
   p.write(p.OUT/'installation_acceptance.json',json.dumps(receipt,indent=2)+'\n')
 return code
if __name__=='__main__':raise SystemExit(main())
