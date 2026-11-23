"""Prepare UNO-only I2C diagnostic modes; preserve the installed motor firmware."""
from pathlib import Path
import argparse
import json
import shutil
import prepare_current_shunt_monitor as util

ROOT = util.ROOT
BASE = ROOT / 'artifacts/live_bench_20261024/current_adc_apex_fix_r1'
OUT = ROOT / 'artifacts/live_bench_20261025/as5600_i2c_diag_r1'
RES = ROOT / 'tools/as5600_i2c_diag'
FIELDS = ('mode', 'epoch', 'stage', 'cause', 'us', 'wait_us',
          'first_ms', 'first_stage', 'first_cause', 'first_us',
          'last_ms', 'last_mode', 'last_stage', 'last_cause', 'last_us')

HANDLER = '''static bool handle_encbus_command(const char *arg) {
  while (*arg == ' ' || *arg == '\\t') ++arg;
  uint8_t mode;
  if (icmp(arg, "HW100")) mode = 0;
  else if (icmp(arg, "SW100")) mode = 1;
  else if (icmp(arg, "SW25")) mode = 2;
  else return false;
  // Require fresh remote OFF as well as local OFF; no START can pass while
  // worker handover is pending. The command never clears faults or starts PWM.
  if (g_state != STATE_SAFE || g_pwm_enabled || g_pwm_outputs_active || g_start_req ||
      !g_bp_mcsdk_telemetry || g_bp_last_rsp_ms == 0 ||
      (uint32_t)(millis() - g_bp_last_rsp_ms) >= 300U ||
      (g_bp_status & BP_STATUS_PWM_ACTIVE) != 0U) return false;
  return as5600_diag_select(mode);
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh-uninstalled', action='store_true')
    args = parser.parse_args()
    if (OUT / 'manifest.json').exists():
        prior = json.loads(util.read(OUT / 'manifest.json'))
        assert args.refresh_uninstalled and prior['schema'] == 'mic_ai.as5600_i2c_diag.v1'
        assert prior['installed'] is False and prior['hardware_validated'] is False
    previous = json.loads(util.read(BASE / 'manifest.json'))
    assert previous['installed']
    for rel, digest in previous['source_sha256'].items():
        assert util.sha(BASE / rel) == digest, rel
    for tree in ('UNOQ_MOTOR', 'web_hmi'):
        shutil.copytree(BASE / tree, OUT / tree, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__'))
    sketch = OUT / 'UNOQ_MOTOR'
    shutil.copyfile(RES / 'reader.h', sketch / 'as5600_i2c_reader.h')
    shutil.copyfile(RES / 'worker.cpp', sketch / 'as5600_teacher.cpp')
    p = sketch / 'as5600_teacher.h'
    s = util.read(p)
    s = util.once(s, '  float rpm = 0.0f;', '  float rpm = 0.0f;\n' +
                  ''.join(f'  uint32_t diag_{f} = 0;\n' for f in FIELDS))
    s = util.once(s, '  As5600Sample sample() const',
                  '  void seed_counters(uint32_t reads, uint32_t errors) {\n'
                  '    sample_.reads = reads; sample_.errors = errors;\n'
                  '  }\n\n  As5600Sample sample() const')
    s += '\nbool as5600_diag_select(uint8_t mode);\nbool as5600_diag_ready();\n'
    util.write(p, s)
    p = sketch / 'UNOQ_MOTOR.ino'; s = util.read(p)
    s = util.once(s, 'FW_BUILD_ID = 2026102509U;', 'FW_BUILD_ID = 2026102513U;')
    s = util.once(s, 'static bool handle_mcfoc_command(const char *arg) {',
                  HANDLER + 'static bool handle_mcfoc_command(const char *arg) {')
    for indent in ('    ', '  '):
        anchor = '\n' + indent + '} else if (starts_ci(cmd, "MCFOC")) {'
        insert = ('\n' + indent + '} else if (starts_ci(cmd, "ENC BUS ")) {\n' +
                  indent + '  handled = handle_encbus_command(cmd + 8);\n')
        s = util.once(s, anchor, insert + anchor)
    s = util.once(s, 'static const char *start_precheck(uint32_t now_ms) {',
                  'static const char *start_precheck(uint32_t now_ms) {\n'
                  '  if (!as5600_diag_ready()) return "encoder bus handover pending";')
    anchor = '    s += " enc_init_error="; s += String((long)g_as5600.init_error);'
    s = util.once(s, anchor, anchor + '\n' + ''.join(
        f'    s += " enc_diag_{f}="; s += String((unsigned long)g_as5600.diag_{f});\n'
        for f in FIELDS).rstrip())
    util.write(p, s)
    p = OUT / 'web_hmi/server.py'; s = util.read(p)
    for old, new in (
        ('!= (2026102509, 2026102510):',
         'not in ((2026102509, 2026102510), (2026102513, 2026102510)):'),
        ('!= (2026102509,2026102510):',
         'not in ((2026102509,2026102510),(2026102513,2026102510)):'),
        ('        (2026102509, 2026102510),',
         '        (2026102509, 2026102510),\n        (2026102513, 2026102510),'),
        ('(2026102509,2026102510)) and',
         '(2026102509,2026102510),(2026102513,2026102510)) and'),
    ):
        assert old in s, old
        s = s.replace(old, new)
    anchor = '                "enc_init_error": int(float(kv.get("enc_init_error", "0"))),'
    s = util.once(s, anchor, anchor + '\n' + ''.join(
        f'                "enc_diag_{f}": int(float(kv.get("enc_diag_{f}", "0"))),\n'
        for f in FIELDS).rstrip())
    # This path is serialized with start/stop by the existing operation lock.
    anchor = '        normalized = " ".join(_cmd_tokens(cmd)).upper()'
    assert s.count(anchor) == 1
    s = util.once(s, anchor, anchor + '''
        if normalized.startswith("ENC BUS ") and app.hv_arm.snapshot()["hmi_hv_armed"]:
            self._send_json({"ok": False, "error": "Disarm before changing encoder bus mode"}, 409)
            return''')
    util.write(p, s)
    (OUT / 'build/uno').mkdir(parents=True, exist_ok=True)
    manifest = dict(schema='mic_ai.as5600_i2c_diag.v1', predecessor=str(BASE),
                    pair_compatibility_ids=[2026102513, 2026102510],
                    uno_only=True, nucleo_firmware_unchanged=True,
                    motor_control_changed=False, thresholds_changed=False,
                    calibration_changed=False, sd_capture_changed=False,
                    uart_protocol_changed=False, sensor_feedback_control=False,
                    installed=False, built=False, selftest_pass=False,
                    hardware_validated=False,
                    modes={'0': 'HW100 default', '1': 'SW100 nominal', '2': 'SW25 nominal'},
                    pins={'SDA': 'PB11/D20', 'SCL': 'PB10/D21'},
                    first_error='First error of boot; immutable across mode changes',
                    comparison_limitations=['Software timings include interrupt/scheduler delays',
                        'Software mode differentiates observed stages, not electrical root cause',
                        'Native driver still reports aggregate EIO; no fabricated ISR diagnosis'],
                    calibration_sha256=previous['calibration_sha256'])
    manifest['source_sha256'] = {str(p.relative_to(OUT)).replace('\\', '/'): util.sha(p)
                               for folder in ('UNOQ_MOTOR', 'web_hmi')
                               for p in (OUT / folder).rglob('*') if p.is_file()
                               and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    util.write(OUT / 'manifest.json', json.dumps(manifest, indent=2) + '\n')
    print(OUT)


if __name__ == '__main__':
    main()
