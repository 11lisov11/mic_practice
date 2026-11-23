"""Seal completed OFF verification from saved evidence; no hardware access."""
import hashlib,json
import prepare_foc_runtime_fix as p

def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()

def main():
 install=p.OUT/'hardware_install_r2';idle=p.OUT/'idle_verification_r2'
 boot=p.OUT/'boot_latch_diagnostics_r1';link=p.OUT/'idle_link_confirm_r1'
 i=json.loads(p.read(install/'install_report.json'));v=json.loads(p.read(idle/'report.json'))
 l=json.loads(p.read(link/'report.json'));readback=json.loads(p.read(boot/'native_readback_guard/report.json'))
 assert i['passed'] and v['passed'] and l['passed'] and readback['passed']
 assert i['uno_flash_commands']==i['nucleo_flash_commands']==1
 assert i['uno_readback_verified'] and i['nucleo_readback_verified']
 assert i['calibration_before']==i['calibration_after']
 assert i['start_commands']==i['clear_commands']==v['start_commands']==v['clear_commands']==0
 s=l['after'];t=s['foc_runtime']
 assert (s['fw_build'],s['mc_fw_build'])==p.NEW
 assert s['state']=='SAFE' and s['pwm']==s['run_id']==s['hmi_hv_armed']==0
 assert s['algorithm_selected']==s['algorithm_requested']==2 and s['algorithm_fault']==0
 assert s['mc_current_zero_ready']==1 and s['mc_sd_live']['level']=='HIGH'
 assert s['mc_sd_live']['config_ok'] and s['mc_sd_live']['break_irq_enabled']
 assert s['mc_fault_current_mask']==4 and 0<=s['vdc']<=20
 assert s['mc_bad_integrity']==s['mc_uart_error_flags']==s['mc_transport_fault']==0
 assert t['available'] and t['source']=='OFF_synthetic_CPU_probe' and t['observer_steps']==64
 assert t['meter_errors']==0 and t['first_fault'] is None
 assert (boot/'native_sram_with_latch.bin').stat().st_size==32768
 assert (boot/'UART_reject.bin').stat().st_size==320
 preserved=json.loads(p.read(p.OUT/'verification/preserved_captures_sha256.json'))
 for rel,h in preserved.items():assert sha(p.ROOT/rel)==h,rel
 for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert sha(p.OUT/rel)==h,rel
 m=json.loads(p.read(p.OUT/'manifest.json'))
 for rel,h in m['artifacts'].items():assert sha(p.OUT/rel)==h,rel
 out=p.OUT/'installation_verified_r1';out.mkdir(exist_ok=False)
 new={}
 for folder in (install,idle,boot,link,p.OUT/'idle_verification_r1',p.OUT/'hardware_install_r1'):
  for f in folder.rglob('*'):
   if f.is_file():new[f.relative_to(p.ROOT).as_posix()]=sha(f)
 p.write(out/'preserved_installation_evidence.json',json.dumps(new,indent=2))
 r=dict(passed=True,pair=list(p.NEW),uno_flash_commands=1,nucleo_flash_commands=1,
  uno_readback_verified=True,nucleo_full_passive_readback_verified=True,
  native_flash_sha256=readback['native_image_sha256'],native_comparison=readback['image_comparison'],
  calibration_unchanged=True,preserved_prior_files=len(preserved),preserved_new_files=len(new),
  initial_USB_enumeration_attempt_made_no_writes=True,
  initial_boot_UART_ORE_and_SRAM_preserved=True,controlled_native_resets_after_install=1,
  initial_ORE_cause_not_proven=True,post_reset_link_verified_seconds=20,
  link_samples=l['samples'],UART_integrity_errors=0,UART_hardware_flags=0,transport_fault=0,
  startup_diagnostic_reject_counts_stable=True,OFF_case_count=64,CPU_IRQ=t,
  fast_kernel_cycles=s['algorithm_fast_cycles'],observer_legacy_max_cycles=s['algorithm_observer_cycles'],
  state=s['state'],pwm=0,run_id=0,vbus=s['vdc'],active_fault_mask=4,
  expected_active_fault='MC_UNDER_VOLT while J1 OFF',algorithm_selected=2,algorithm_fault=0,
  auto_zero_ready=True,SD_HIGH=True,BIE_enabled=True,protection_config_ok=True,
  start_commands=0,clear_commands=0,arm_commands=0,hardware_under_PWM_validated=False)
 p.write(out/'report.json',json.dumps(r,indent=2))
 m.update(installed=True,flash_commands=2,uno_readback_verified=True,nucleo_readback_verified=True,
  calibration_unchanged=True,target_timing_measured=True,hardware_CPU_IRQ_split_measured=True,
  hardware_CPU_IRQ_split_context='OFF_synthetic_CPU_probe',hardware_under_PWM_validated=False,
  installation_report='installation_verified_r1/report.json',
  boot_ORE_archived_before_one_reset=True,controlled_native_resets_after_install=1,
  new_capture_files_preserved=len(new),no_motor_starts_or_clears=True)
 p.write(p.OUT/'manifest.json',json.dumps(m,indent=2));print(json.dumps(r))

if __name__=='__main__':main()
