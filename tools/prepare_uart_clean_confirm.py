"""Offline UART correction: quarantine multi-NE commands until a fresh clean command.

No noisy command is executed by this new path. CRC-loss budget and watchdog stay
unchanged. This does not repair or establish the physical origin of line noise.
"""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'artifacts/live_bench_20261021/sd_dual_capture_r1'
OUT = ROOT/'artifacts/live_bench_20261021/uart_clean_confirm_r1'
OLD, NEW = (2026102101, 2026102102), (2026102103, 2026102104)

def read(p): return p.read_text(encoding='utf-8-sig')
def write(p, s): p.write_text(s, encoding='utf-8', newline='\n')
def once(s, a, b):
    assert s.count(a) == 1, (a, s.count(a))
    return s.replace(a, b)

def transport(s):
    s = once(s, '  UV3_CLEAN_REQUIRED = 3',
             '  UV3_CONFIRM_MS = 100,\n  UV3_CLEAN_REQUIRED = 3')
    s = once(s, '  uint8_t speculative_prefix;', '''  /* One CRC-valid but multi-NE command may be withheld during an already
     running, qualified link. Only a subsequent CLEAN, fresh full command can
     publish control. No deadline/budget is refreshed by the withheld frame. */
  bool confirm_pending;
  uint8_t confirm_sequence, confirm_loss_base;
  uint32_t confirm_started_ms;
  uint32_t deferred_noise_frames, clean_confirmations;
  uint8_t speculative_prefix;''')
    s = once(s, '  rx->fault_latched = true;',
             '  rx->confirm_pending = false;\n  rx->fault_latched = true;')
    s = once(s, '/* Every discarded packet shares one sliding budget.',
             '/* Every damaged/unqualified discarded packet shares one sliding budget.')
    s = once(s, '  if (rx->index != 0 && (uint32_t)(now_ms-rx->frame_started_ms)>UV3_FRAME_DEADLINE_MS) {', '''  if (rx->confirm_pending &&
      (uint32_t)(now_ms-rx->confirm_started_ms)>UV3_CONFIRM_MS)
    return uv3_trip(rx, UV3_NOISE_REJECTED);
  if (rx->index != 0 && (uint32_t)(now_ms-rx->frame_started_ms)>UV3_FRAME_DEADLINE_MS) {''')
    s = once(s, '''    const uint8_t advance = (uint8_t)(rx->frame[5] - rx->previous[5]);
    /* A gap is legal only after a specific observed discarded packet and
       within the unextended 300 ms deadline. Replays/backward jumps fail. */
    if (advance == 0 || advance > (uint8_t)(rx->recoverable_losses + 1U))''', '''    /* A withheld verified packet is an observed sequence, never a command.
       Anchor freshness to it so replaying that same packet cannot confirm it.
       Only genuinely observed damaged packets since that anchor grant a gap. */
    const uint8_t anchor=rx->confirm_pending ? rx->confirm_sequence : rx->previous[5];
    const uint8_t losses=rx->confirm_pending ?
        (uint8_t)(rx->recoverable_losses-rx->confirm_loss_base) : rx->recoverable_losses;
    const uint8_t advance = (uint8_t)(rx->frame[5] - anchor);
    if (advance == 0 || advance > (uint8_t)(losses + 1U))''')
    s = once(s, '  if (rx->ne_bytes && !uv3_noise_allowed(rx, now_ms))', '''  /* A second noisy packet never confirms the first, even with a valid CRC.
     A clean STOP/ESTOP still reaches the existing owner immediately. */
  if (rx->confirm_pending && rx->ne_bytes)
    return uv3_trip(rx,UV3_NOISE_REJECTED);
  if (rx->ne_bytes>1 && rx->bounded_noise && !rx->fault_latched &&
      rx->link_seen && rx->run_anchor && rx->clean_run_frames>=UV3_CLEAN_REQUIRED &&
      rx->frame[3]==1 && rx->frame[4]==3) {
    uv3_capture_reject(rx,&rx->last_reject,UV3_NOISE_REJECTED);
    rx->last_reject_valid=true;
    rx->confirm_pending=true;rx->confirm_sequence=rx->frame[5];
    rx->confirm_loss_base=rx->recoverable_losses;rx->confirm_started_ms=now_ms;
    if(rx->deferred_noise_frames!=UINT32_MAX)++rx->deferred_noise_frames;
    if(rx->dropped_frames!=UINT32_MAX)++rx->dropped_frames;
    rx->last_drop_reason=UV3_NOISE_REJECTED;
    rx->index=0;rx->speculative_prefix=0;
    return UV3_DROPPED;
  }
  if (rx->ne_bytes && !uv3_noise_allowed(rx, now_ms))''')
    s = once(s, '  if (explicit_clean_clear && rx->ne_bytes == 0 && !actually_running && !controller_fault) {', '''  if(rx->confirm_pending && !rx->ne_bytes && !controller_fault && !rx->fault_latched &&
      rx->clean_confirmations!=UINT32_MAX)++rx->clean_confirmations;
  rx->confirm_pending=false;
  if (explicit_clean_clear && rx->ne_bytes == 0 && !actually_running && !controller_fault) {''')
    return s

