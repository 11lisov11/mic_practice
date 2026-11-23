"""Separate CRC-verified single-NE metadata from the damaged-packet recovery budget."""
import json
import shutil
from pathlib import Path
from prepare_pwm_filter_pair import change,write,sha
from prepare_ipm_break_wifi import source_hashes

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261014/uart_recovery_working_pair_r1'
OUT=ROOT/'artifacts/live_bench_20261014/uart_recovery_working_pair_r2'
PAIR=(2026101415,2026101414)

def advisory_policy(header):
    old='''  if (rx->ne_bytes != 1 || rx->clean_run_frames < UV3_CLEAN_REQUIRED ||
      rx->frame[3] == 8 || !uv3_take_recovery_budget(rx, now_ms)) return false;'''
    new='''  (void)now_ms;
  /* Full CRC, version and fresh-sequence checks already passed. A single
     hardware NE mark on that verified packet is observable metadata, not a
     damaged/lost command. Keep its counter without spending discard budget. */
  if (rx->ne_bytes != 1 || rx->clean_run_frames < UV3_CLEAN_REQUIRED ||
      rx->frame[3] == 8 || !rx->bounded_noise || rx->fault_latched) return false;'''
    assert header.count(old)==1
    header=header.replace(old,new)
    old='''  if (rx->ne_bytes) rx->clean_run_frames = 0;
  else if (rx->clean_run_frames < UV3_CLEAN_REQUIRED) ++rx->clean_run_frames;'''
    new='''  /* A verified/committed packet does not erase established link
     qualification just because its UART sampling carried an NE mark. */
  if (!rx->ne_bytes && rx->clean_run_frames < UV3_CLEAN_REQUIRED) ++rx->clean_run_frames;'''
    assert header.count(old)==1
    return header.replace(old,new).replace('Every recovered event shares one sliding budget.',
        'Every discarded packet shares one sliding budget.')

def prepare():
    mf=json.loads((BASE/'manifest.json').read_text())
    assert mf['installed'] and mf['pair']==[2026101413,2026101412]
    assert json.loads((BASE/'installation/report.json').read_text())['idle_qualification_complete']
    for tree,key in [('nucleo','nucleo_source_sha256'),('UNOQ_MOTOR','uno_source_sha256')]:
        assert source_hashes(BASE/tree)==mf[key]
    assert sha(BASE/'web_hmi/server.py')==mf['hmi_sha256']
    OUT.mkdir(exist_ok=False)
    for tree in ('nucleo','UNOQ_MOTOR','web_hmi'):
        shutil.copytree(BASE/tree,OUT/tree,ignore=shutil.ignore_patterns('Debug','Release','__pycache__','.metadata'))
    for tree in ('nucleo/Inc','UNOQ_MOTOR'):
        p=OUT/tree/'uart_v3_transport.h';write(p,advisory_policy(p.read_text()))
        change(OUT/tree/'break_wire.h','BW_NUCLEO_BUILD 2026101412UL','BW_NUCLEO_BUILD 2026101414UL')
    change(OUT/'nucleo/Src/main.c','MIC_NUCLEO_FW_BUILD_ID 2026101412UL','MIC_NUCLEO_FW_BUILD_ID 2026101414UL')
    change(OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino','FW_BUILD_ID = 2026101413U','FW_BUILD_ID = 2026101415U')
    change(OUT/'UNOQ_MOTOR/nucleo_fault_diagnostics.h','build == 2026101412U;',
        'build == 2026101412U || build == 2026101414U;')
    web=OUT/'web_hmi/server.py'
    change(web,'(2026101413, 2026101412),','(2026101413, 2026101412),\n        (2026101415, 2026101414),')
    change(web,'2026101493, 2026101412)','2026101493, 2026101412, 2026101414)')
    anchor='    if cfg.profile == ARM_PROFILE_HV and _as_int(data or {}, "mc_fw_build", -1) == 2026101412'
    change(web,anchor,
        '    if cfg.profile == ARM_PROFILE_HV and _as_int(data or {}, "mc_fw_build", -1) == 2026101414 and _as_int(data or {}, "fw_build", -1) != 2026101415:\n'
        '        return False, "working motor-controller image requires its matching supervisory firmware"\n'+anchor)
    hashes=source_hashes(OUT/'nucleo')
    changed=[p for p,h in hashes.items() if mf['nucleo_source_sha256'].get(p)!=h]
    assert sorted(changed)==['Inc/break_wire.h','Inc/uart_v3_transport.h','Src/main.c']
    new=dict(mf,pair=list(PAIR),predecessor_pair=mf['pair'],predecessor_candidate=str(BASE),
      nucleo_source_sha256=hashes,uno_source_sha256=source_hashes(OUT/'UNOQ_MOTOR'),
      hmi_sha256=sha(web),source_only=True,installed=False,qualification_pending=True,
      intact_ne_is_advisory=True,recovery_budget_for_discarded_packets_only=True,
      calibration_points_preserved=True,measurement_and_pwm_sources_unchanged=True,
      no_fixture_firmware=True,hardware_commands=0)
    write(OUT/'manifest.json',json.dumps(new,indent=2)+'\n')
    print(json.dumps(dict(pair=new['pair'],installed=False,hardware_commands=0,intact_ne_is_advisory=True)))

if __name__=='__main__':prepare()
