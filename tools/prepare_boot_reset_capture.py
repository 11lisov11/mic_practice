"""Prepare 3013/3014 offline; never overwrite installed firmware/evidence."""
import json
import os
import shutil
from prepare_standstill_commissioning import ROOT,read,write,once

BASE=ROOT/'artifacts/live_bench_20261029/foc_observer_schedule_fix_r1'
OUT=ROOT/'artifacts/live_bench_20261030/boot_reset_capture_r1'
NEW=(2026103013,2026103014)
SOURCE=ROOT/'tools/boot_reset_capture'


def main():
    assert not (OUT/'manifest.json').exists(), 'Never overwrite a completed candidate'
    if OUT.exists():
        assert {p.name for p in OUT.iterdir()} <= {'nucleo','UNOQ_MOTOR','libraries','web_hmi'}
    for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
        def cp(src,dst):
            rel=os.path.relpath(src,BASE/folder).split(os.sep)
            if folder=='libraries' or folder=='nucleo' and rel[0] in ('Drivers','MCSDK_v6.4.2-Full'):
                if os.path.exists(dst):assert os.path.samefile(src,dst)
                else:os.link(src,dst)
                return dst
            return shutil.copy2(src,dst)
        shutil.copytree(BASE/folder,OUT/folder,copy_function=cp,dirs_exist_ok=True,
            ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
        for f in (OUT/folder).rglob('*'):
            if f.is_file():
                s=read(f);n=s.replace('2026103011',str(NEW[0])).replace('2026103012',str(NEW[1])).replace('3011-observer-schedule','3013-boot-capture')
                if s!=n:write(f,n)
    for folder in ('nucleo/Inc','UNOQ_MOTOR'):
        for name in ('boot_record.h','boot_wire.h'):write(OUT/folder/name,read(SOURCE/name))
    write(OUT/'nucleo/Inc/boot_diag.h',read(SOURCE/'boot_diag.h'))
    f=OUT/'nucleo/Src/system_stm32g4xx.c';s=read(f)
    s=once(s,'void SystemInit(void)',
        '#include "boot_wire.h"\n#include "boot_diag.h"\n#define MIC_NUCLEO_FW_BUILD_ID 2026103014UL\n'+read(SOURCE/'target.inc')+'\nvoid SystemInit(void)')
    # GCC can emit VFP loads/stores even for integer struct copies. Enable
    # CP10/CP11 and complete the barriers before entering the early recorder.
    anchor='  /* Configure the Vector Table location add offset address ------------------*/'
    s=once(s,anchor,'  __DSB();__ISB();\n  mic_boot_capture_early();\n\n'+anchor)
    write(f,s)
    f=OUT/'nucleo/STM32CubeIDE/STM32G431RBTX_FLASH.ld';s=read(f)
    s=once(s,'  /* User_heap_stack section, used to check that there is enough "RAM" Ram  type memory left */',
        '  .noinit (NOLOAD) :\n  {\n    . = ALIGN(4);\n    KEEP(*(.noinit.mic_boot))\n    . = ALIGN(4);\n  } >RAM\n\n  /* User_heap_stack section, used to check that there is enough "RAM" Ram  type memory left */')
    write(f,s)
    f=OUT/'nucleo/Src/mcp.c';s=read(f)
    s=once(s,'#include "mcp.h"','#include "mcp.h"\n#include "boot_diag.h"\n#include "boot_record.h"')
    s=once(s,'        HAL_NVIC_SystemReset();','        mic_boot_note_software_reset(MB_MCP_RESET);\n        HAL_NVIC_SystemReset();')
    write(f,s)
    f=OUT/'nucleo/Src/main.c';s=read(f)
    s=once(s,'#include "foc_timing_irq.h"','#include "foc_timing_irq.h"\n#include "boot_diag.h"')
    anchor='static void mic_send_research_page(uint32_t now_ms) {'
    s=once(s,anchor,'''static void mic_send_boot_page(uint32_t now_ms){
  static uint32_t last_ms;
  if(LL_TIM_IsEnabledAllOutputs(TIM1)||uno_link.command_enabled||
     !mic_last_control_reply_safe_off||(uint32_t)(now_ms-last_ms)<500U||
     (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME];mic_boot_packet(packet,now_ms);
  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK)last_ms=now_ms;
}

'''+anchor)
    s=once(s,'      mic_send_break_page(now_ms);mic_send_peak_page(now_ms);',
        '      mic_send_boot_page(now_ms);\n      mic_send_break_page(now_ms);mic_send_peak_page(now_ms);')
    write(f,s)
    f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
    s=once(s,'#include "foc_timing_wire.h"','#include "foc_timing_wire.h"\n#include "boot_wire.h"\nstatic mb_receiver g_native_boot={};')
    s=once(s,'      if(buf[2]==FT_WIRE){','''      if(buf[2]==MB_WIRE){
        const uint32_t now=millis();
        const bool fresh=g_bp_mcsdk_telemetry&&(uint32_t)(now-g_bp_last_rsp_ms)<300U;
        (void)mb_receive(&g_native_boot,buf,g_bp_fw_build,fresh,now);continue;
      }
      if(buf[2]==FT_WIRE){''')
    anchor='      pe_reset(&g_encoder_history,&g_encoder_records);'
    assert s.count(anchor)==2
    s=s.replace(anchor,'      memset(&g_native_boot,0,sizeof(g_native_boot));\n'+anchor)
    s=once(s,'    s += " foc_runtime_valid=";', '''    s += " mc_boot_packet_hex=";
    if(g_native_boot.received){
      static const char digits[]="0123456789abcdef";
      for(unsigned i=0;i<UV3_FRAME;++i){s+=digits[g_native_boot.packet[i]>>4];s+=digits[g_native_boot.packet[i]&15U];}
    }else s+="-";
    s += " mc_boot_fresh=";s += String(mb_fresh(&g_native_boot,g_bp_fw_build,native_fresh,millis())?1:0);
    s += " foc_runtime_valid=";''')
    write(f,s)
    f=OUT/'web_hmi/server.py';s=read(f)
    s=once(s,'def foc_runtime_status(kv):',read(SOURCE/'web_status.py')+'\n\ndef foc_runtime_status(kv):')
    s=once(s,'                **foc_runtime_status(kv),','                **boot_wire_status(kv),\n                **foc_runtime_status(kv),')
    s=once(s,'        self._event_id = ""','        self._event_id = ""\n        self._boot_key = None\n        self._boot_tick = None')
    s=once(s,'            changed = key is not None and key != self._key','''            boot=data.get('native_boot',{})
            if boot.get('available') and boot.get('fresh'):
                boot_key=(data.get('linux_boot_id'),boot.get('firmware'),boot.get('retained_sequence'),boot.get('early_record_crc'))
                boot_tick=boot.get('native_tick_ms')
                if boot_key!=self._boot_key or (self._boot_tick is not None and boot_tick<self._boot_tick and self._boot_tick-boot_tick<0x80000000):
                    lines.append('MC_BOOT_RECORD '+json.dumps(dict(linux_boot_id=data.get('linux_boot_id'),observed_unix_s=_now_ts(),record=boot),separators=(',',':'),allow_nan=False))
                self._boot_key=boot_key;self._boot_tick=boot_tick
            changed = key is not None and key != self._key''')
    write(f,s)
    f=OUT/'web_hmi/static/app.js';s=read(f)
    s=once(s,'  d.driveDiagRaw.textContent = String(data.mc_fault_detail || "Нет кода ошибки от контроллера.");',
        '''  d.driveDiagRaw.textContent = String(data.mc_fault_detail || "Нет кода ошибки от контроллера.")
    + (data.native_boot?.available ? ` · Загрузка Nucleo: ${data.native_boot.summary_ru}` : " · Причина сброса Nucleo: запись пока не получена");''')
    write(f,s)
    write(OUT/'manifest.json',json.dumps(dict(pair=list(NEW),base_pair=[2026103011,2026103012],
        built=False,installed=False,hardware_commands=0,START=0,CLEAR=0,RESET=0,
        current_trip_A=1.35,ADC_guard_ticks=2048,estimate_age_limit_ms=2,
        fast_budget_cycles=5312,zero_criteria_unchanged=True,thresholds_changed=False,
        boot_capture_before_HAL=True,telemetry_OFF_only=True,retained_bytes=32,
        previous_reset_cause_not_recoverable=True),indent=2)+'\n')
    print('Prepared3013/3014 offline; no hardware access')


if __name__=='__main__':main()
