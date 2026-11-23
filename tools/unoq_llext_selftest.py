"""Regression for compile-success/load-failure caused by TLS in UNO Q ELF."""
import argparse
import json
from pathlib import Path
import tempfile

from prepare_unoq_llext_fix import ROOT, BASE, sketch, hmi
from unoq_llext_check import inspect
from ipm_break_wifi_selftest import load_module
from web_hmi_command_guard_selftest import safe_status


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir', type=Path, required=True)
    a = p.parse_args()
    out = a.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    records = []
    for rel, expected in (
        ('artifacts/live_bench_20261011/idle_deadline_fix/candidate_r2', True),
        ('artifacts/live_bench_20261011/rpc_priority_fix/candidate_r2', False),
        ('artifacts/live_bench_20261012/bridge_boot_fix/candidate_r1', False),
    ):
        result = inspect(ROOT / rel / 'uno_build/UNOQ_MOTOR.ino.elf')
        assert result['pass_'] is expected
        records.append(result)
    new = sketch((BASE / 'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text())
    assert 'k_current_get()' not in new
    assert new.count('k_thread_priority_set(k_sched_current_thread_query(), 4)') == 2
    setup = new[new.index('    if (k_mutex_init(&g_control_mutex)'):]
    assert setup.index('k_thread_priority_set') < setup.index('Bridge.begin')
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'server.py'
        path.write_text(hmi((BASE / 'web_hmi/server.py').read_text()))
        mod = load_module(path)
        assert not mod.hv_arm_precheck(safe_status(fw_build=2026101108, mc_fw_build=2026101102),
                                      mod.HvArmConfig(enabled=True), True)[0]
    result = dict(pass_=True, historical_elf_checks=records, cases=7,
                  hardware_commands=0, hardware_validated=False)
    result['pass'] = result.pop('pass_')
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'pass': True, 'cases': 7}))


if __name__ == '__main__':
    main()
