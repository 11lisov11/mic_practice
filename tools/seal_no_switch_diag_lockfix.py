"""Seal2791 and the exact observed2790 GPIO-lock regression evidence."""
import json,hashlib
from pathlib import Path
import prepare_no_switch_diag_lockfix as fix
def main():
 p=fix.configure_common();old=fix.OLD
 # Separate IO module: no changes to sealed2790 tools, sources or images.
 s=(p.ROOT/'tools/no_switch_diag_io.py').read_text(encoding='utf-8')
 s=p.once(s,"PACKAGE=ROOT/'artifacts/live_bench_20261027/no_switch_diag_r1'","PACKAGE=ROOT/'artifacts/live_bench_20261027/no_switch_diag_r2'")
 s=p.once(s,"if w[:4]!=(0x3147444c,1,2026102790,WORDS):", "if w[:2]!=(0x3147444c,1) or w[2] not in (2026102790,2026102791) or w[3]!=WORDS:")
 s=p.once(s,'return dict(state=w[5]','return dict(build=w[2],state=w[5]')
 s=p.once(s,"return (d['state']==0", "return (d.get('build')==2026102791 and d['state']==0")
 p.write(p.ROOT/'tools/no_switch_diag_lockfix_io.py',s)
 import no_switch_diag_lockfix_io as io
 import seal_no_switch_diag as seal
 seal.decode=io.decode;seal.eligible=io.eligible;seal.main()
 m=json.loads(p.read(p.OUT/'manifest.json'))
 m.update(GPIO_lock_not_removed=True,fix_confirmed_on_hardware_registers=True,
   fixed_diagnostic_hardware_tested=False,old_2790_readback_passed_but_boot_guard_failed=True,
   old_2790_GPIOMODER='AF2, ODR/IDR LOW; LCKR A0x107c2/B0x10003',
   initialization_order=['MX_TIM1_Init','mic_load_prepare_pins','MX_MotorControl_Init/mc_lock_pins','mic_load_init'],
   install_command='python tools/install_no_switch_diag_lockfix.py --confirm-j1-j4-off-meter-below20-nucleo-usb --outdir <new-folder>',
   request_command='python tools/run_no_switch_diag_lockfix.py --confirm-j1-j4-off-meter-below20-nucleo-usb --request-once --outdir <new-folder>')
 for name in ('prepare_no_switch_diag_lockfix.py','seal_no_switch_diag_lockfix.py','no_switch_diag_lockfix_io.py','install_no_switch_diag_lockfix.py','run_no_switch_diag_lockfix.py'):
  f=p.ROOT/'tools'/name;m['tool_sha256']['tools/'+name]=p.sha(f)
 p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
 print(json.dumps(dict(sealed=True,build=fix.BUILD,preserved_files=len(m['preserved_records']),hardware_commands=0)))
if __name__=='__main__':main()
