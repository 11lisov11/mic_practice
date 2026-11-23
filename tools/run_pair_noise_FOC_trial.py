"""One later-authorized1715/1716 FOC5Hz/5000ms; no hardware access on import.

Uses unchanged bounded-run safety/heartbeat/auto-stop admission and schema5
collection. CLEAR only when explicitly authorized via --clear-once. Replay is
strictly offline after outputs-off and collection, never an automatic retry.
"""
import json,sys
from pathlib import Path
import prepare_observer_pair_noise as p
import run_telemetry_deadline_trial as runner
from release_observer_decoder import load_decoder
from replay_observer_pair_noise import replay_pair_record

runner.p=p;runner.driver.package=p;runner.driver.trial.PAIR=p.NEW
runner.driver.boot.package=p;runner.driver.boot.trial=runner.driver.trial
runner.driver.capture.package=p;runner.driver.capture.base=runner.driver.boot
runner.driver.capture.decode_observer_trace_hex=load_decoder(p.OUT)


def package_check():
 m=json.loads(p.read(p.OUT/'manifest.json'));a=json.loads(p.read(p.OUT/'installation_acceptance.json'))
 assert m['pair']==a['pair']==list(p.NEW) and m['built'] and a['installed']
 assert a['native_readback_verified'] and a['uno_readback_verified'] and a['OFF_target_timing_qualified']
 assert m['NIS_safety_guard_retained'] and a['NIS_original_and_corrected_stop_retained']
 assert (m['current_trip_A'],m['OFF_fast_limit_cycles'],m['estimate_age_ms'],m['ADC_UPDATE_ticks'])==(1.35,4000,2,2048)
 assert a['OFF_cases']==64 and a['OFF_fast_cycles']<=4000
 for file,base in ((p.OUT/'source_hashes.json',p.OUT),(p.OUT/'release/sha256.json',p.OUT/'release'),
                   (p.OUT/'preserved_inputs_sha256.json',p.ROOT)):
  for rel,h in json.loads(p.read(file)).items():assert p.sha(base/rel)==h,rel
 return m


def offline_replay(out):
 result=dict(attempted=False,hardware_commands=0)
 try:
  record=out/'observer_trace.bin'
  if record.exists():
   raw=record.read_bytes();d=load_decoder(p.OUT)(raw.hex(),p.NEW[1])
   if d.get('first_nis_replay'):
    m=json.loads(p.read(p.OUT/'release/replay_manifest.json'));elf=p.OUT/'release'/m['elf']
    assert p.sha(elf)==m['elf_sha256']
    result.update(attempted=True,**replay_pair_record(raw,elf,p.NEW[1]),
                  record_sha256=p.sha(record),elf_sha256=m['elf_sha256'])
   else:result['reason']='No eligible corrected NIS refusal recorded; original trace archived'
  else:result['reason']='No complete observer record; no automatic repeat'
 except Exception as error:result.update(passed=False,error=str(error))
 target=out/'NIS_step_replay.json';assert not target.exists()
 p.write(target,json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 p.write(out/'NIS_replay_files_sha256.json',json.dumps({target.name:p.sha(target)},indent=2)+'\n')
 return result


def main():
 package_check()
 if sys.argv[1:]==['--verify-package-only']:
  print(json.dumps(dict(passed=True,pair=p.NEW,hardware_commands=0,START=0,CLEAR=0,ARM=0)));return 0
 rc=runner.main()
 out=Path(sys.argv[sys.argv.index('--outdir')+1]).resolve()
 if out.exists():
  result=offline_replay(out)
  print(json.dumps(dict(offline_replay_attempted=result['attempted'],offline_replay_passed=result.get('passed'),additional_motor_commands=0)))
  if result.get('attempted') and not result.get('passed'):return 1
 return rc


if __name__=='__main__':raise SystemExit(main())
