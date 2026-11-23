"""Prepare UNO-only horizontal matrix correction; preserve installed capture firmware."""
import json
from pathlib import Path
import shutil
import prepare_current_shunt_monitor as util
from current_peak_capture.display_orientation import NEW as PREVIOUS_MAPPING

ROOT=util.ROOT
BASE=ROOT/'artifacts/live_bench_20261024/current_peak_capture_r1'
OUT=BASE.parent/'uno_display_order_r2'
OLD=(2026102501,2026102502)
NEW=(2026102503,2026102502)
MAPPING='''  // Compensate both axes for the inverted bench mounting. The previous
  // Y-only mapping was physically reported as 10 -> 01. Keep the Y flip
  // and add X compensation to the whole image, including glyphs/markers.
  g_matrix_pixels[(MATRIX_H - 1 - y) * MATRIX_W + (MATRIX_W - 1 - x)] = 1;'''


def main():
    assert not OUT.exists(), 'Preserve previous candidate'
    manifest=json.loads(util.read(BASE/'manifest.json'))
    assert manifest['installed'] and manifest['installation_runtime_pair_verified']
    for rel,digest in manifest['source_sha256'].items():
        assert util.sha(BASE/rel)==digest,rel
    for folder in ('UNOQ_MOTOR','web_hmi'):
        shutil.copytree(BASE/folder,OUT/folder,ignore=shutil.ignore_patterns('__pycache__'))
    p=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino'
    source=util.read(p)
    source=util.once(source,'FW_BUILD_ID = 2026102501U;','FW_BUILD_ID = 2026102503U;')
    util.write(p,util.once(source,PREVIOUS_MAPPING,MAPPING))
    p=OUT/'web_hmi/server.py';source=util.read(p)
    source=util.once(source,"if (data.get('fw_build'), data.get('mc_fw_build')) != (2026102501, 2026102502):",
        "if (data.get('fw_build'), data.get('mc_fw_build')) not in ((2026102501, 2026102502), (2026102503, 2026102502)):")
    source=util.once(source,"if (data.get('fw_build'),data.get('mc_fw_build')) != (2026102501,2026102502):",
        "if (data.get('fw_build'),data.get('mc_fw_build')) not in ((2026102501,2026102502),(2026102503,2026102502)):")
    source=util.once(source,'        (2026102501, 2026102502),',
        '        (2026102501, 2026102502),\n        (2026102503, 2026102502),')
    source=util.once(source,'(2026102501,2026102502)) and',
        '(2026102501,2026102502),(2026102503,2026102502)) and')
    util.write(p,source)
    (OUT/'build/uno').mkdir(parents=True)
    m=dict(schema='mic_ai.uno_bus_display.v1',predecessor=str(BASE),
        pair_compatibility_ids=list(NEW),built=False,selftest_pass=False,installed=False,
        uno_only=True,nucleo_firmware_unchanged=True,nucleo_build_id=NEW[1],
        calibration_changed=False,uart_changed=False,motor_control_changed=False,
        capture_protocol_changed=False,zero_calibration_changed=False,
        display_mapping='raw_x=12-x, raw_y=7-y',
        physical_feedback='Installed 2501/Y-only mapping displays10V as01; user confirmed',
        physical_orientation_verified=False,hardware_commands=0,
        calibration_sha256=manifest['calibration_sha256'])
    util.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(OUT)


if __name__=='__main__':
    main()
