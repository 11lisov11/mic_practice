"""Seal2792 timestamp-order fix; preserve unchanged diagnostic safety limits."""
import json
import prepare_no_switch_diag_snapshot as fix
def main():
 p=fix.configure_common()
 s=(p.ROOT/'tools/no_switch_diag_lockfix_io.py').read_text(encoding='utf-8')
 s=p.once(s,"PACKAGE=ROOT/'artifacts/live_bench_20261027/no_switch_diag_r2'","PACKAGE=ROOT/'artifacts/live_bench_20261027/no_switch_diag_r3'")
 s=p.once(s,'w[2] not in (2026102790,2026102791)','w[2] not in (2026102790,2026102791,2026102792)')
 s=p.once(s,"d.get('build')==2026102791","d.get('build')==2026102792")
 s=p.once(s,'sequence=w[4])','sequence=w[4],guard_adc_stamp=w[66],guard_cache_stamp=w[67],guard_clock=w[68])')
 p.write(p.ROOT/'tools/no_switch_diag_snapshot_io.py',s)
 # Installation algorithm stays identical; only the identified predecessor
 # is now the OFF/ABORTED2791 with the diagnosed age-race reason8.
 s=(p.ROOT/'tools/install_no_switch_diag_lockfix.py').read_text(encoding='utf-8')
 s=s.replace('from no_switch_diag_lockfix_io import','from no_switch_diag_snapshot_io import')
 s=s.replace("PACKAGE.with_name('no_switch_diag_r1')","PACKAGE.with_name('no_switch_diag_r2')")
 s=s.replace("before['build']==2026102790 and before['state']==0 and before['attempted']==0","before['build']==2026102791 and before['state']==3 and before['attempted']==1 and before['reason']==8")
 s=s.replace("d['build']==2026102791","d['build']==2026102792")
 s=s.replace("'before2790'","'before2791'").replace("'boot2791'","'boot2792'").replace('2791 write/readback','2792 write/readback')
 p.write(p.ROOT/'tools/install_no_switch_diag_snapshot.py',s)
 import no_switch_diag_snapshot_io as io
 import seal_no_switch_diag as seal
 seal.decode=io.decode;seal.eligible=io.eligible;seal.main()
 m=json.loads(p.read(p.OUT/'manifest.json'))
 m.update(installed=False,active=False,readback_verified=False,runtime_boot_guard_passed=False,GPIO_LOW_and_locks_hardware_verified=False,
  snapshot_order_fix_hardware_qualified=False,diagnostic_ADC_age_limit_ms=5,diagnostic_foreground_age_limit_ms=5,
  register_time_snapshot_preemption_cases=20000,true_stale_age_negative_controls=2,
  install_command='python tools/install_no_switch_diag_snapshot.py --confirm-j1-j4-off-meter-below20-nucleo-usb --outdir <new-folder>',
  request_command='python tools/run_no_switch_diag_snapshot.py --confirm-j1-j4-off-meter-below20-nucleo-usb --request-once --outdir <new-folder>')
 for name in ('prepare_no_switch_diag_snapshot.py','seal_no_switch_diag_snapshot.py','no_switch_diag_snapshot_io.py','install_no_switch_diag_snapshot.py','run_no_switch_diag_snapshot.py'):
  f=p.ROOT/'tools'/name;m['tool_sha256']['tools/'+name]=p.sha(f)
 p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
 print(json.dumps(dict(sealed=True,build=fix.BUILD,preserved_files=len(m['preserved_records']),hardware_commands=0)))
if __name__=='__main__':main()
