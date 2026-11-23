"""Prepare an offline correction of double-counted speculative UART prefixes."""
from pathlib import Path
import json,hashlib,shutil

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261018/bkin_fast_capture_r1'
OUT=ROOT/'artifacts/live_bench_20261018/uart_resync_fix_r1'
T=ROOT/'tools/uart_resync_fix'
def read(p):return p.read_text(encoding='utf-8-sig')
def write(p,s):p.write_text(s,encoding='utf-8',newline='\n')
def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b)

def patched_transport(s):
    a='typedef struct {\n  uint8_t frame[UV3_FRAME];'
    s=once(s,a,'''/* Frozen rejected data, never used as a control command. */
typedef struct { uint32_t meta[14]; uint8_t bytes[44], marks[44]; } uv3_reject;
typedef struct {
  uint8_t speculative_prefix;
  uint32_t speculative_expired, observed_ms;
  bool last_reject_valid, fatal_reject_valid;
  uv3_reject last_reject, fatal_reject;
  uint8_t frame[UV3_FRAME];''')
    s=once(s,'static inline uv3_result uv3_trip(','''static inline void uv3_capture_reject(const uv3_rx *rx, uv3_reject *e, uv3_result reason) {
  memset(e,0,sizeof(*e));
  const unsigned length=rx->index<=UV3_FRAME ? (unsigned)rx->index : (unsigned)UV3_FRAME;
  const uint32_t meta[14]={rx->observed_ms,(uint32_t)reason,length,rx->speculative_prefix,
    rx->last_uart_flags,rx->link_seen ? rx->previous[5] : UINT32_MAX,
    rx->noise_used,rx->recoverable_losses,rx->dropped_frames,rx->last_valid_ms,
    rx->frame_started_ms,(rx->link_seen ? 1U : 0U)|(rx->fault_latched ? 2U : 0U),0,0};
  memcpy(e->meta,meta,sizeof(meta));
  memcpy(e->bytes,rx->frame,length);memcpy(e->marks,rx->marks,length);
  if (length==UV3_FRAME) {
    for(unsigned i=0;i<4;++i)e->meta[12]|=(uint32_t)rx->frame[UV3_PAYLOAD+i]<<(8*i);
    e->meta[13]=uv3_crc32c(rx->frame,UV3_PAYLOAD);
  }
}

static inline uv3_result uv3_trip(''')
    s=once(s,'  if (!rx->fault_latched) rx->fault = reason;', '''  if (!rx->fault_latched) {
    rx->fault=reason;
    uv3_capture_reject(rx,&rx->fatal_reject,reason);rx->fatal_reject_valid=true;
  }
  rx->speculative_prefix=0;''')
    s=once(s,'  if (rx->dropped_frames != UINT32_MAX) ++rx->dropped_frames;', '''  if (!rx->fatal_reject_valid) {
    uv3_capture_reject(rx,&rx->last_reject,reason);rx->last_reject_valid=true;
  }
  rx->speculative_prefix=0;
  if (rx->dropped_frames != UINT32_MAX) ++rx->dropped_frames;''')
    s=once(s,'  rx->seeking_sync = rx->index == 0;', '  rx->speculative_prefix=rx->index;\n  rx->seeking_sync = rx->index == 0;')
    s=once(s,'static inline uv3_result uv3_tick(uv3_rx *rx, uint32_t now_ms) {',
        'static inline uv3_result uv3_tick(uv3_rx *rx, uint32_t now_ms) {\n  rx->observed_ms=now_ms;')
    s=once(s,'''  if (rx->index != 0 && (uint32_t)(now_ms - rx->frame_started_ms) > UV3_FRAME_DEADLINE_MS)
    return uv3_drop(rx, UV3_FRAME_TIMEOUT, now_ms);''', '''  if (rx->index != 0 && (uint32_t)(now_ms-rx->frame_started_ms)>UV3_FRAME_DEADLINE_MS) {
    if (rx->speculative_prefix==rx->index) {
      /* No NEW byte arrived: this is the already rejected packet's suffix,
       * not a second lost packet. Do not spend budget or grant a sequence gap.
       * The last committed watchdog deadline stays unchanged. */
      rx->index=0;rx->speculative_prefix=0;rx->seeking_sync=true;
      if(rx->speculative_expired!=UINT32_MAX)++rx->speculative_expired;
      return UV3_WAIT;
    }
    return uv3_drop(rx,UV3_FRAME_TIMEOUT,now_ms);
  }''')
    s=once(s,'  rx->last_uart_flags = flags;','  rx->observed_ms=now_ms;\n  rx->last_uart_flags = flags;')
    s=once(s,'        rx->frame_uart_flags = flags;',
        '        rx->frame[0]=byte;rx->marks[0]=flags;rx->index=1;\n        rx->frame_uart_flags = flags;')
    s=once(s,'    rx->seeking_sync = false;\n    rx->frame_started_ms',
        '    rx->speculative_prefix=0;\n    rx->seeking_sync = false;\n    rx->frame_started_ms')
    s=once(s,'''    rx->index = 0;
    pending = uv3_drop(rx, flags || rx->ne_bytes ? UV3_NOISE_REJECTED : UV3_BAD_CRC, now_ms);''', '''    if (rx->speculative_prefix==rx->index && byte==0xaa) {
      /* Reuse the incoming AA as a fresh header; the old retained AA was
       * already charged. There is no lost new packet here. */
      rx->frame[0]=byte;rx->marks[0]=flags;rx->index=1;rx->speculative_prefix=0;
      rx->frame_started_ms=now_ms;rx->frame_uart_flags=flags;rx->ne_bytes=!!(flags&UV3_NE);
      return pending;
    }
    rx->frame[rx->index]=byte;rx->marks[rx->index++]=flags;
    pending = uv3_drop(rx, flags || rx->ne_bytes ? UV3_NOISE_REJECTED : UV3_BAD_CRC, now_ms);''')
    s=once(s,'  rx->index = 0;\n  rx->last_uart_flags = rx->frame_uart_flags;',
        '  rx->last_uart_flags = rx->frame_uart_flags;')
    s=once(s,'  return UV3_READY;','  rx->index=0;rx->speculative_prefix=0;\n  return UV3_READY;')
    return s

