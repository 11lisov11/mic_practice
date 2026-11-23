"""Seal verified3015/3016 installation; filesystem only, no motor commands."""
import hashlib,json,shutil
import prepare_observer_trace as p


def sha(f):
    with f.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    out=p.OUT/'installation_verified_r1';out.mkdir(exist_ok=False)
    i=json.loads(p.read(p.OUT/'hardware_install_r2/install_report.json'))
    v=json.loads(p.read(p.OUT/'post_install_readback_r1/report.json'))
    initial=json.loads(p.read(p.OUT/'hardware_install_r1/install_report.json'))
    assert i['passed'] and v['passed'] and initial['uno_flash_commands']==initial['nucleo_flash_commands']==0
    assert i['uno_flash_commands']==i['nucleo_flash_commands']==1
    assert i['uno_readback_verified'] and i['nucleo_readback_verified'] and i['calibration_unchanged']
    assert all(v[k]==0 for k in ('START','CLEAR','ARM','RESET','flash','configuration_commands'))
    m=json.loads(p.read(p.OUT/'manifest.json'));assert m['built'] and not m['installed']
    for rel,digest in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert sha(p.OUT/rel)==digest,rel
    for rel,digest in m['artifacts'].items():assert sha(p.OUT/rel)==digest,rel
    prior=json.loads(p.read(p.OUT/'verification/preserved_captures_sha256.json'))
    for rel,digest in prior.items():assert sha(p.ROOT/rel)==digest,rel
    s=json.loads(p.read(p.OUT/'post_install_readback_r1/final_status.json'))['data']
    assert (s['fw_build'],s['mc_fw_build'])==p.NEW and s['state']=='SAFE' and s['pwm']==0
    assert s['run_id']==s['hmi_hv_armed']==0 and s['mc_current_zero_ready']==1
    assert s['mc_fault_current_mask']==s['mc_fault_occurred_mask']==0
    assert s['mc_sd_live']['level']=='HIGH' and s['mc_sd_live']['break_irq_enabled']
    assert s['observer_trace']==dict(available=False,reason='not_received') and s['mc_observer_trace_complete']==0
    assert v['recorder_RAM_empty'] and s['foc_runtime']['source']=='OFF_synthetic_CPU_probe'
    assert s['foc_runtime']['observer_steps']==64 and s['foc_runtime']['first_fault'] is None and s['foc_runtime']['meter_errors']==0
    shutil.copy2(p.OUT/'manifest.json',out/'manifest_before_install.json')
    shutil.copy2(p.OUT/'release_evidence_sha256.json',out/'prepared_release_evidence_sha256.json')
    report=dict(passed=True,pair=list(p.NEW),installed=True,
        initial_enumeration_attempt_writes=0,uno_flash_commands=1,nucleo_flash_commands=1,
        readback_both_verified=True,independent_native_flash_sha256=v['independent_native_readback']['native_image_sha256'],
        recorder_RAM_empty=True,recorder_state_bytes=1804,observer_trace=s['observer_trace'],
        observer_trace_good=s['mc_observer_trace_good'],observer_trace_bad=s['mc_observer_trace_bad'],
        zero_ready=1,zero_attempts=s['mc_current_zero_attempts'],fault_masks=[0,0],SD=s['mc_sd_live'],
        native_boot=s['native_boot'],OFF_CPU=s['foc_runtime'],OFF_fast_cycles=s['algorithm_fast_cycles'],
        calibration_unchanged=True,old_files_verified=len(prior),thresholds_changed=False,
        START=0,CLEAR=0,ARM=0,extra_test_resets=0,programming_resets_used=True,
        real_RUN_observer_capture_not_yet_validated=True,target_recording_execution_time_not_measured=True,
        physical_state=dict(J1='OFF',J4_15V='ON',both_USB_PC=True),
        evidence='post_install_readback_r1/report.json')
    p.write(out/'report.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    m.update(installed=True,readback_verified=True,calibration_unchanged=True,
        hardware_commands=dict(uno_flash=1,nucleo_flash=1,programming_resets_used=True,START=0,CLEAR=0,ARM=0,extra_test_resets=0),
        hardware_idle_diagnostics_verified=True,hardware_recorder_empty_verified=True,
        installation_evidence='installation_verified_r1/report.json')
    p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    hashes={}
    for folder in ('hardware_install_r1','hardware_install_r2','post_install_readback_r1','installation_verified_r1'):
        for f in (p.OUT/folder).rglob('*'):
            if f.is_file():hashes[f.relative_to(p.OUT).as_posix()]=sha(f)
    hashes['manifest.json']=sha(p.OUT/'manifest.json')
    p.write(out/'saved_files_sha256.json',json.dumps(hashes,indent=2)+'\n')
    print(json.dumps(dict(passed=True,installed=True,pair=list(p.NEW),old_files_verified=len(prior),new_evidence_files=len(hashes),START=0,CLEAR=0)))


if __name__=='__main__':main()
