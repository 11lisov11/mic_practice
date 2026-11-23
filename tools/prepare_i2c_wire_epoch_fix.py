"""Uno-only repair of the existing control-reply cache reset integration."""
import ast,json,shutil,subprocess
import prepare_i2c_wire_capture as previous
ROOT=previous.ROOT;BASE=previous.OUT;OUT=ROOT/'artifacts/live_bench_20261028/i2c_wire_epoch_fix_r2'
OLD=previous.NEW;NEW=(2026102813,2026102812)
read,write,sha,once=previous.read,previous.write,previous.sha,previous.once
OLD_BLOCK='    { bw_reset(&g_break_wire);urw_reset(&g_uart_reject);ct_reset(&g_current);pc_reset(&g_peak);zh_reset(&g_zero_history); }'
NEW_BLOCK='''    {
      pe_reset(&g_encoder_history,&g_encoder_records);
      memset(&g_encoder_health,0,sizeof(g_encoder_health));
      bw_reset(&g_break_wire);urw_reset(&g_uart_reject);ct_reset(&g_current);pc_reset(&g_peak);zh_reset(&g_zero_history);
    }'''
def hmi(s):
    for x in ('(2026102811,2026102812)','(2026102811, 2026102812)'):
        s=s.replace(x,x+', (2026102813,2026102812)')
    ast.parse(s);return s
def main():
    assert not OUT.exists()
    m=json.loads(read(BASE/'manifest.json'));assert m['built'] and m['selftest_pass']
    for table in ('source_sha256','build_sha256','verification_sha256'):
        for rel,d in m[table].items():assert sha(BASE/rel)==d
    for folder in ('UNOQ_MOTOR','web_hmi','libraries','build/nucleo'):
        shutil.copytree(BASE/folder,OUT/folder,ignore=shutil.ignore_patterns('__pycache__'))
    f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
    s=once(s,'FW_BUILD_ID = 2026102811U','FW_BUILD_ID = 2026102813U')
    write(f,once(s,OLD_BLOCK,NEW_BLOCK));write(OUT/'web_hmi/server.py',hmi(read(BASE/'web_hmi/server.py')))
    (OUT/'verification').mkdir();(OUT/'build/uno').mkdir()
    reports=('install_usb_r1/report.json','manual_usb_capture_r1/report.json','manual_usb_capture_r1/captured_status.json','manual_usb_capture_r1/native_wire_state.bin','manual_usb_capture_r1/frozen_ring.bin','manual_usb_capture_r1/wire.bin','manual_usb_capture_r1/after_reset_status.json')
    archived={str((BASE/rel).relative_to(ROOT)).replace('\\','/'):sha(BASE/rel) for rel in reports}
    write(OUT/'archive_references.json',json.dumps(archived,indent=2)+'\n')
    r=dict(schema='mic_ai.i2c_wire_epoch_fix.v1',pair_compatibility_ids=list(NEW),predecessor=str(BASE),
      built=False,selftest_pass=False,installed=False,uno_only=True,nucleo_firmware_unchanged=True,
      calibration_changed=False,uart_changed=False,motor_control_changed=False,thresholds_changed=False,
      rpc_libraries_changed=False,old_reset_criteria_unchanged=True,calibration_sha256=m['calibration_sha256'],
      waveform_on_hardware_verified=True,analog_or_external_timing_qualified=False,initial_pwm_i2c_fixed_or_proven=False)
    write(OUT/'manifest.json',json.dumps(r,indent=2)+'\n')
    print(json.dumps(dict(prepared=True,pair=NEW,nucleo_rebuild=False,hardware_commands=0)))
if __name__=='__main__':main()
