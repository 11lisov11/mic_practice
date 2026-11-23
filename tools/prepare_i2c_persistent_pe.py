"""Prepare the healthy-transfer PE lifecycle change. No hardware access."""
import ast,json,os,shutil
from pathlib import Path
import prepare_sda_idle_bus_clear as previous
ROOT=previous.ROOT;BASE=previous.OUT
AUDIT=ROOT/'artifacts/live_bench_20261027/pwm_i2c_lifecycle_audit_r1'
OUT=ROOT/'artifacts/live_bench_20261027/i2c_persistent_pe_r1'
RES=ROOT/'tools/i2c_persistent_pe'
OLD=(2026102707,2026102708);NEW=(2026102709,2026102710)
read,write,sha,once=previous.read,previous.write,previous.sha,previous.once

def identity(s):return s.replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))

def hmi(s):
 for a,b in [('(2026102707,2026102708)','(2026102709,2026102710)'),('(2026102707, 2026102708)','(2026102709, 2026102710)')]:s=s.replace(a,a+','+b)
 # Peer lists are spread over current/zero/SD/capture decoders. Extend every
 # literal integer tuple, preserving every older peer and the exact pair gates.
 tree=ast.parse(s);lines=s.splitlines(keepends=True);offsets=[0]
 for line in lines:offsets.append(offsets[-1]+len(line))
 edits=[]
 for node in ast.walk(tree):
  if not isinstance(node,ast.Tuple) or not all(isinstance(x,ast.Constant) and type(x.value) is int for x in node.elts):continue
  values=tuple(x.value for x in node.elts)
  if values in (OLD,NEW) or OLD[1] not in values or NEW[1] in values:continue
  a=offsets[node.lineno-1]+node.col_offset;b=offsets[node.end_lineno-1]+node.end_col_offset
  old=s[a:b];assert old.endswith(')')
  edits.append((a,b,old[:-1].rstrip().rstrip(',')+','+str(NEW[1])+')'))
 for a,b,text in sorted(edits,reverse=True):s=s[:a]+text+s[b:]
 s=once(s,'peer!=2026102708 or len(b)!=43','peer not in (2026102708,2026102710) or len(b)!=43')
 ast.parse(s);return s

def main():
 assert not OUT.exists(),'Keep previous package'
 m=json.loads(read(BASE/'manifest.json'));assert m['installed'] and m['built']
 for table in ('source_sha256','build_sha256','verification_sha256'):
  for rel,d in m[table].items():assert sha(BASE/rel)==d,rel
 assert json.loads(read(AUDIT/'report.json'))['passed']
 for rel,d in json.loads(read(AUDIT/'sha256.json')).items():assert sha(AUDIT/rel)==d,rel
 for folder in ('nucleo','UNOQ_MOTOR','web_hmi','libraries'):
  def copier(src,dst):
   rel=Path(src).relative_to(BASE/folder)
   if folder=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dst);return dst
   return shutil.copy2(src,dst)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=copier,ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    a=read(f);b=identity(a)
    if a!=b:write(f,b)
 for name,dst in [('encoder_core.h','nucleo/Inc/encoder_core.h'),('nucleo_encoder.c','nucleo/Src/nucleo_encoder.c')]:
  write(OUT/dst,identity(read(AUDIT/'candidate'/name)))
 write(OUT/'web_hmi/server.py',hmi(read(BASE/'web_hmi/server.py')))
 for folder in ('verification','build/uno','build/nucleo','preserved_records'):(OUT/folder).mkdir(parents=True)
 shutil.copytree(BASE/'preserved_records',OUT/'preserved_records/earlier_history')
 for rel in ('final_captures.json','installation_evidence.json','runtime_idle_r2/report.json','runtime_idle_r2/samples.jsonl','install_usb_r2/report.json','install_usb_r2_preserved_live/saved_status.json'):
  dst=OUT/'preserved_records'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(BASE/rel,dst);assert sha(dst)==sha(BASE/rel)
 archive={str(f.relative_to(OUT/'preserved_records')).replace('\\','/'):sha(f) for f in sorted((OUT/'preserved_records').rglob('*')) if f.is_file()}
 r=dict(schema='mic_ai.i2c_persistent_pe.v1',pair_compatibility_ids=list(NEW),predecessor=str(BASE),built=False,selftest_pass=False,installed=False,
  successful_read_keeps_pe_enabled=True,successful_read_clears_cr2=True,error_cleanup_policy_unchanged=True,
  i2c_timing_filters_unchanged=True,data_acquisition_budget_ms=3,error_backoff_ms=20,cleanup_budget_us=500,
  bus_clear_once_per_boot=True,bus_clear_off_and_below_20v_only=True,bus_clear_max_clocks=9,
  first_records_frozen=True,original_capture_bytes=160,original_capture_format=2,extension_bytes=100,
  sensor_feedback_control=False,motor_control_changed=False,thresholds_changed=False,calibration_changed=False,
  uart_command_protocol_changed=False,bkin_changed=False,adc_trigger_changed=False,pwm_ccr123_changed=False,
  deadtime_changed=False,watchdogs_changed=False,rpc_libraries_unchanged=True,no_irq_mask_or_delay_loop=True,
  calibration_sha256=m['calibration_sha256'],historical_records_preserved=archive,
  sensor_under_pwm_qualified=False,hardware_validated=False,initial_pwm_nack_fixed_or_proven=False)
 write(OUT/'manifest.json',json.dumps(r,indent=2)+'\n');print(json.dumps(dict(prepared=True,pair=NEW,archived_files=len(archive),hardware_commands=0)))
if __name__=='__main__':main()
