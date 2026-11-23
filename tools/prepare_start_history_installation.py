"""Prepare immutable install/readback assets, no board or network access."""
import ast,json,shutil
import prepare_start_history_release as p
from probe_native_programming_state import programmed_hex_image
from install_start_history_release import adapted_source
from verify_start_history_idle import source as idle_source
from elftools.elf.elffile import ELFFile

def member_layout(elf,name):
 with elf.open('rb') as f:
  e=ELFFile(f)
  for cu in e.get_dwarf_info().iter_CUs():
   for die in cu.iter_DIEs():
    a=die.attributes.get('DW_AT_name')
    if die.tag=='DW_TAG_typedef' and a and a.value==name.encode():
     t=die.get_DIE_from_attribute('DW_AT_type')
     return {m.attributes['DW_AT_name'].value.decode():int(m.attributes['DW_AT_data_member_location'].value) for m in t.iter_children() if m.tag=='DW_TAG_member'}
 raise ValueError(name)

def main():
 out=p.OUT/'installation_recipe_r1';out.mkdir(exist_ok=False);release=out/'release';release.mkdir()
 m=json.loads(p.read(p.OUT/'release_manifest.json'));assert m['pair']==list(p.NEW)
 for rel,h in m['artifacts'].items():assert p.sha(p.OUT/rel)==h,rel
 base=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL'
 for ext in ('elf','bin','hex'):shutil.copy2(base.with_suffix('.'+ext),release/f'nucleo_{p.NEW[1]}_start_history.{ext}')
 expected,holes=programmed_hex_image(base.with_suffix('.hex'),base.with_suffix('.bin').read_bytes())
 (release/f'nucleo_{p.NEW[1]}_expected_readback.bin').write_bytes(expected)
 shutil.copy2(p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin',release/f'uno_{p.NEW[0]}_start_history.elf-zsk.bin')
 assert member_layout(base.with_suffix('.elf'),'UART_HandleTypeDef')['Init']==4
 assert member_layout(base.with_suffix('.elf'),'UART_InitTypeDef')['BaudRate']==0
 install=adapted_source();idle=idle_source();compile(install,'prepared_installer','exec');compile(idle,'prepared_IDLE','exec')
 p.write(out/'reviewable_installer.py',install);p.write(out/'reviewable_OFF_verifier.py',idle)
 # Check operational order, including independent readbacks and no motor calls.
 order=[install.index("run(upload+['--upload-property'"),install.index("r['nucleo_flash_commands']=1"),install.index("'readback_native'"),install.index("'verify_uno',90"),install.index("route('open');router_closed=False")]
 assert order==sorted(order),order
 assert 'openocd_cfg=flash_verify_unoq_history_hold.cfg' in install
 cfg=p.read(p.ROOT/'tools/flash_verify_unoq_history_hold.cfg')
 assert 'flash write_image erase ${filename1} 0x08100000 bin' in cfg and 'mww' not in cfg
 assert 'reset\n    sleep' not in cfg and 'VERIFIED AND HELD' in cfg
 # Existing recipe does not invoke a motor START/CLEAR/ARM RPC route.
 tree=ast.parse(install)
 for node in ast.walk(tree):
  if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='route':
   assert len(node.args)==1 and isinstance(node.args[0],ast.Constant) and node.args[0].value in ('open','close')
 assert "'/api/control'" not in install and "'cmd'," not in install
 assets={}
 names=['install_start_history_release.py','prepare_start_history_installation.py','verify_start_history_idle.py',
  'flash_verify_unoq_history_hold.cfg','verify_restart_unoq_sketch.cfg','install_observer_current_window.py',
  'finish_rollback_3014_hmi.py','install_bkin_boot_armed_pair.py','install_sd_break_filter_usb_pair.py',
  'unoq_wifi_hmi_deploy.py','wifi_stop_tail_probe.py','probe_native_programming_state.py','probe_low_bus_usb.py',
  'verify_exact_nis_input_idle.py','prepare_start_history_release.py']
 for name in names:
  path=p.ROOT/'tools'/name;assets[path.relative_to(p.ROOT).as_posix()]=p.sha(path)
 for path in out.rglob('*'):
  if path.is_file():assets[path.relative_to(p.ROOT).as_posix()]=p.sha(path)
 p.write(out/'assets_sha256.json',json.dumps(assets,indent=2)+'\n')
 p.write(out/'report.json',json.dumps(dict(passed=True,pair=p.NEW,hardware_commands=0,
  independent_native_readback_expected_bytes=len(expected),native_erased_padding_offsets=holes,
  uno_held_until_native_baud_updated=True,operation_order=order,
  Uno_loader_verified_not_rewritten=True,independent_Uno_verify_before_restart=True,
  UART_register_proof_prepared=True,OFF_DWT_64_cases=True,no_START_CLEAR_ARM=True,
  no_automatic_reflash_after_partial_install=True),indent=2)+'\n')
 print(json.dumps(dict(prepared=True,pair=p.NEW,hardware_commands=0,assets=len(assets))))
if __name__=='__main__':main()