def main():
    if OUT.exists(): raise RuntimeError('preserve existing candidate')
    m = json.loads(read(BASE/'manifest.json'))
    assert m['installed'] and m['built'] and m['selftest_pass']
    for rel, expected in m['source_sha256'].items():
        assert hashlib.sha256((BASE/rel).read_bytes()).hexdigest() == expected, rel
    for tree in ('nucleo','UNOQ_MOTOR','web_hmi'):
        shutil.copytree(BASE/tree,OUT/tree,ignore=shutil.ignore_patterns(
            'build','Debug','Release','.metadata','.settings','__pycache__','.lock'))
    for folder in ('build/nucleo','build/uno','selftest'): (OUT/folder).mkdir(parents=True)
    # Retain all historical diagnostic/calibration identities in the HMI.
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
        for p in (OUT/folder).rglob('*'):
            if p.is_file():
                s=read(p); new=s.replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))
                if new!=s:write(p,new)
    for folder in ('nucleo/Inc','UNOQ_MOTOR'):
        p=OUT/folder/'uart_v3_transport.h';write(p,transport(read(p)))
    p=OUT/'web_hmi/server.py';s=read(p)
    s=''.join(line.replace(',2026102102)',',2026102102,2026102104)').replace(', 2026102102)',', 2026102102, 2026102104)')
              if 'not in (' in line else line for line in s.splitlines(keepends=True))
    s=s.replace("'mc_fw_build', 0) != 2026102102:","'mc_fw_build', 0) not in (2026102102,2026102104):")
    s=s.replace('"mc_fw_build", 0) == 2026102102:', '"mc_fw_build", 0) in (2026102102,2026102104):')
    s=once(s,'        (2026102101, 2026102102),','        (2026102101, 2026102102),\n        (2026102103, 2026102104),')
    s=once(s,'(2026102101,2026102102)) and','(2026102101,2026102102),(2026102103,2026102104)) and')
    write(p,s)
    manifest=dict(schema='mic_ai.uart_clean_confirm.v1',predecessor=str(BASE),
        pair_compatibility_ids=list(NEW),built=False,selftest_pass=False,installed=False,
        clean_confirmation_deadline_ms=100,maximum_outstanding_noisy_frames=1,
        damaged_frame_budget=2,damaged_frame_window_ms=1000,watchdog_ms=300,
        frame_deadline_ms=15,record_schema=5,record_bytes=320,
        calibration_changed=False,break_filter_changed=False,control_protocol_changed=False,
        pwm_or_motor_control_changed=False,uart_tx_backend_changed=False,watchdogs_changed=False,
        recovery_budget_changed=False,automatic_restart_added=False,
        hardware_commands=0,motor_commands=0,mcu_flash_commands=0,operationally_qualified=False,
        physical_noise_cause_proven=False,
        limitations=['Offline validation cannot establish the physical source of UART noise',
                     'Three truly damaged frames per one-second window still stop the drive',
                     'Continuous noise or missing clean confirmation still stops the drive',
                     '50 Hz motor operation has not been qualified'])
    write(OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n')
    print(OUT)

if __name__=='__main__': main()
