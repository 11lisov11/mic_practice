"""Prepare an offline full-pulse BKIN diagnostic pair. No device/network I/O."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261017/bkin_dma_arr_fix_r1'
OUT=ROOT/'artifacts/live_bench_20261018/bkin_full_pulse_r1'
T=ROOT/'tools/bkin_full_pulse'
def read(p): return p.read_text(encoding='utf-8-sig')
def write(p,s): p.write_text(s,encoding='utf-8',newline='\n')
def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b)
def main():
    if OUT.exists(): raise RuntimeError('refusing to overwrite candidate')
    for name in ('nucleo','UNOQ_MOTOR','web_hmi'):
        shutil.copytree(BASE/name,OUT/name,ignore=shutil.ignore_patterns('build','Debug','Release','.metadata','.settings','__pycache__','.lock'))
    for d in ('build/nucleo','build/uno','selftest'): (OUT/d).mkdir(parents=True)
    for folder in ('nucleo/Inc','UNOQ_MOTOR'):
        for name in ('pulse_core.h','pulse_record.h'): shutil.copyfile(T/name,OUT/folder/name)
    p=OUT/'nucleo/Inc/bkin_wave_capture.h'
    s=read(p).replace('MIC_BKIN_RECORD_BYTES = 160U','MIC_BKIN_RECORD_BYTES = 320U').replace('MIC_BKIN_WIRE_PAGES = 7U','MIC_BKIN_WIRE_PAGES = 14U').replace('MIC_BKIN_RECORD_SCHEMA 2U','MIC_BKIN_RECORD_SCHEMA 3U').replace('mic_bkin_capture_stop_from_break','mic_bkin_capture_trigger_from_break')
    write(p,s)
    p=OUT/'nucleo/Inc/first_break_snapshot.h'; write(p,read(p).replace('mic_bkin_capture_stop_from_break','mic_bkin_capture_trigger_from_break'))
    p=OUT/'nucleo/Src/main.c'; s=read(p)
    s=once(s,'#include "bkin_wave_capture.h"','#include "bkin_wave_capture.h"\n#include "pulse_core.h"')
    a=s.index('static bool mic_bkin_dma_initialized;'); b=s.index('static void mic_bkin_wave_packet(',a)
    s=s[:a]+read(T/'firmware.inc')+'\n'+s[b:]
    s=s.replace('2026101710','2026101802'); write(p,s)
    for rel in ('nucleo/Inc/break_wire.h','UNOQ_MOTOR/break_wire.h','UNOQ_MOTOR/nucleo_fault_diagnostics.h','UNOQ_MOTOR/UNOQ_MOTOR.ino'):
        p=OUT/rel; write(p,read(p).replace('2026101710','2026101802').replace('2026101711','2026101803'))
    p=OUT/'UNOQ_MOTOR/bkin_wave_wire.h'; s=read(p)
    s=s.replace('#include "break_wire.h"','#include "break_wire.h"\n#include "pulse_record.h"')
    s=s.replace('BKW_RECORD_BYTES=160','BKW_RECORD_BYTES=320').replace('BKW_PAGES=7','BKW_PAGES=14').replace('uint8_t mask;','uint16_t mask;').replace('const uint8_t bit=(uint8_t)','const uint16_t bit=(uint16_t)').replace('(uint8_t)((1U<<BKW_PAGES)-1U)','(uint16_t)((1U<<BKW_PAGES)-1U)')
    a=s.index('    if (uv3_crc32c('); b=s.index('    rx->received_ms=',a)
    s=s[:a]+'''    if (uv3_crc32c(rx->data,BKW_RECORD_BYTES)!=rx->crc ||
        !bp_record_valid(rx->data)) { rx->mask=0; bw_increment(&rx->bad_pages); return false; }
'''+s[b:]; write(p,s)
    p=OUT/'web_hmi/server.py'; s=read(p)
    # New unique pair throughout the identity/calibration compatibility allowlists.
    s=s.replace('2026101710','2026101802').replace('2026101711','2026101803')
    s=once(s,'        (2026101803, 2026101802),','        (2026101711, 2026101710),\n        (2026101803, 2026101802),')
    a=s.index('def bkin_wave_status('); b=s.index('\n\nSTATE_NAMES =',a)
    s=s[:a]+read(T/'decoder.py')+s[b:]; write(p,s)
    p=OUT/'web_hmi/static/app.js'; s=read(p)
    anchor='      writeDriveSnapshotUnavailable(`${origin} (${at}): ${flags}${hz}${bus}${temp}${contextAge}. PA6 снят один раз при входе в обработчик: длительность импульса и точную физическую причину этот снимок не устанавливает.`);'
    s=once(s,anchor,'''      let pulseText = "Полная запись PA6 пока не получена.";
      try {
        const waveRes = await fetch("/api/bkin-trace", { headers: controlHeaders(false), cache: "no-store" });
        const waveEnvelope = await waveRes.json();
        const wave = waveEnvelope.data;
        if (waveRes.ok && waveEnvelope.ok && wave?.available) pulseText = wave.summary_ru;
      } catch (_) { /* Snapshot remains useful if the waveform request fails. */ }
      writeDriveSnapshotUnavailable(`${origin} (${at}): ${flags}${hz}${bus}${temp}${contextAge}. ${pulseText} По одному SD точная физическая причина не определяется.`);''')
    write(p,s)
    files={str(p.relative_to(OUT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi') for p in (OUT/folder).rglob('*') if p.is_file()}
    m={'schema':'mic_ai.bkin_full_pulse_candidate.v1','candidate':str(OUT),'predecessor':str(BASE),'pair_compatibility_ids':[2026101803,2026101802],'source_sha256':files,'calibration_changed':False,'control_protocol_changed':False,'pwm_or_motor_control_changed':False,'hardware_commands':0,'mcu_flash_commands':0,'motor_commands':0,'operationally_qualified':False,'hv_release_approved':False,'built':False,'selftest_pass':False}
    write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(OUT)
if __name__=='__main__': main()
