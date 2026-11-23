"""Prepare simultaneous TP23/PA6 recorder, entirely offline. Never flashes."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'artifacts/live_bench_20261020/sd_break_filter_fix_r1'
OUT = ROOT/'artifacts/live_bench_20261021/sd_dual_capture_r1'
T = ROOT/'tools/sd_dual'
OLD, NEW = (2026102001, 2026102002), (2026102101, 2026102102)

def read(p): return p.read_text(encoding='utf-8-sig')
def write(p,s): p.write_text(s,encoding='utf-8',newline='\n')
def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b)

def main():
    if OUT.exists(): raise RuntimeError('preserve existing candidate')
    for tree in ('nucleo','UNOQ_MOTOR','web_hmi'):
        shutil.copytree(BASE/tree,OUT/tree,ignore=shutil.ignore_patterns(
            'build','Debug','Release','.metadata','.settings','__pycache__','.lock'))
    for d in ('build/nucleo','build/uno','selftest'): (OUT/d).mkdir(parents=True)
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
        for p in (OUT/folder).rglob('*'):
            if p.is_file():
                s=read(p); updated=s.replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))
                if s!=updated: write(p,updated)
    for folder in ('nucleo/Inc','UNOQ_MOTOR'):
        for name in ('pulse_core.h','pulse_record.h'): shutil.copyfile(T/name,OUT/folder/name)
    p=OUT/'nucleo/Inc/bkin_wave_capture.h'
    write(p,once(read(p),'MIC_BKIN_RECORD_SCHEMA 4U','MIC_BKIN_RECORD_SCHEMA 5U'))
    p=OUT/'nucleo/Src/main.c';s=read(p)
    s=once(s,'  bp_init(&mic_bkin_pulse);','''  /* Passive TP23 input. Never drive SD, no pull-up/down, no EXTI. */
  GPIO_InitTypeDef probe={0};
  probe.Pin=GPIO_PIN_4; probe.Mode=GPIO_MODE_INPUT; probe.Pull=GPIO_NOPULL;
  HAL_GPIO_Init(GPIOA,&probe);
  if (((GPIOA->MODER>>8U)&3U)!=0U || ((GPIOA->PUPDR>>8U)&3U)!=0U) {
    mic_bkin_capture_state=MIC_BKIN_CAPTURE_ERROR; return;
  }
  bp_init(&mic_bkin_pulse);''')
    s=once(s,'const uint32_t high=!!(mic_bkin_ring[mic_bkin_cursor&8191U]&GPIO_PIN_6);',
           'const uint32_t high=mic_bkin_ring[mic_bkin_cursor&8191U] & (GPIO_PIN_4|GPIO_PIN_6);')
    s=once(s,'!!(mic_bkin_ring[(mic_bkin_cursor+count)&8191U]&GPIO_PIN_6)==high',
           '(mic_bkin_ring[(mic_bkin_cursor+count)&8191U] & (GPIO_PIN_4|GPIO_PIN_6))==high')
    s=once(s,'bp_feed_span(&mic_bkin_pulse,high,count)',
           'bp_feed_span(&mic_bkin_pulse,bp_state(high),count)')
    s=once(s,'''MIC_BKIN_RECORD_MAGIC,4U,MIC_BKIN_RECORD_BYTES,
    mic_bkin_event_tick_ms,200U,mic_bkin_pulse.flags,
    mic_bkin_pulse.trigger,mic_bkin_pulse.samples,mic_bkin_pulse.runs,
    mic_bkin_pulse.fall,mic_bkin_pulse.rise,bp_width(&mic_bkin_pulse),
    BP_LIMIT,mic_bkin_dma_flags,mic_bkin_remaining,0U''','''MIC_BKIN_RECORD_MAGIC,5U,MIC_BKIN_RECORD_BYTES,
    mic_bkin_event_tick_ms,200U,mic_bkin_pulse.flags,
    mic_bkin_pulse.trigger,mic_bkin_pulse.samples,mic_bkin_pulse.runs,
    0x50U,BP_LIMIT,BP_POST,BP_PRE,mic_bkin_dma_flags,mic_bkin_remaining,1U''')
    write(p,s)
    # Keep CubeMX regeneration aware of the passive diagnostic input.
    p=next((OUT/'nucleo').glob('*.ioc'));s=read(p)
    # Add to the numbered pin list, without altering existing entries.
    import re
    n=int(re.search(r'^Mcu.PinsNb=(\d+)$',s,re.M)[1])
    s=once(s,f'Mcu.PinsNb={n}',f'Mcu.Pin{n}=PA4\nMcu.PinsNb={n+1}')
    s+='\nPA4.GPIOParameters=GPIO_Label\nPA4.GPIO_Label=SD_TP23_PROBE\nPA4.Locked=true\nPA4.Signal=GPIO_Input\n'
    write(p,s)
    p=OUT/'web_hmi/server.py';s=read(p)
    # Existing identities remain valid for deployed calibration and old evidence.
    lines=[]
    for line in s.splitlines(keepends=True):
        if 'not in (' in line:
            line=line.replace(',2026102002)',',2026102002,2026102102)').replace(', 2026102002)',', 2026102002, 2026102102)')
        lines.append(line)
    s=''.join(lines)
    s=once(s,'        (2026102001, 2026102002),','        (2026102001, 2026102002),\n        (2026102101, 2026102102),')
    s=once(s,'(2026102001,2026102002)) and','(2026102001,2026102002),(2026102101,2026102102)) and')
    # Dispatch only the new exact peer to the new schema; old records retain
    # their original decoder and build allowlist.
    s=once(s,'def bkin_wave_status(data):',read(T/'decoder.py')+'\n\ndef bkin_wave_status(data):\n    if _as_int(data or {}, "mc_fw_build", 0) == 2026102102:\n        return dual_sd_wave_status(data)')
    write(p,s)
    p=OUT/'web_hmi/static/app.js';s=read(p)
    s=once(s,'Number(trace.schema) !== 4','![4, 5].includes(Number(trace.schema))')
    write(p,s)
    m=dict(schema='mic_ai.sd_dual_capture.v1',predecessor=str(BASE),
        pair_compatibility_ids=list(NEW),built=False,selftest_pass=False,installed=False,
        record_schema=5,record_bytes=320,joint_runs=32,channels={'0':'PA6/BKIN','1':'PA4/TP23'},
        sample_rate_hz_requested=5000000,prehistory_us=409.6,post_high_us=64.2,
        maximum_post_trigger_ms=100,ring_bytes=16384,calibration_changed=False,
        break_filter_changed=False,control_protocol_changed=False,pwm_or_motor_control_changed=False,
        uart_tx_backend_changed=False,watchdogs_changed=False,automatic_restart_added=False,
        hardware_commands=0,motor_commands=0,mcu_flash_commands=0,operationally_qualified=False,
        limitations=['No hardware run yet; timing/wiring/loading not physically qualified',
            'Both digital inputs reference Nucleo ground; not an isolated analog measurement',
            'A matching LOW does not prove a defective IPM or genuine overcurrent'])
    write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(OUT)
if __name__=='__main__': main()
