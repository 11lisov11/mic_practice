"""Install sealed2709/2710 in confirmed discharged USB state; no motor/CLEAR."""
import importlib.util,json,math,subprocess,sys
from pathlib import Path
import install_current_shunt_monitor as install
import prepare_i2c_persistent_pe as p

def guard_source():
 s=p.read(p.ROOT/'tools/uart_resync_fix/update_guard.py').replace(
  '((2026101805,2026101804),(2026101807,2026101806))',
  '((2026102707,2026102708),(2026102709,2026102710))')
 # A retained FE snapshot is not a motor-start permission. On this physically
 # discharged bench, fresh OFF telemetry and its unchanged saved fault can be
 # archived/programmed without sending CLEAR. Never alter the status values.
 a="        for key in ('mc_uart_error_flags','bp_uart_error_flags'):\n            if s[key]!=0: return False,'active UART hardware error: '+key"
 b="""        retained_fe=(s.get('mc_diag_valid')==s.get('bp_diag_valid')==1
            and s.get('mc_transport_fault')==s.get('bp_transport_fault')==4
            and s.get('mc_fault')==s.get('bp_fault')==5
            and s.get('mc_fault_reason')==s.get('mc_last_bad_reason')==12
            and s.get('mc_uart_error_flags')==s.get('bp_uart_error_flags')==2
            and s.get('mc_last_uart_error_flags')==s.get('bp_last_uart_error_flags')==2
            and s.get('mc_bad_cnt')==s.get('bp_bad_cnt')==1
            and s.get('mc_fault_current_mask')==s.get('mc_fault_occurred_mask')==0
            and s.get('uno_rx_hw_flags')==s.get('uno_rx_hw_errors')==0)
        for key in ('mc_uart_error_flags','bp_uart_error_flags'):
            if s[key]!=0 and not retained_fe:return False,'unrecognized UART diagnostic: '+key"""
 s=p.once(s,a,b)
 return p.once(s,'not (reset_timeout or known_crc)','not (reset_timeout or known_crc or retained_fe)')

install.ROOT,install.C,install.OLD,install.NEW=p.ROOT,p.OUT,p.OLD,p.NEW
install.GUARD=guard_source();exec(install.GUARD,install.__dict__)

def verify_package():
 c=p.OUT;m=json.loads(p.read(c/'manifest.json'))
 assert m['schema']=='mic_ai.i2c_persistent_pe.v1' and m['pair_compatibility_ids']==list(p.NEW) and m['built'] and m['selftest_pass'] and not m['installed']
 assert m['successful_read_keeps_pe_enabled'] and m['error_cleanup_policy_unchanged']
 for k in ('sensor_feedback_control','motor_control_changed','thresholds_changed','calibration_changed','uart_command_protocol_changed','bkin_changed','adc_trigger_changed','pwm_ccr123_changed','deadtime_changed','watchdogs_changed'):assert m[k] is False,k
 for table in ('source_sha256','build_sha256','verification_sha256'):
  for rel,d in m[table].items():assert p.sha(c/rel)==d,rel
 for rel,d in m['historical_records_preserved'].items():assert p.sha(c/'preserved_records'/rel)==d,rel
 images=[]
 for folder,name,fw in [('uno','unoq_mcsdk_scalar',p.NEW[0]),('nucleo','ACIM-NUCLEOG431RB-IPM15B-VF_OL',p.NEW[1])]:
  b=json.loads(p.read(c/'build'/folder/(name+'.build-manifest.json')));assert b['firmware_build_id']==fw
  for item in b['artifacts']:assert p.sha(c/'build'/folder/item['file'])==item['sha256'].lower()
  images.append(c/'build'/folder/(b['flash_artifact'] if folder=='uno' else name+'.hex'))
 assert json.loads(p.read(c/'verification/report.json'))['passed'];return tuple(images)
install.verify_package=verify_package

def main():
 if '--verify-package-only' in sys.argv:return install.main()
 if '--confirm-j1-off-meter-below-20v-both-usb' in sys.argv and '--outdir' in sys.argv:
  verify_package();adb=['adb','-s',install.io.UNO_SERIAL]
  assert subprocess.check_output(adb+['get-state'],text=True).strip()=='device'
  subprocess.run(adb+['forward','tcp:18080','tcp:8080'],check=True,capture_output=True)
  install.io.URL='http://127.0.0.1:18080'
  spec=importlib.util.spec_from_file_location('preserve_live',p.ROOT/'tools/pe_release_capture/preserve_live.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  complete=module.complete
  def full(s):
   if not complete(s) or s.get('enc_release_decode_valid')!=1 or s.get('enc_bus_clear_decode_valid')!=1:return False
   if s.get('enc_fault_first_hex','-')!='-' and s.get('enc_release_first_hex','-')=='-':return False
   if s.get('enc_bus_clear_hex','-')!='-' and not s.get('enc_bus_clear_record'):return False
   return True
  module.complete=full
  out=Path(sys.argv[sys.argv.index('--outdir')+1]).resolve()
  def guard(s):
   if (s.get('fw_build'),s.get('mc_fw_build'))!=p.OLD:return False,'unexpected installed pair'
   return install.precheck(s)
  archive=out.with_name(out.name+'_preserved_live');module.preserve(install.io.live_status,guard,archive)
  samples=[json.loads(line) for line in p.read(archive/'samples.jsonl').splitlines()]
  # Refuse a changing UART rejection stream; retained bits are not erased or
  # relabeled as live USART.ISR. Keep exact raw/decoded records above.
  for key in ('mc_bad_cnt','bp_bad_cnt','mc_uart_error_flags','mc_last_uart_error_flags','uno_rx_hw_errors'):
   assert len({s.get(key) for s in samples[-3:]})==1,'UART diagnostics changed during archival: '+key
  for key in ('enc_fault_first_hex','enc_fault_pwm_hex','enc_release_first_hex','enc_release_pwm_hex','enc_bus_clear_hex'):
   assert len({s.get(key) for s in samples[-3:]})==1,'Frozen capture changed during archival: '+key
 # Do not call the historical automatic serial close/open fallback. It removes
 # MCU method registrations even when RPC is healthy and a fault is only saved.
 return install.main()
if __name__=='__main__':raise SystemExit(main())