def main():
    if OUT.exists():raise RuntimeError('candidate exists; preserve it')
    for name in ('nucleo','UNOQ_MOTOR','web_hmi'):
        shutil.copytree(BASE/name,OUT/name,ignore=shutil.ignore_patterns('build','Debug','Release',
            '.metadata','.settings','__pycache__','.lock'))
    for rel in ('build/nucleo','build/uno','selftest'):(OUT/rel).mkdir(parents=True)
    for folder in ('nucleo/Inc','UNOQ_MOTOR'):
        write(OUT/folder/'uart_v3_transport.h',patched_transport(read(BASE/folder/'uart_v3_transport.h')))
        shutil.copyfile(T/'uart_reject_record.h',OUT/folder/'uart_reject_record.h')
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
        for p in (OUT/folder).rglob('*'):
            if p.is_file() and p.suffix in ('.h','.c','.ino','.py','.js'):
                before=read(p)
                after=before.replace('2026101804','2026101806').replace('2026101805','2026101807')
                if after!=before:write(p,after)
    p=OUT/'nucleo/Src/main.c';s=read(p)
    s=once(s,'#include "pulse_core.h"','#include "pulse_core.h"\n#include "uart_reject_record.h"')
    s=once(s,'static uv3_rx uno_transport;', 'static uv3_rx uno_transport;\n'+read(T/'send_trace.inc'))
    # Keep existing diagnostic page order and OFF-only gate. New pages follow
    # the existing 8 snapshot and 14 waveform pages, at the same 200-ms rate.
    s=once(s,'  if (slot >= 2U * BW_PAGES) {', '''  if(slot>=2U*BW_PAGES+MIC_BKIN_WIRE_PAGES) {
    if(uno_transport.fatal_reject_valid) {
      uint8_t packet[UV3_FRAME];mic_uart_reject_packet(packet,slot-2U*BW_PAGES-MIC_BKIN_WIRE_PAGES);
      if(HAL_UART_Transmit(&huart1,packet,UV3_FRAME,UNO_REPLY_TIMEOUT_MS)!=HAL_OK)
        bw_increment(&mic_break_diag_tx_errors);
    }
    slot=(uint8_t)((slot+1U)%(2U*BW_PAGES+MIC_BKIN_WIRE_PAGES+UR_PAGES));return;
  }
  if (slot >= 2U * BW_PAGES) {''')
    s=s.replace('(2U * BW_PAGES + MIC_BKIN_WIRE_PAGES)',
        '(2U * BW_PAGES + MIC_BKIN_WIRE_PAGES + UR_PAGES)').replace(
        '(2U*BW_PAGES + MIC_BKIN_WIRE_PAGES)', '(2U*BW_PAGES + MIC_BKIN_WIRE_PAGES + UR_PAGES)')
    write(p,s)
    # Same paging/CRC/fresh-OFF validation as the proven BKIN receiver.
    w=read(OUT/'UNOQ_MOTOR/bkin_wave_wire.h')
    w=w.replace('MIC_BKIN_WAVE_WIRE_H','MIC_UART_REJECT_WIRE_H').replace('"pulse_record.h"','"uart_reject_record.h"')
    w=w.replace('BKW','URW').replace('bkw_','urw_').replace('0xD2','0xD3').replace('0x314e4b42','0x31545255')
    w=w.replace('bp_record_valid(rx->data)','ur_record_valid(rx->data,BW_NUCLEO_BUILD)')
    write(OUT/'UNOQ_MOTOR/uart_reject_wire.h',w)
    p=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(p)
    s=once(s,'static bkw_receiver g_bkin_wave;', '#include "uart_reject_wire.h"\nstatic bkw_receiver g_bkin_wave;\nstatic urw_receiver g_uart_reject;')
    s=once(s,'    bw_reset(&g_break_wire);', '    { bw_reset(&g_break_wire);urw_reset(&g_uart_reject); }')
    s=once(s,'      if (buf[2] == BKW_VERSION) {', '''      if(buf[2]==URW_VERSION) {
        const uint32_t observed_ms=millis();
        const bool fresh_off=g_bp_mcsdk_telemetry && !g_pwm_enabled &&
            (g_bp_status&0x22U)==0U && (uint32_t)(observed_ms-g_bp_last_rsp_ms)<300U;
        (void)urw_receive(&g_uart_reject,buf,g_bp_fw_build,fresh_off,observed_ms);continue;
      }
      if (buf[2] == BKW_VERSION) {''')
    s=once(s,'  s += " mc_break_wave_hex=";', '''  s += " mc_uart_reject_hex=";
  if(g_uart_reject.complete) {
    for(unsigned i=0;i<URW_RECORD_BYTES;++i) {
      const uint8_t byte=g_uart_reject.data[i];s+=break_hex[byte>>4];s+=break_hex[byte&15];
    }
  } else s+="-";
  s+=" mc_uart_reject_good_pages=";s+=String((unsigned long)g_uart_reject.good_pages);
  s+=" mc_uart_reject_bad_pages=";s+=String((unsigned long)g_uart_reject.bad_pages);
  s += " mc_break_wave_hex=";''')
    write(p,s)
    p=OUT/'web_hmi/server.py';s=read(p)
    s=once(s,'        (2026101807, 2026101806),','        (2026101805, 2026101804),\n        (2026101807, 2026101806),')
    s=once(s,'def bkin_wave_status(data):',read(T/'decoder.py')+'\n\ndef bkin_wave_status(data):')
    s=once(s,'                "mc_break_wave_hex": kv.get("mc_break_wave_hex", "-"),',
        '                "mc_uart_reject_hex": kv.get("mc_uart_reject_hex", "-"),\n'
        '                "mc_uart_reject_good_pages": int(kv.get("mc_uart_reject_good_pages", "0")),\n'
        '                "mc_uart_reject_bad_pages": int(kv.get("mc_uart_reject_bad_pages", "0")),\n'
        '                "mc_break_wave_hex": kv.get("mc_break_wave_hex", "-"),')
    s=once(s,'        if parsed.path == "/api/bkin-trace":','''        if parsed.path == "/api/uart-reject":
            if not self._require_control_access(mark_heartbeat=False):return
            ok,data,err=self.server.app.rpc.get()
            if not ok or data is None:
                self._send_json({"ok":False,"error":err or "no response"},503);return
            self._send_json({"ok":True,"data":uart_reject_status(data)});return
        if parsed.path == "/api/bkin-trace":''')
    s=once(s,'        data["mc_fault_detail"] = motor_fault_detail(data)',
        '        data["mc_fault_detail"] = motor_fault_detail(data)\n'
        '        trace=uart_reject_status(data)\n'
        '        if trace.get("available"):data["mc_fault_detail"]+="; "+trace["summary_ru"]')
    write(p,s)
    hashes={p.relative_to(OUT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for tree in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi') for p in (OUT/tree).rglob('*') if p.is_file()}
    manifest=dict(schema='mic_ai.uart_resync_fix_candidate.v1',pair_compatibility_ids=[2026101807,2026101806],
        source_sha256=hashes,predecessor=str(BASE),calibration_changed=False,control_protocol_changed=False,
        pwm_or_motor_control_changed=False,recovery_budget_changed=False,watchdog_changed=False,
        physical_crc_cause_proven=False,hardware_commands=0,motor_commands=0,mcu_flash_commands=0,
        operationally_qualified=False,hv_release_approved=False,built=False,selftest_pass=False)
    write(OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n');print(OUT)

if __name__=='__main__':main()
