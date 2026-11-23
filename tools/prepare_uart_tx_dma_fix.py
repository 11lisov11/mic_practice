"""Prepare whole-frame DMA UART TX; no hardware operations."""
from pathlib import Path
import argparse
import json
import shutil
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261018/sd_live_diagnostics_r1'
OUT=ROOT/'artifacts/live_bench_20261018/uart_tx_dma_fix_r1'

def read(p):return p.read_text(encoding='utf-8-sig')
def write(p,s):p.write_text(s,encoding='utf-8',newline='\n')
def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b)

def main():
    global OUT
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--revision2',action='store_true')
    args=p.parse_args()
    uno_build,nuc_build=(2026101813,2026101812) if args.revision2 else (2026101811,2026101810)
    if args.revision2:OUT=ROOT/'artifacts/live_bench_20261018/uart_tx_dma_fix_r2'
    if OUT.exists():raise RuntimeError('preserve existing candidate')
    for tree in ('nucleo','UNOQ_MOTOR','web_hmi'):
        shutil.copytree(BASE/tree,OUT/tree,ignore=shutil.ignore_patterns('build','Debug','Release','.metadata','.settings','__pycache__','.lock'))
    for tree in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
        for p in (OUT/tree).rglob('*'):
            if p.is_file():
                old=read(p);s=old.replace('2026101809',str(uno_build)).replace('2026101808',str(nuc_build))
                if s!=old:write(p,s)
    p=OUT/'nucleo/Src/main.c';s=read(p)
    s=once(s,'static volatile uint8_t uno_rx_overflow;','static volatile uint8_t uno_rx_overflow;\n\n'+read(ROOT/'tools/uart_tx_dma/driver.inc'))
    s=once(s,'\n}\n\n\nstatic uint32_t uno_u32le', '\n  uno_tx_tc_isr();\n}\n\n\nstatic uint32_t uno_u32le')
    s=s.replace('HAL_UART_Transmit(&huart1,packet,UV3_FRAME,UNO_REPLY_TIMEOUT_MS)','uno_tx_submit(packet,UNO_TX_TAG_DIAG)')
    s=once(s,'  const int tx_status = HAL_UART_Transmit(&huart1, reply, UNO_FRAME_LEN, UNO_REPLY_TIMEOUT_MS);',
        '  const int tx_status = uno_tx_submit(reply,(status&0x22U)==0U ? UNO_TX_TAG_OFF : UNO_TX_TAG_ON);')
    s=once(s,'  mic_last_control_reply_safe_off = (tx_status == HAL_OK) && ((status & 0x22U) == 0U);',
        '  /* OFF evidence is published only by the USART TC ISR after the last stop bit. */')
    s=once(s,'  if (uno_clear_frame_is_safe(frame)) {','''  if (uno_clear_frame_is_safe(frame)) {
    if(!uno_tx_clear_ready()) {
      uno_latch_fault_reason(UNO_FAULT_INTERNAL,UNO_DIAG_TX);return;
    }''')
    s=once(s,'static void uno_link_poll(void) {','''static void uno_link_poll(void) {
  const int tx_failure=uno_tx_watchdog();
  if(tx_failure!=HAL_OK) {
    uno_capture_diagnostics(UNO_DIAG_TX,0U,(uint8_t)tx_failure);
    uno_link.last_bad_reason=UNO_DIAG_TX;
    uno_link.last_tx_status=(uint8_t)tx_failure;
    uno_saturating_increment(&uno_link.bad_count);
    uno_latch_fault_reason(UNO_FAULT_INTERNAL,UNO_DIAG_TX);
  }''')
    s=once(s,'  HAL_NVIC_SetPriority(USART1_IRQn, 3U, 0U);','  uno_tx_init();\n  HAL_NVIC_SetPriority(USART1_IRQn, 3U, 0U);')
    assert 'HAL_UART_Transmit(&huart1' not in s
    write(p,s)
    p=OUT/'web_hmi/server.py';s=read(p)
    pairs='        (2026101809, 2026101808),\n        (2026101811, 2026101810),'
    if args.revision2:pairs+='\n        (2026101813, 2026101812),'
    s=once(s,'        (2026101809, 2026101808),',pairs)
    # Manual scalar has its own compatibility predicate in addition to the
    # calibration identity list. Keep it in sync with the generated MCU pair.
    s=once(s,'(2026101807,2026101806)) and _as_int(data,"manual_scalar_capable",0)==1)',
        f'(2026101807,2026101806),({uno_build},{nuc_build})) and _as_int(data,"manual_scalar_capable",0)==1)')
    supported='2026101806,2026101808,2026101810'+(',2026101812' if args.revision2 else '')
    s=s.replace('2026101806,2026101808)',supported+')')
    s=s.replace('2026101806, 2026101808)',supported.replace(',',', ')+')')
    sd_builds='2026101808,2026101810'+(',2026101812' if args.revision2 else '')
    s=once(s,"int(data.get('mc_fw_build', 0)) != 2026101808:","int(data.get('mc_fw_build', 0)) not in ("+sd_builds+"):")
    write(p,s)
    manifest=dict(schema='mic_ai.uart_tx_dma_fix.v1',pair_compatibility_ids=[uno_build,nuc_build],
        predecessor=str(BASE),built=False,selftest_pass=False,calibration_changed=False,control_protocol_changed=False,
        pwm_or_motor_control_changed=False,recovery_budget_changed=False,watchdog_changed=False,
        tx_backend_changed=True,tx_frame_deadline_ms=5,tx_timeout_aborts_frame=False,
        hardware_commands=0,motor_commands=0,mcu_flash_commands=0,hv_release_approved=False,
        operationally_qualified=False,physical_crc_cause_proven=False)
    write(OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n');print(OUT)

if __name__=='__main__':main()
