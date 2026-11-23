"""Install the sealed research pair on the existing discharged USB bench. No START/CLEAR."""
import base64,json,sys,time
import install_current_shunt_monitor as install
import prepare_research_suite as p
install.ROOT,install.C,install.OLD,install.NEW=p.ROOT,p.OUT,p.OLD,p.NEW
install.GUARD=p.read(p.ROOT/'tools/uart_resync_fix/update_guard.py').replace(
 '((2026101805,2026101804),(2026101807,2026101806))',str((p.OLD,p.NEW)))
exec(install.GUARD,install.__dict__)

_remote_installer=install.remote_installer
def remote_installer():
 # Keep HTML and JS in the same checked deployment, before the one HMI restart.
 source=_remote_installer();encoded=base64.b64encode((p.OUT/'web_hmi/static/index.html').read_bytes()).decode()
 source=p.once(source,'    app_data = None','    import base64\n    index_data=base64.b64decode('+repr(encoded)+')\n    app_data = None')
 source=p.once(source,"    (backup / 'server.py').write_bytes(previous)","    (backup / 'server.py').write_bytes(previous)\n    (backup/'index.html').write_bytes((root/'static/index.html').read_bytes())")
 source=p.once(source,'    os.kill(pid, signal.SIGTERM)',"    index_pending=root/'static/index.research-pending'\n    index_pending.write_bytes(index_data);index_pending.chmod(0o644)\n    os.replace(index_pending,root/'static/index.html')\n    os.kill(pid, signal.SIGTERM)")
 source=p.once(source,'    if target.read_bytes() != data or',"    if (root/'static/index.html').read_bytes()!=index_data:raise RuntimeError('index mismatch')\n    if target.read_bytes() != data or")
 return source
install.remote_installer=remote_installer

def verify_package():
 m=json.loads(p.read(p.OUT/'manifest.json'))
 assert m['schema']=='mic_ai.research_suite.v1' and m['pair_compatibility_ids']==list(p.NEW)
 assert m['built'] and m['selftest_pass'] and m['actuating_algorithms']==['VF_FIXED']
 assert not m['requested_other_algorithms_implemented']
 for k in ('calibration_changed','thresholds_changed','uart_changed','motor_control_changed','adc_sampling_changed','as5600_enabled','ai_control_enabled'):assert m[k] is False,k
 for table in ('source_sha256','build_sha256','verification_sha256','tooling_sha256','evidence_sha256'):
  for rel,h in m.get(table,{}).items():assert p.sha(p.OUT/rel)==h,rel
 for rel,h in json.loads(p.read(p.OUT/'archive_references.json')).items():assert p.sha(p.ROOT/rel)==h
 images=[]
 for folder,name,build in [('uno','unoq_mcsdk_scalar',p.NEW[0]),('nucleo','ACIM-NUCLEOG431RB-IPM15B-VF_OL',p.NEW[1])]:
  b=json.loads((p.OUT/'build'/folder/(name+'.build-manifest.json')).read_text(encoding='utf-8-sig'));assert b['firmware_build_id']==build
  if folder=='nucleo':assert b['build_errors']==b['build_warnings']==0
  for item in b['artifacts']:assert p.sha(p.OUT/'build'/folder/item['file'])==item['sha256'].lower()
  images.append(p.OUT/'build'/folder/(b['flash_artifact'] if folder=='uno' else name+'.hex'))
 return tuple(images)

install.verify_package=verify_package

def main():
 code=install.main()
 if code and '--outdir' in sys.argv:
  out=Path(sys.argv[sys.argv.index('--outdir')+1]).resolve()
  record=json.loads(p.read(out/'report.json'))
  if (record.get('uno_readback_verified') and record.get('nucleo_readback_verified') and record.get('calibration_unchanged')
      and str(record.get('error','')).startswith('Runtime verification pending:')):
   from install_sd_break_filter_usb_pair import restart_owned_hmi
   recovery=dict(motor_commands=0,mcu_reset_commands=0,additional_flash_commands=0,hmi_restart=restart_owned_hmi(),passed=False)
   for _ in range(10):
    try:
     s=install.io.live_status()
     if (s.get('fw_build'),s.get('mc_fw_build'))==p.NEW and install.precheck(s)[0]:
      recovery.update(passed=True,status=s);break
    except Exception as e:recovery['last_error']=str(e)
    time.sleep(.5)
   p.write(out/'runtime_recovery.json',json.dumps(recovery,indent=2))
   if recovery['passed']:return 0
 return code

from pathlib import Path
if __name__=='__main__':raise SystemExit(main())
