"""Record completed installation and passive readback; no motor commands."""
import json,hashlib,urllib.request
import prepare_foc_start_epoch_fix as p
from probe_native_programming_state import probe

def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()

def main():
 install_dir=p.OUT/'hardware_install_r3';idle_dir=p.OUT/'idle_verification_r1'
 install=json.loads(p.read(install_dir/'install_report.json'))
 idle=json.loads(p.read(idle_dir/'report.json'))
 assert install['passed'] and idle['passed']
 assert install['uno_flash_commands']==install['nucleo_flash_commands']==1
 assert install['uno_readback_verified'] and install['nucleo_readback_verified']
 assert install['calibration_before']==install['calibration_after']
 assert install['start_commands']==install['clear_commands']==0
 assert idle['start_commands']==idle['clear_commands']==idle['arm_commands']==0
 out=p.OUT/'post_install_readback_r1';out.mkdir(exist_ok=False)
 native=probe(p.OUT,out/'native',
  'same confirmed J1 OFF / meter below20V / both USB state; passive post-install readback only')
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with opener.open('http://192.168.1.138:8080/api/status',timeout=8) as response:payload=json.load(response)
 p.write(out/'status.json',json.dumps(payload,ensure_ascii=False,indent=2))
 assert payload['ok'];s=payload['data']
 assert (s['fw_build'],s['mc_fw_build'])==p.NEW
 assert s['state']=='SAFE' and s['pwm']==0 and s['run_id']==0
 assert s['hmi_hv_armed']==0 and not(s['bp_status']&0x22)
 assert 0<=s['vdc']<=20 and 0<=s['mc_age_ms']<300
 assert s['algorithm_selected']==s['algorithm_requested']==2 and s['algorithm_fault']==0
 assert s['algorithm_qualification']==128 and s['algorithm_profile_crc']==1354279011
 assert s['mc_current_zero_ready']==1
 assert s['mc_sd_live']['level']=='HIGH' and s['mc_sd_live']['break_irq_enabled']
 assert s['mc_sd_live']['config_ok']
 assert s['bp_bad_integrity']==s['bp_transport_fault']==0
 assert s['rpc_response_timeouts']==s['rpc_send_timeouts']==0
 assert s['mc_fault_current_mask']==4 # expected under-voltage with J1 OFF
 m=json.loads(p.read(p.OUT/'manifest.json'))
 for rel,h in m['artifacts'].items():assert sha(p.OUT/rel)==h,rel
 for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert sha(p.OUT/rel)==h,rel
 preserved=json.loads(p.read(p.OUT/'verification/preserved_captures_sha256.json'))
 for rel,h in preserved.items():assert sha(p.ROOT/rel)==h,rel
 report=dict(passed=True,pair=list(p.NEW),uno_flash_commands=1,nucleo_flash_commands=1,
  start_commands=0,clear_commands=0,arm_commands=0,
  uno_readback_verified=True,native_full_passive_readback_verified=True,
  native_readback_sha256=native['native_image_sha256'],native_image_comparison=native['image_comparison'],
  calibration_unchanged=True,preserved_files_verified=len(preserved),
  off_timing_cases=s['foc_timing_cases'],off_kernel_cycles=s['algorithm_fast_cycles'],
  off_observer_cycles=s['algorithm_observer_cycles'],auto_zero_ready=True,
  sd_high=True,break_irq_enabled=True,protection_config_ok=True,
  algorithm_selected=2,algorithm_fault=0,bus_volts=s['vdc'],
  active_fault_mask=4,active_fault_explanation='MC_UNDER_VOLT expected with confirmed J1 OFF',
  physical_FOC_after_fix_validated=False)
 p.write(out/'report.json',json.dumps(report,indent=2))
 m.update(installed=True,target_timing_measured=True,physical_trial_after_fix=False,
  installation_report=str((install_dir/'install_report.json').relative_to(p.OUT)),
  idle_verification_report=str((idle_dir/'report.json').relative_to(p.OUT)),
  post_install_report=str((out/'report.json').relative_to(p.OUT)),
  installed_without_start_or_clear=True,readback_verified=True,calibration_unchanged=True)
 p.write(p.OUT/'manifest.json',json.dumps(m,indent=2));print(json.dumps(report))

if __name__=='__main__':main()
