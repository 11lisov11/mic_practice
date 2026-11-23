"""Prepare additive shunt acquisition and telemetry, retaining corrected scalar V/f."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parents[1]
NUC=ROOT/'artifacts/live_bench_20261024/vf_smooth_start_r1'
BASE=ROOT/'artifacts/live_bench_20261024/uno_bus_display_r1'
OUT=ROOT/'artifacts/live_bench_20261024/current_shunt_monitor_r1'
RES=ROOT/'tools/current_shunt_monitor'
OLD,NEW=(2026102403,2026102402),(2026102405,2026102406)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return p.read_text(encoding='utf-8-sig')
def write(p,s):p.write_text(s,encoding='utf-8',newline='\n')
def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b)

def main():
    assert not OUT.exists(),'Preserve candidate'
    for folder in (BASE,NUC):
        m=json.loads(read(folder/'manifest.json'));assert m['installed']
        for rel,digest in m['source_sha256'].items():assert sha(folder/rel)==digest,rel
    for tree,source in (('nucleo',NUC),('UNOQ_MOTOR',BASE),('web_hmi',BASE)):
        shutil.copytree(source/tree,OUT/tree,ignore=shutil.ignore_patterns('Debug','Release','__pycache__','.metadata','.settings'))
    for rel in ('build/uno','build/nucleo'):(OUT/rel).mkdir(parents=True)
    for p in (OUT/'UNOQ_MOTOR').rglob('*'):
        if p.is_file():
            s=read(p);s=s.replace('2026102403','2026102405').replace('2026102402','2026102406');write(p,s)
    for folder in ('nucleo/Inc','nucleo/Src'):
        for p in (OUT/folder).rglob('*'):
            if p.is_file():
                s=read(p);new=s.replace('2026102402','2026102406')
                if s!=new:write(p,new)
    for name in ('current_core.h','current_shunt.h'):shutil.copyfile(RES/name,OUT/'nucleo/Inc'/name)
    shutil.copyfile(RES/'current_shunt.c',OUT/'nucleo/Src/current_shunt.c')
    p=OUT/'nucleo/STM32CubeIDE/.project';s=read(p)
    s=once(s,'\t<linkedResources>','\t<linkedResources>\n\t\t<link>\n\t\t\t<name>Application/User/current_shunt.c</name>\n\t\t\t<type>1</type>\n\t\t\t<locationURI>PARENT-1-PROJECT_LOC/Src/current_shunt.c</locationURI>\n\t\t</link>')
    write(p,s)
    shutil.copyfile(RES/'current_wire.h',OUT/'UNOQ_MOTOR/current_wire.h')
    p=OUT/'nucleo/Src/main.c';s=read(p)
    s=once(s,'#include "sd_live_status.h"','#include "sd_live_status.h"\n#include "current_shunt.h"')
    s=once(s,'  /* Keep the external UNO Q transport outside generated peripheral lists. */',
           '  mic_current_init();\n  /* Keep the external UNO Q transport outside generated peripheral lists. */')
    insert='''static void mic_send_current_page(uint32_t now_ms) {
  static uint32_t last_ms;
  static uint8_t slot;
  if((uint32_t)(now_ms-last_ms)<200U ||
      (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U || mic_uart_tx.hard_error) return;
  uint8_t packet[UV3_FRAME];
  mic_current_packet(packet,(uint8_t)(slot==0U),MIC_NUCLEO_FW_BUILD_ID);
  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK) {
    last_ms=now_ms;slot=(uint8_t)((slot+1U)%5U);
  }
}

'''
    s=once(s,'static void uno_send_reply(void) {',insert+'static void uno_send_reply(void) {')
    s=once(s,'  if (tx_status == HAL_OK) mic_send_break_page(now_ms);',
           '  if (tx_status == HAL_OK) { mic_send_break_page(now_ms);mic_send_current_page(now_ms); }')
    write(p,s)
    p=OUT/'nucleo/Src/stm32g4xx_mc_it.c';s=read(p)
    s='#include "current_shunt.h"\n'+s
    s=once(s,'  // Clear Flags M1\n  LL_ADC_ClearFlag_JEOS( ADC1 );',
           '  mic_current_adc_irq();\n  // Clear Flags M1\n  LL_ADC_ClearFlag_JEOS( ADC1 );')
    write(p,s)
    p=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(p)
    s=once(s,'static urw_receiver g_uart_reject;',
           'static urw_receiver g_uart_reject;\n#include "current_wire.h"\nstatic ct_receiver g_current;')
    s=once(s,'{ bw_reset(&g_break_wire);urw_reset(&g_uart_reject); }',
           '{ bw_reset(&g_break_wire);urw_reset(&g_uart_reject);ct_reset(&g_current); }')
    dispatch='''      if(buf[2]==CT_SUMMARY || buf[2]==CT_DETAIL) {
        const uint32_t observed_ms=millis();
        const bool fresh=g_bp_mcsdk_telemetry && (uint32_t)(observed_ms-g_bp_last_rsp_ms)<300U;
        (void)ct_receive(&g_current,buf,g_bp_fw_build,fresh,observed_ms);continue;
      }
'''
    s=once(s,'      if(buf[2]==URW_VERSION) {',dispatch+'      if(buf[2]==URW_VERSION) {')
    rpc='''  s += " mc_current_packet_hex=";
  if(g_current.has_summary) for(unsigned i=0;i<UV3_FRAME;++i) {
    s += break_hex[g_current.summary[i]>>4];s += break_hex[g_current.summary[i]&15];
  } else s += "-";
  s += " mc_current_detail_hex=";
  if(g_current.has_detail) for(unsigned i=0;i<UV3_FRAME;++i) {
    s += break_hex[g_current.detail[i]>>4];s += break_hex[g_current.detail[i]&15];
  } else s += "-";
  s += " mc_current_age_ms=";s += String((unsigned long)(g_current.has_summary?millis()-g_current.summary_ms:999999U));
  s += " mc_current_detail_age_ms=";s += String((unsigned long)(g_current.has_detail?millis()-g_current.detail_ms:999999U));
  s += " mc_current_good=";s += String((unsigned long)g_current.good);
  s += " mc_current_bad=";s += String((unsigned long)g_current.bad);
'''
    s=once(s,'  s += manual_status_fields(bp_age);',rpc+'  s += manual_status_fields(bp_age);');write(p,s)
    p=OUT/'web_hmi/server.py';s=read(p)
    # Retain historical calibration identities and add the new exact peer/pair.
    lines=[]
    for line in s.splitlines(keepends=True):
        if 'not in (' in line or ('mc_fw_build' in line and ' in (2026' in line):
            line=line.replace(',2026102402)',',2026102402,2026102406)').replace(', 2026102402)',', 2026102402, 2026102406)')
        lines.append(line)
    s=''.join(lines)
    s=once(s,'        (2026102403, 2026102402),','        (2026102403, 2026102402),\n        (2026102405, 2026102406),')
    s=once(s,'(2026102403,2026102402)) and','(2026102403,2026102402),(2026102405,2026102406)) and')
    s=once(s,'def with_motor_controller_aliases(data: dict) -> dict:',read(RES/'current_hmi.py')+'\n\ndef with_motor_controller_aliases(data: dict) -> dict:')
    s=once(s,'            if data.get("uno_local_adc_acquired") == 0 else "uno_q_local_adc_unqualified")',
           '            if data.get("uno_local_adc_acquired") == 0 else "uno_q_local_adc_unqualified")\n        data=with_shunt_currents(data)')
    s=once(s,'                "mc_uart_reject_hex": kv.get("mc_uart_reject_hex", "-"),',
           '''                **{key: kv.get(key, "-") for key in ("mc_current_packet_hex", "mc_current_detail_hex")},
                **{key: int(kv.get(key, "999999" if "age_ms" in key else "0")) for key in
                   ("mc_current_age_ms", "mc_current_detail_age_ms", "mc_current_good", "mc_current_bad")},
                "mc_uart_reject_hex": kv.get("mc_uart_reject_hex", "-"),''')
    write(p,s)
    p=OUT/'web_hmi/static/app.js';s=read(p)
    start=s.index('    currVal.textContent = Number(mcField(data, "mcsdk_telemetry", 0)) === 1')
    end=s.index('\n\n    if (phaseVal)',start)
    s=s[:start]+'    updateShuntCurrentPanel(data);'+s[end:]
    write(p,s+'\n'+read(RES/'current_ui.js'))
    m=dict(schema='mic_ai.current_shunt_monitor.v1',pair_compatibility_ids=list(NEW),
        predecessor_uno=str(BASE),predecessor_nucleo=str(NUC),built=False,selftest_pass=False,installed=False,
        control_mode='MAIN_VF_OL',foc_enabled=False,pwm_ccr123_changed=False,deadtime_changed=False,
        calibration_changed=False,watchdogs_changed=False,bkin_changed=False,uart_command_protocol_changed=False,
        adc_trigger_changed=True,adc_trigger='TIM1_OC4REF, ARR-384 ticks, one injected conversion per converter',
        current_window_ms=200,zero_samples_per_converter_path=256,current_scale_qualified=False,
        rshunt_ohm=.04,amplifier_gain=2.1,adc_reference_v=3.3,wire_packets_per_second_max=5,
        summary_version=213,detail_version=214,hardware_commands=0,physical_measurements_verified=False)
    write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n');print(OUT)

if __name__=='__main__':main()
