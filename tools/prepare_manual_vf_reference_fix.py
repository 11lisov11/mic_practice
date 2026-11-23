"""Correct the MCSDK V/f open-loop reference getter in one permanent working pair."""
import json
import shutil
from pathlib import Path
from prepare_ipm_break_wifi import source_hashes
from prepare_pwm_filter_pair import sha,write
from manual_scalar_sources import replace

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261015/manual_scalar_working_pair_r2'
OUT=ROOT/'artifacts/live_bench_20261015/manual_scalar_working_pair_r3'

def prepare():
    old=json.loads((BASE/'manifest.json').read_text());assert old['installed']
    assert not (OUT/'manifest.json').exists()
    OUT.mkdir(parents=True,exist_ok=True)
    for tree in ('nucleo','UNOQ_MOTOR','web_hmi'):
        shutil.copytree(BASE/tree,OUT/tree,ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
    f=OUT/'nucleo/Src/mc_interface.c'
    s=replace(f.read_text(),'''  int16_t hRefSpeed = 0;
  hRefSpeed = (int16_t)(pHandle->pACIM_VF->fRotorFreqRef_RPM * SPEED_UNIT / 60.0f);
  return hRefSpeed;''','''  /* VF_OL updates the ramp manager and flux frequency. fRotorFreqRef_RPM is
     updated only by VF_CL and stays zero in open loop. This is a field
     reference, never a measured rotor speed. */
  return ACIM_VF_GetMecSpeedRefUnit(pHandle->pACIM_VF);''')
    write(f,s)
    f=OUT/'nucleo/Src/main.c'
    s=replace(f.read_text(),'MIC_NUCLEO_FW_BUILD_ID 2026101502UL','MIC_NUCLEO_FW_BUILD_ID 2026101504UL')
    s=replace(s,'uno_link.ramp_target_speed_unit!=target_speed_unit && current==uno_link.ramp_target_speed_unit',
        'uno_link.ramp_target_speed_unit!=target_speed_unit && MC_HasRampCompletedMotor1()')
    write(f,s)
    for tree in ('nucleo/Inc','UNOQ_MOTOR'):
        f=OUT/tree/'break_wire.h';write(f,replace(f.read_text(),'BW_NUCLEO_BUILD 2026101502UL','BW_NUCLEO_BUILD 2026101504UL'))
    f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino'
    s=replace(f.read_text(),'FW_BUILD_ID = 2026101503U','FW_BUILD_ID = 2026101505U')
    s=replace(s,'g_bp_fw_build==2026101502U','g_bp_fw_build==2026101504U');write(f,s)
    f=OUT/'UNOQ_MOTOR/nucleo_fault_diagnostics.h';s=f.read_text().replace('2026101502U','2026101504U');write(f,s)
    f=OUT/'web_hmi/server.py';s=f.read_text()
    s=replace(s,'(2026101503, 2026101502),','(2026101503, 2026101502),\n        (2026101505, 2026101504),')
    s=replace(s,'2026101414, 2026101502)','2026101414, 2026101502, 2026101504)')
    s=replace(s,'"mc_fw_build", -1) == 2026101502 and _as_int(data or {}, "fw_build", -1) != 2026101503:',
        '"mc_fw_build", -1) in (2026101502,2026101504) and (_as_int(data or {}, "fw_build", -1),_as_int(data or {}, "mc_fw_build", -1)) != (2026101505,2026101504):')
    s=replace(s,'"fw_build",0)==2026101503','"fw_build",0)==2026101505')
    s=replace(s,'"mc_fw_build",0)==2026101502','"mc_fw_build",0)==2026101504');compile(s,str(f),'exec');write(f,s)
    mf=dict(old,pair=[2026101505,2026101504],predecessor_pair=old['pair'],predecessor_candidate=str(BASE),
        installed=False,source_only=True,qualification_pending=True,reuse_identical_nucleo_image=False,
        nucleo_source_sha256=source_hashes(OUT/'nucleo'),uno_source_sha256=source_hashes(OUT/'UNOQ_MOTOR'),
        hmi_sha256=sha(f),vf_open_loop_reference_fixed=True,
        measurement_and_pwm_sources_unchanged=False,core_adc_filter_pwm_protection_sources_unchanged=True,
        reference_getter_only_mc_sdk_change=True)
    shutil.copyfile(BASE/'browser_qualification.json',OUT/'browser_qualification.json')
    write(OUT/'manifest.json',json.dumps(mf,indent=2)+'\n');print(json.dumps({'prepared':str(OUT),'pair':mf['pair']}))

if __name__=='__main__':prepare()
