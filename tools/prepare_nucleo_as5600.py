"""Build candidate sources for Nucleo-owned AS5600; never access hardware."""
import json
import os
from pathlib import Path
import shutil
import prepare_current_shunt_monitor as u

ROOT=u.ROOT
UNO=ROOT/'artifacts/live_bench_20261025/as5600_recovery_r1'
NUC=ROOT/'artifacts/live_bench_20261024/current_adc_apex_fix_r1'
OUT=ROOT/'artifacts/live_bench_20261026/nucleo_as5600_r1'
RES=ROOT/'tools/nucleo_as5600'
OLD=(2026102518,2026102510)
NEW=(2026102601,2026102602)

def main():
    assert not (OUT/'manifest.json').exists(),'Preserve candidate'
    for base in (UNO,NUC):
        m=json.loads(u.read(base/'manifest.json'));assert m['installed'] and m['built'] and m['selftest_pass']
        for rel,digest in m['source_sha256'].items():assert u.sha(base/rel)==digest,rel
    for name,base in [('nucleo',NUC),('UNOQ_MOTOR',UNO),('web_hmi',UNO)]:
        def copy(src,dst):
            rel=Path(src).relative_to(base/name)
            if name=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):
                os.link(src,dst);return dst
            return shutil.copy2(src,dst)
        shutil.copytree(base/name,OUT/name,copy_function=copy,
            ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
        for f in (OUT/folder).rglob('*'):
            if f.is_file():
                a=u.read(f);b=a.replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))
                if a!=b:u.write(f,b)
    for name in ('encoder_core.h','encoder_wire.h','nucleo_encoder.h'):
        shutil.copyfile(RES/name,OUT/'nucleo/Inc'/name)
    shutil.copyfile(RES/'nucleo_encoder.c',OUT/'nucleo/Src/nucleo_encoder.c')
    f=OUT/'nucleo/STM32CubeIDE/.project';s=u.read(f)
    s=u.once(s,'\t<linkedResources>', '\t<linkedResources>\n\t\t<link>\n\t\t\t<name>Application/User/nucleo_encoder.c</name>\n\t\t\t<type>1</type>\n\t\t\t<locationURI>PARENT-1-PROJECT_LOC/Src/nucleo_encoder.c</locationURI>\n\t\t</link>')
    u.write(f,s)
    for name in ('encoder_wire.h','uno_encoder_adapter.h'):
        shutil.copyfile(RES/name,OUT/'UNOQ_MOTOR'/name)
    f=OUT/'nucleo/Src/main.c';s=u.read(f)
    s=u.once(s,'#include "current_shunt.h"','#include "current_shunt.h"\n#include "nucleo_encoder.h"')
    anchor='static void uno_send_reply(void) {'
    s=u.once(s,anchor,'''static void mic_send_encoder_page(uint32_t now_ms) {
  static uint32_t last_ms;
  if(!uno_link.link_seen || (uint32_t)(now_ms-last_ms)<20U ||
      (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U || mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME];mic_encoder_packet(packet,MIC_NUCLEO_FW_BUILD_ID);
  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK)last_ms=now_ms;
}

'''+anchor)
    s=u.once(s,'  mic_current_init();','  mic_current_init();\n  mic_encoder_init();')
    s=u.once(s,'    uno_link_poll();','    uno_link_poll();\n    mic_encoder_poll();\n    mic_send_encoder_page(HAL_GetTick());')
    u.write(f,s)
    f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=u.read(f)
    s=u.once(s,'#include "as5600_teacher.h"','#include "as5600_teacher.h"\n#include "uno_encoder_adapter.h"')
    a=s.index('static bool handle_encbus_command(');b=s.index('static bool handle_mcfoc_command(',a)
    s=s[:a]+'''static bool handle_encbus_command(const char *arg) {
  (void)arg;return false; // Sensor is owned by Nucleo; no second I2C master.
}
'''+s[b:]
    s=u.once(s,'  if (!as5600_diag_ready()) return "encoder bus handover pending";',
        '  // Sensor is observational in scalar mode; no local bus handover exists.')
    s=u.once(s,'s += " enc_source=uno_q_i2c2";',
        's += " enc_source=nucleo_g431_i2c1";\n    s += " enc_peer_good=";s += String((unsigned long)g_remote_encoder.good);\n    s += " enc_peer_bad=";s += String((unsigned long)g_remote_encoder.bad);\n    s += " enc_diag_category_counts_available=0";')
    s=u.once(s,'  if (NUCLEO_MCSDK_ACIM_BACKEND) as5600_teacher_begin();',
        '  // Nucleo owns AS5600. Do not start the Uno I2C worker.')
    s=u.once(s,'    g_as5600 = as5600_teacher_snapshot(millis());',
        '    g_as5600 = remote_encoder_snapshot(millis(),g_bp_mcsdk_telemetry && (uint32_t)(millis()-g_bp_last_rsp_ms)<300U);')
    anchor='      if(buf[2]==PC_WIRE) {'
    s=u.once(s,anchor,'''      if(buf[2]==EW_VERSION) {
        const uint32_t now=millis();
        const bool fresh=g_bp_mcsdk_telemetry && (uint32_t)(now-g_bp_last_rsp_ms)<300U;
        (void)ew_receive(&g_remote_encoder,buf,g_bp_fw_build,fresh,now);continue;
      }
'''+anchor)
    u.write(f,s)
    f=OUT/'web_hmi/server.py';s=u.read(f)
    # Keep earlier calibration identities and packet decoders; add this pair.
    s=s.replace('(2026102518, 2026102510)', '(2026102518, 2026102510), (2026102601, 2026102602)')
    s=s.replace('(2026102518,2026102510)', '(2026102518,2026102510),(2026102601,2026102602)')
    s=s.replace(', 2026102510)',', 2026102510, 2026102602)').replace(',2026102510)',',2026102510,2026102602)') if False else s
    lines=[]
    for line in s.splitlines(keepends=True):
        if "'mc_fw_build'" in line or '"mc_fw_build"' in line or 'elif peer not in' in line:
            if 'not in (' in line or ' in (' in line:
                # Do not alter tuple-pair whitelists.
                if '(2026102518,' not in line and '(2026102518, ' not in line:
                    line=line.replace(',2026102510)',',2026102510,2026102602)').replace(', 2026102510)',', 2026102510, 2026102602)')
        lines.append(line)
    s=''.join(lines)
    s=u.once(s,"int.from_bytes(raw[6:10], 'little') != 2026102510", "int.from_bytes(raw[6:10], 'little') != int(data['mc_fw_build'])")
    s=u.once(s,"int.from_bytes(p[6:10],'little')!=2026102510", "int.from_bytes(p[6:10],'little')!=int(data['mc_fw_build'])")
    s=u.once(s,"trace=decode_adc_peak_hex(data['mc_adc_peak_hex'])", "trace=decode_adc_peak_hex(data['mc_adc_peak_hex'],int(data['mc_fw_build']))")
    anchor='                "enc_source": kv.get("enc_source", "motor_controller_uart"),'
    s=u.once(s,anchor,anchor+'\n                "enc_peer_good": int(kv.get("enc_peer_good","0")),\n                "enc_peer_bad": int(kv.get("enc_peer_bad","0")),\n                "enc_diag_category_counts_available": int(kv.get("enc_diag_category_counts_available","1")),')
    u.write(f,s)
    f=OUT/'web_hmi/static/app.js';s=u.read(f)
    s=u.once(s,'if (encOk && encRpm !== null && (data.enc_source !== "uno_q_i2c2" || Number(data.enc_speed_ok) === 1))',
        'if (encOk && encRpm !== null && Number(data.enc_speed_ok) === 1)')
    s=u.once(s,'if (data.enc_source === "uno_q_i2c2" && !encOk)',
        'if (["uno_q_i2c2", "nucleo_g431_i2c1"].includes(data.enc_source) && !encOk)')
    s=u.once(s,'      encVal.textContent = text;', '''      encVal.textContent = text;
      encVal.title = `Источник: ${data.enc_source || "—"}; ошибок чтения: ${Number(data.enc_errors || 0)}; стадия: ${Number(data.enc_diag_stage || 0)}; причина: ${Number(data.enc_diag_cause || 0)}; возраст: ${Number(data.enc_age_ms || 0)} мс`;''')
    u.write(f,s)
    for n in ('build/uno','build/nucleo','verification'):(OUT/n).mkdir(parents=True,exist_ok=True)
    m=dict(schema='mic_ai.nucleo_as5600.v1',pair_compatibility_ids=list(NEW),
        predecessor_uno=str(UNO),predecessor_nucleo=str(NUC),built=False,selftest_pass=False,installed=False,
        sensor_source='nucleo_g431_i2c1',sensor_feedback_control=False,control_mode='MAIN_VF_OL',
        i2c_sample_period_ms=5,i2c_transaction_deadline_ms=3,telemetry_period_ms=20,
        calibration_changed=False,thresholds_changed=False,watchdogs_changed=False,bkin_changed=False,
        pwm_ccr123_changed=False,deadtime_changed=False,adc_trigger_changed=False,
        uart_command_protocol_changed=False,sensor_packet_version=218,
        calibration_sha256=json.loads(u.read(UNO/'manifest.json'))['calibration_sha256'])
    u.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n');print(OUT)

if __name__=='__main__':main()
