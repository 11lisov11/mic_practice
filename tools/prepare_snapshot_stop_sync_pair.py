"""Gate passive pages on the safe-off state actually published to Uno."""
import argparse,json,shutil
from pathlib import Path
from prepare_pwm_filter_pair import sha,write,change
from prepare_ipm_break_wifi import source_hashes
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261014/pwm_filter_pair_r6'

def prepare(out):
    assert json.loads((BASE/'qualification_frame_fix/report.json').read_text())['pass']
    assert json.loads((BASE/'reject_selftest_r2/report.json').read_text())['actual_receiver_packet_hmi_decode_pass']
    out.mkdir(parents=True,exist_ok=False)
    pairs={'production':((2026101409,2026101408),(2026101411,2026101410)),
           'fixture':((2026101494,2026101495),(2026101492,2026101493))}
    for name,(old,new) in pairs.items():
        original=json.loads((BASE/name/'manifest.json').read_text())
        assert source_hashes(BASE/name/'nucleo')==original['nucleo_source_sha256']
        assert source_hashes(BASE/name/'UNOQ_MOTOR')==original['uno_source_sha256']
        p=out/name
        for tree in ('nucleo','UNOQ_MOTOR','web_hmi'):
            shutil.copytree(BASE/name/tree,p/tree,ignore=shutil.ignore_patterns('Debug','Release','.metadata','__pycache__','server.py.before_frame_width_fix'))
        change(p/'nucleo/Src/main.c',f'MIC_NUCLEO_FW_BUILD_ID {old[1]}UL',f'MIC_NUCLEO_FW_BUILD_ID {new[1]}UL')
        change(p/'UNOQ_MOTOR/UNOQ_MOTOR.ino',f'FW_BUILD_ID = {old[0]}U',f'FW_BUILD_ID = {new[0]}U')
        for tree in ('nucleo/Inc','UNOQ_MOTOR'):
            change(p/tree/'break_wire.h',f'BW_NUCLEO_BUILD {old[1]}UL',f'BW_NUCLEO_BUILD {new[1]}UL')
        peer=p/'UNOQ_MOTOR/nucleo_fault_diagnostics.h'
        if name=='production':change(peer,f'build == {old[1]}U;',f'build == {old[1]}U || build == {new[1]}U;')
        else:change(peer,'build == 2026101408U;', 'build == 2026101408U || build == 2026101410U || build == 2026101493U;')
        main=p/'nucleo/Src/main.c'
        change(main,'static uint32_t mic_break_diag_tx_errors;',
          'static uint32_t mic_break_diag_tx_errors;\nstatic bool mic_last_control_reply_safe_off;')
        change(main,'  if (uno_link.command_enabled || mic_break_start_window != 0U ||',
          '  if (!mic_last_control_reply_safe_off || uno_link.command_enabled || mic_break_start_window != 0U ||')
        change(main,'  if (tx_status == HAL_OK) mic_send_break_page(now_ms);',
          '''  /* Publish diagnostics only after an off reply, not an IRQ transition
     which occurred while a previous on reply was being transmitted. */
  mic_last_control_reply_safe_off = (tx_status == HAL_OK) && ((status & 0x22U) == 0U);
  if (tx_status == HAL_OK) mic_send_break_page(now_ms);''')
        web=p/'web_hmi/server.py';text=web.read_text()
        text=text.replace('(2026101102, 2026101204, 2026101404, 2026101499, 2026101406, 2026101497, 2026101408, 2026101495)',
          '(2026101102, 2026101204, 2026101404, 2026101499, 2026101406, 2026101497, 2026101408, 2026101495, 2026101410, 2026101493)')
        text=text.replace('in (2026101404, 2026101499, 2026101406, 2026101497, 2026101408, 2026101495):',
          'in (2026101404, 2026101499, 2026101406, 2026101497, 2026101408, 2026101495, 2026101410, 2026101493):')
        if name=='fixture':text=text.replace('(2026101494, 2026101495)','(2026101492, 2026101493)')
        write(web,text)
        manifest=dict(original,pair=list(new),nucleo_source_sha256=source_hashes(p/'nucleo'),
          uno_source_sha256=source_hashes(p/'UNOQ_MOTOR'),hmi_sha256=sha(web),sender_requires_published_safe_off=True)
        write(p/'manifest.json',json.dumps(manifest,indent=2)+'\n')
        assert (p/'nucleo/Inc/break_wire.h').read_bytes()==(p/'UNOQ_MOTOR/break_wire.h').read_bytes()
    shutil.copytree(BASE/'fastmath',out/'fastmath')
    write(out/'manifest.json',json.dumps(dict(production_pair=[2026101411,2026101410],fixture_pair=[2026101492,2026101493],
       predecessor_pair=[2026101409,2026101408],predecessor_hmi_sha256=sha(BASE/'production/web_hmi/server.py'),
       hardware_commands=0,hv_release_approved=False),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--outdir',type=Path,required=True);a=p.parse_args();prepare(a.outdir.resolve())
