"""One authorized1809/1810 FOC5Hz/5s; no IO on import/package verification.

Uses the established bounded trial, native guards, RPC baseline, heartbeat,
MCU auto-stop and STOP fallback. CLEAR requires explicit --clear-once consent.
"""
import json,sys
from pathlib import Path
import prepare_boot_stack_integrity as p
import run_pair_noise_FOC_trial as prior
from release_observer_decoder import load_decoder
from replay_observer_pair_noise import replay_pair_record

prior.p=p
prior.runner.p=p
prior.runner.driver.package=p
prior.runner.driver.trial.PAIR=p.NEW
prior.runner.driver.boot.package=p
prior.runner.driver.boot.trial=prior.runner.driver.trial
prior.runner.driver.capture.package=p
prior.runner.driver.capture.base=prior.runner.driver.boot
prior.runner.driver.capture.decode_observer_trace_hex=load_decoder(p.OUT)

def package_check():
 m=json.loads(p.read(p.OUT/'release_manifest.json'))
 a=json.loads(p.read(p.OUT/'installation_acceptance.json'))
 q=json.loads(p.read(p.OUT/'post_install_idle_r1/report.json'))
 assert m['built'] and m['offline_acceptance_passed'] and m['pair']==a['pair']==list(p.NEW)
 assert a['installed'] and a['native_readback_verified'] and a['uno_readback_verified'] and a['calibration_unchanged']
 assert a['runtime_idle_verified'] and a['OFF_timing_qualified'] and a['boot_record_CRC_verified']
 assert q['passed'] and q['CPU_qualified'] and q['fast_cycles']<=4000
 assert (m['OFF_fast_limit_cycles'],m['estimate_age_ms'],m['raw_current_trip_A'],m['ADC_UPDATE_ticks'])==(4000,2,1.35,2048)
 assert m['capture_capacities_unchanged'] and m['stack_reserve']==4096 and m['heap_reserve']==512
 for name,root in [('source_hashes.json',p.OUT),('preserved_inputs_sha256.json',p.ROOT)]:
  for rel,h in json.loads(p.read(p.OUT/name)).items():assert p.sha(root/rel)==h,rel
 for rel,h in m['artifacts'].items():assert p.sha(p.OUT/rel)==h,rel
 for rel in m['tests']:assert json.loads(p.read(p.OUT/rel))['passed'],rel
 return m

def offline_replay(out):
 result=dict(attempted=False,hardware_commands=0)
 try:
  record=out/'observer_trace.bin'
  if record.exists():
   raw=record.read_bytes();d=load_decoder(p.OUT)(raw.hex(),p.NEW[1])
   if d.get('first_nis_replay'):
    elf=p.OUT/'release/nucleo_2026111810_stack_guard.elf'
    manifest=json.loads(p.read(p.OUT/'release_manifest.json'))
    assert p.sha(elf)==manifest['artifacts'][elf.relative_to(p.OUT).as_posix()]
    result.update(attempted=True,**replay_pair_record(raw,elf,p.NEW[1]),record_sha256=p.sha(record),elf_sha256=p.sha(elf))
   else:result['reason']='No eligible NIS refusal recorded; original trace retained'
  else:result['reason']='No complete observer record; no automatic repeat'
 except Exception as e:result.update(passed=False,error=repr(e))
 target=out/'NIS_step_replay.json';assert not target.exists()
 p.write(target,json.dumps(result,indent=2)+'\n')
 p.write(out/'NIS_replay_files_sha256.json',json.dumps({target.name:p.sha(target)},indent=2)+'\n')
 return result

prior.package_check=package_check
prior.offline_replay=offline_replay

if __name__=='__main__':raise SystemExit(prior.main())
