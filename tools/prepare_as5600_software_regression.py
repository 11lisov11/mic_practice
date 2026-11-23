"""Prepare a software regression experiment without changing motor firmware."""
import json
import shutil
import prepare_current_shunt_monitor as util

ROOT = util.ROOT
BASE = ROOT / 'artifacts/live_bench_20261025/as5600_i2c_diag_r1'
OUT = ROOT / 'artifacts/live_bench_20261025/as5600_software_regression_r1'
RES = ROOT / 'tools/as5600_software_regression'
FIELDS = ('thread_priority', 'cfg_expected', 'cfg_before', 'cfg_after', 'cfg_match',
          'last_cfg_before', 'last_cfg_after', 'tx_byte', 'tx_echo', 'tx_bits',
          'last_tx_byte', 'last_tx_echo', 'last_tx_bits')


def main():
    assert not OUT.exists(), 'Preserve previous experiment'
    m = json.loads(util.read(BASE / 'manifest.json'))
    assert m['installed'] and m['installation_runtime_pair_verified']
    for rel, digest in m['source_sha256'].items():
        assert util.sha(BASE / rel) == digest, rel
    for folder in ('UNOQ_MOTOR', 'web_hmi'):
        shutil.copytree(BASE / folder, OUT / folder, ignore=shutil.ignore_patterns('__pycache__'))
    sketch = OUT / 'UNOQ_MOTOR'
    shutil.copyfile(RES / 'worker.cpp', sketch / 'as5600_teacher.cpp')
    shutil.copyfile(RES / 'reader.h', sketch / 'as5600_i2c_reader.h')
    p = sketch / 'as5600_teacher.h'; s = util.read(p)
    s = util.once(s, '  float rpm = 0.0f;', '  float rpm = 0.0f;\n' + ''.join(
        f'  uint32_t diag_{f} = 0;\n' for f in FIELDS).rstrip())
    util.write(p, s)
    p = sketch / 'UNOQ_MOTOR.ino'; s = util.read(p)
    s = util.once(s, 'FW_BUILD_ID = 2026102513U;', 'FW_BUILD_ID = 2026102515U;')
    s = util.once(s, '  else if (icmp(arg, "SW25")) mode = 2;',
        '  else if (icmp(arg, "SW25")) mode = 2;\n  else if (icmp(arg, "LEGACY")) mode = 3;')
    anchor = '    s += " enc_diag_mode="; s += String((unsigned long)g_as5600.diag_mode);'
    s = util.once(s, anchor, anchor + '\n' + ''.join(
        f'    s += " enc_diag_{f}="; s += String((unsigned long)g_as5600.diag_{f});\n'
        for f in FIELDS).rstrip())
    util.write(p, s)
    p = OUT / 'web_hmi/server.py'; s = util.read(p)
    for old, new in (('(2026102513, 2026102510)', '(2026102513, 2026102510), (2026102515, 2026102510)'),
                     ('(2026102513,2026102510)', '(2026102513,2026102510),(2026102515,2026102510)')):
        assert old in s; s = s.replace(old, new)
    anchor = '                "enc_diag_mode": int(float(kv.get("enc_diag_mode", "0"))),'
    s = util.once(s, anchor, anchor + '\n' + ''.join(
        f'                "enc_diag_{f}": int(float(kv.get("enc_diag_{f}", "0"))),\n'
        for f in FIELDS).rstrip())
    util.write(p, s)
    manifest = dict(schema='mic_ai.as5600_software_regression.v1', predecessor=str(BASE),
        pair_compatibility_ids=[2026102515, 2026102510],
        uno_only=True, nucleo_firmware_unchanged=True, built=False, selftest_pass=False,
        installed=False, hardware_validated=False, root_cause_proven=False,
        calibration_changed=False, motor_control_changed=False, uart_protocol_changed=False,
        thresholds_changed=False, sd_capture_changed=False, sensor_feedback_control=False,
        calibration_sha256=m['calibration_sha256'],
        experiment='LEGACY native100k priority14 vs native100k priority4, same wires and motor firmware',
        mode_map={'0':'HW100/priority4', '1':'SW100/priority4', '2':'SW25/priority4', '3':'LEGACY/priority14'},
        readback_scope='SDA sampled at MCU during each transmitted bit; no proof of waveform at sensor',
        pin_cfg_encoding=dict(moder_bits='0..3', otyper_bits='4..5', pupdr_bits='6..9',
                              ospeedr_bits='10..13', afr_bits='14..21'),
        source_sha256={str(p.relative_to(OUT)).replace('\\','/'):util.sha(p)
            for folder in ('UNOQ_MOTOR','web_hmi') for p in (OUT/folder).rglob('*')
            if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'})
    (OUT / 'build/uno').mkdir(parents=True)
    util.write(OUT / 'manifest.json', json.dumps(manifest, indent=2) + '\n')
    print(OUT)


if __name__ == '__main__':
    main()
