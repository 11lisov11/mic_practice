"""Seal completed installation evidence; no hardware commands."""
import hashlib
import json
import shutil
import prepare_boot_reset_capture as p


def sha(f):
    with f.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    out=p.OUT/'installation_verified_r1';out.mkdir(exist_ok=False)
    install=json.loads(p.read(p.OUT/'hardware_install_r1/install_report.json'))
    check=json.loads(p.read(p.OUT/'post_install_readback_r1/report.json'))
    assert install['passed'] and check['passed']
    assert install['uno_flash_commands']==install['nucleo_flash_commands']==1
    assert install['uno_readback_verified'] and install['nucleo_readback_verified'] and install['calibration_unchanged']
    assert all(check[k]==0 for k in ('START','CLEAR','ARM','RESET','flash'))
    manifest=json.loads(p.read(p.OUT/'manifest.json'));assert manifest['built'] and not manifest['installed']
    for rel,digest in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert sha(p.OUT/rel)==digest,rel
    for rel,digest in manifest['artifacts'].items():assert sha(p.OUT/rel)==digest,rel
    preserved=json.loads(p.read(p.OUT/'verification/preserved_captures_sha256.json'))
    for rel,digest in preserved.items():assert sha(p.ROOT/rel)==digest,rel
    shutil.copy2(p.OUT/'manifest.json',out/'manifest_before_install.json')
    shutil.copy2(p.OUT/'release_evidence_sha256.json',out/'prepared_release_evidence_sha256.json')
    s=json.loads(p.read(p.OUT/'post_install_readback_r1/final_status.json'))['data']
    assert (s['fw_build'],s['mc_fw_build'])==p.NEW and s['state']=='SAFE' and s['pwm']==0
    assert s['run_id']==0 and s['hmi_hv_armed']==0 and s['mc_current_zero_ready']==1
    assert s['mc_fault_current_mask']==s['mc_fault_occurred_mask']==0
    assert s['mc_sd_live']['level']=='HIGH' and s['mc_sd_live']['break_irq_enabled']
    assert s['native_boot']['available'] and s['native_boot']['fresh']
    assert s['native_boot']['current_flags_cleared'] and check['current_RCC_CSR']&0xfe000000==0
    assert s['algorithm_qualification']==128 and s['algorithm_profile_crc']==1354279011
    assert s['foc_runtime']['source']=='OFF_synthetic_CPU_probe' and s['foc_runtime']['observer_steps']==64
    assert s['foc_runtime']['first_fault'] is None and s['foc_runtime']['meter_errors']==0
    report=dict(passed=True,pair=list(p.NEW),installed=True,uno_readback_verified=True,
        native_readback_verified=True,native_flash_sha256=check['independent_native_readback']['native_image_sha256'],
        independent_native_RAM_record_matches_UART=True,native_boot=s['native_boot'],
        linux_boot_id=s.get('linux_boot_id'),zero_ready=1,zero_attempts=s['mc_current_zero_attempts'],
        SD=s['mc_sd_live'],fault_masks=[0,0],CPU_OFF=s['foc_runtime'],
        calibration_unchanged=True,old_files_verified=len(preserved),thresholds_changed=False,
        START=0,CLEAR=0,ARM=0,uno_flash_commands=1,nucleo_flash_commands=1,
        programming_resets_used=True,additional_test_resets=0,
        J1_user_confirmed_OFF=True,PC_USB_connected=True,J4_15V_left_ON=True,
        old_spontaneous_reset_cause_identified=False,programming_boot_is_baseline=True,
        warm_reset_retention_not_separately_tested=True,physical_FOC_5s_not_proven=True)
    p.write(out/'report.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    manifest.update(installed=True,readback_verified=True,calibration_unchanged=True,
        hardware_commands=2,programming_resets_used=True,additional_test_resets=0,
        installed_pair=list(p.NEW),hardware_boot_telemetry_validated=True,
        hardware_reset_classification_not_yet_validated=True,
        installation_evidence='installation_verified_r1/report.json')
    p.write(p.OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n')
    hashes={}
    for folder in ('hardware_install_r1','post_install_readback_r1','installation_verified_r1'):
        for f in (p.OUT/folder).rglob('*'):
            if f.is_file():hashes[f.relative_to(p.OUT).as_posix()]=sha(f)
    hashes['manifest.json']=sha(p.OUT/'manifest.json')
    p.write(out/'saved_files_sha256.json',json.dumps(hashes,indent=2)+'\n')
    print(json.dumps(dict(passed=True,installed=True,pair=list(p.NEW),old_files_verified=len(preserved),new_evidence_files=len(hashes),START=0,CLEAR=0)))


if __name__=='__main__':main()
