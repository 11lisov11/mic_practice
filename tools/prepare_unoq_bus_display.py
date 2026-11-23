"""Prepare a matrix-only Uno update; never contact or flash hardware."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/live_bench_20261024/vf_smooth_start_r1'
OUT = ROOT / 'artifacts/live_bench_20261024/uno_bus_display_r1'
OLD, NEW = (2026102401, 2026102402), (2026102403, 2026102402)

IDLE_BRANCH = '''  if (!g_pwm_enabled) {
    // Display the accepted Nucleo bus measurement even at zero Hz, ESTOP
    // or an idle fault. Never use the default/stale g_vdc as a zero indication.
    const bool voltage_fresh = NUCLEO_MCSDK_ACIM_BACKEND && g_bp_mcsdk_telemetry &&
      g_bp_fw_build == 2026102402U && g_bp_vbus_valid &&
      g_bp_vbus_ms != 0U && g_bp_last_rsp_ms != 0U &&
      (uint32_t)(now - g_bp_vbus_ms) <= BP_VBUS_STALE_MS &&
      (uint32_t)(now - g_bp_last_rsp_ms) <= BP_REPLY_TIMEOUT_MS &&
      isfinite(g_bp_vdc) && g_bp_vdc >= 0.0f && g_bp_vdc <= 999.0f;
    if (voltage_fresh) {
      const int volts = (int)(g_bp_vdc + 0.5f);
      if (volts >= 100) matrix_draw_digit(x0, y0, volts / 100);
      if (volts >= 10) matrix_draw_digit(x0 + 4, y0, (volts / 10) % 10);
      matrix_draw_digit(x0 + 8, y0, volts % 10);
    } else {
      // Three dashes mean unavailable, never a measured zero.
      for (int digit = 0; digit < 3; ++digit)
        for (int x = 0; x < 3; ++x) matrix_set_pixel(x0 + 4*digit + x, y0 + 2);
    }
    // Small V below the digits identifies DC-bus volts, without a decimal.
    matrix_set_pixel(0, 6);
    matrix_set_pixel(2, 6);
    matrix_set_pixel(1, 7);
  } else if (show_rpm) {'''


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def once(s, a, b):
    assert s.count(a) == 1, a
    return s.replace(a, b)


def main():
    assert not OUT.exists(), 'Preserve existing candidate'
    manifest = json.loads((BASE / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['installed'] and manifest['installation_runtime_connection_verified']
    for rel, expected in manifest['source_sha256'].items():
        assert sha(BASE / rel) == expected, rel
    for tree in ('UNOQ_MOTOR', 'web_hmi'):
        shutil.copytree(BASE / tree, OUT / tree, ignore=shutil.ignore_patterns('__pycache__'))
    (OUT / 'build/uno').mkdir(parents=True)
    p = OUT / 'UNOQ_MOTOR/UNOQ_MOTOR.ino'
    s = p.read_text(encoding='utf-8-sig')
    s = once(s, 'FW_BUILD_ID = 2026102401U;', 'FW_BUILD_ID = 2026102403U;')
    s = once(s, '  // SAFE shows the Wi-Fi frequency command immediately. While running, the\n  // matrix alternates each second between electrical Hz and calculated RPM.',
             '  // Stopped: DC bus in whole volts with a V marker, or --- if stale.\n  // Running: retain the existing alternating electrical Hz / calculated RPM.')
    s = once(s, '  if (show_rpm) {', IDLE_BRANCH)
    p.write_text(s, encoding='utf-8', newline='\n')
    p = OUT / 'web_hmi/server.py'
    s = p.read_text(encoding='utf-8-sig')
    s = once(s, '        (2026102401, 2026102402),',
             '        (2026102401, 2026102402),\n        (2026102403, 2026102402),')
    s = once(s, '(2026102401,2026102402)) and',
             '(2026102401,2026102402),(2026102403,2026102402)) and')
    p.write_text(s, encoding='utf-8', newline='\n')
    m = dict(schema='mic_ai.uno_bus_display.v1', predecessor=str(BASE),
             pair_compatibility_ids=list(NEW), built=False, selftest_pass=False, installed=False,
             uno_only=True, nucleo_firmware_unchanged=True, nucleo_build_id=NEW[1],
             calibration_changed=False, uart_changed=False, motor_control_changed=False,
             display_idle='Accepted Nucleo DC bus rounded to whole volts, with V marker',
             display_unavailable='--- with V marker', stale_after_ms=500,
             active_display_unchanged=True, startup_matrix_selftest_unchanged=True,
             calibration_contract='Same existing Nucleo engineering-unit bus telemetry as HMI; verification points untouched',
             physical_display_verified=False, hardware_commands=0)
    (OUT / 'manifest.json').write_text(json.dumps(m, indent=2)+'\n', encoding='utf-8')
    print(OUT)


if __name__ == '__main__':
    main()
