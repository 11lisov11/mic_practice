"""Install sealed1805/1806 OFF only; archive known broken1803/1804 RX.

Programming repair accepts archived UART errors ONLY on the old OFF pair.
All new-pair/runtime checks still demand clean UART. No START/CLEAR/ARM.
"""
import json,sys,time,types,ast
from pathlib import Path
import prepare_uart_921600_rx as p
import install_start_history_release as previous

OLD=(2026111803,2026111804)

def package_check():
 m=json.loads(p.read(p.OUT/'release_manifest.json'))
 assert m['built'] and not m['installed'] and m['offline_acceptance_passed'] and m['pair']==list(p.NEW)
 assert (m['OFF_fast_limit_cycles'],m['estimate_age_ms'],m['raw_current_trip_A'],m['ADC_UPDATE_ticks'])==(4000,2,1.35,2048)
 for rel in m['tests']:assert json.loads(p.read(p.OUT/rel))['passed'],rel
 for name,root in [('source_hashes.json',p.OUT),('preserved_inputs_sha256.json',p.ROOT),('evidence_sha256.json',p.ROOT)]:
  for rel,h in json.loads(p.read(p.OUT/name)).items():assert p.sha(root/rel)==h,rel
 for rel,h in m['artifacts'].items():assert p.sha(p.OUT/rel)==h,rel
 if '--verify-only' not in sys.argv:
  assert '--confirmed-j1-off-current-usb-low-bus' in sys.argv
  assert not (p.OUT/'installation_acceptance.json').exists(),'Already installed: do not reflash for RPC'
  report=p.OUT/'hardware_install_r1/report.json'
  if report.exists():
   r=json.loads(p.read(report));assert not r.get('uno_flash_commands') and not r.get('nucleo_flash_commands'),'Review partial installation before resume'
  proof=p.OUT/'USB_readiness_r1/report.json';r=json.loads(p.read(proof))
  assert time.time()-proof.stat().st_mtime<900 and r['passed'] and r['fresh_live_bus_valid']
  assert r['flash_writes']==r['reset_commands']==r['halt_commands']==r['motor_commands']==0
  assert all(0<=x['bus_volts']<20 and not x['moe'] for x in r['rows'])
  assert json.loads(p.read(p.OUT/'USB_readiness_r1/Uno_RAM/report.json'))['passed']
 return m

def source():
 s=previous.adapted_source()
 replacements={
  'import prepare_start_history_release as p':'import prepare_uart_921600_rx as p',
  'OLD=(2026111801,2026111802)':'OLD=(2026111803,2026111804)',
  "p.BASE/f'release/nucleo_{OLD[1]}_expected_readback.bin'":"p.BASE/f'installation_recipe_r1/release/nucleo_{OLD[1]}_expected_readback.bin'",
  "p.OUT/f'installation_recipe_r1/release/nucleo_{NEW[1]}_start_history.hex'":"p.OUT/f'release/nucleo_{NEW[1]}_uart_rx_dma.hex'",
  "p.OUT/f'installation_recipe_r1/release/nucleo_{NEW[1]}_expected_readback.bin'":"p.OUT/f'release/nucleo_{NEW[1]}_expected_readback.bin'",
  "p.OUT/f'installation_recipe_r1/release/uno_{NEW[0]}_start_history.elf-zsk.bin'":"p.OUT/f'release/uno_{NEW[0]}_fifo_uart.elf-zsk.bin'",
  "'/tmp/mic_history1804_'":"'/tmp/mic_uart1806_'",
  "'history_1804_'":"'uart_1806_'",
 }
 for a,b in replacements.items():assert a in s,a;s=s.replace(a,b)
 a=" assert all(s.get(k)==0 for k in ('mc_uart_error_flags','mc_last_uart_error_flags','mc_bad_integrity','mc_bad_sequence')),'UART unhealthy'"
 assert a in s
 s=s.replace(a," if pair!=OLD:\n  assert all(s.get(k)==0 for k in ('mc_uart_error_flags','mc_last_uart_error_flags','mc_bad_integrity','mc_bad_sequence','uno_rx_hw_errors','uno_rx_dropped')),'new UART unhealthy'\n # Old UART faults are archived solely for OFF programming repair, never START.")
 return s

def main():
 if '--verify-only' not in sys.argv:
  assert '--outdir' in sys.argv
  assert Path(sys.argv[sys.argv.index('--outdir')+1]).resolve()==(p.OUT/'hardware_install_r1').resolve()
 s=source();compile(s,__file__,'exec')
 # Retain concrete reviewed code, including programming order and the narrow repair gate.
 recipe=p.OUT/'installation_recipe_r1';recipe.mkdir(exist_ok=True)
 target=recipe/'reviewable_installer.py'
 if target.exists():assert p.read(target)==s
 else:p.write(target,s)
 tree=ast.parse(s)
 for n in ast.walk(tree):
  if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='route':assert n.args[0].value in ('open','close')
 assert "'/api/control'" not in s and "'cmd'," not in s
 assert s.index("r['uno_flash_commands']=1")<s.index("r['nucleo_flash_commands']=1")<s.index("'readback_native'")<s.index("'verify_uno',90")
 module=types.ModuleType('uart_installer');module.__file__=__file__
 exec(compile(s,__file__,'exec'),module.__dict__);module.package_check=package_check
 code=module.main()
 path=p.OUT/'hardware_install_r1/report.json'
 if '--verify-only' not in sys.argv and path.exists():
  r=json.loads(p.read(path))
  if r.get('native_readback_verified') and r.get('uno_readback_verified'):
   p.write(p.OUT/'installation_acceptance.json',json.dumps(dict(pair=p.NEW,installed=True,
    native_readback_verified=True,uno_readback_verified=True,runtime_verified=bool(r['passed']),
    calibration_unchanged=r.get('calibration_unchanged'),OFF_timing_qualified=False,
    UART921600_qualified=False,START=0,CLEAR=0,ARM=0,
    note='Both images verified. No reflash for pending RPC.'),indent=2)+'\n')
 return code

if __name__=='__main__':raise SystemExit(main())
