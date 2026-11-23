"""Fix RPC startup ordering and avoid reinitializing an active failed Bridge instance."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from prepare_unoq_rx_fix import ROOT
from prepare_ipm_break_wifi import source_hashes
from prepare_mcsdk_logic_bench import replace_once

BASE=ROOT/'artifacts/live_bench_20261011/rpc_priority_fix/candidate_r2'
BUILD=2026101107


def sketch(text):
    text=replace_once(text,'FW_BUILD_ID = 2026101106U',f'FW_BUILD_ID = {BUILD}U')
    text=replace_once(text,'    if (k_mutex_init(&g_control_mutex) != 0) k_panic();\n    delay(6000);\n    Bridge.begin(RPC_BAUD);',
        '    if (k_mutex_init(&g_control_mutex) != 0) k_panic();\n'
        '    if (NUCLEO_MCSDK_ACIM_BACKEND) k_thread_priority_set(k_current_get(), 4);\n'
        '    delay(6000);\n'
        '    if (!Bridge.begin(RPC_BAUD) && NUCLEO_MCSDK_ACIM_BACKEND) NVIC_SystemReset();')
    text=replace_once(text,'                  nullptr, nullptr, nullptr, CONFIG_NUM_PREEMPT_PRIORITIES - 1, 0, K_NO_WAIT);',
        '                  nullptr, nullptr, nullptr, NUCLEO_MCSDK_ACIM_BACKEND ? 4 : CONFIG_NUM_PREEMPT_PRIORITIES - 1, 0, K_NO_WAIT);')
    text=replace_once(text,'  if (!Bridge) {\n    g_bridge_ready = Bridge.begin(RPC_BAUD);',
        '  if (!Bridge) {\n'
        '    // This function already refuses active local or peer PWM. A failed begin\n'
        '    // still owns a running updater thread: do not recreate it in-place.\n'
        '    if (NUCLEO_MCSDK_ACIM_BACKEND) { NVIC_SystemReset(); return; }\n'
        '    g_bridge_ready = Bridge.begin(RPC_BAUD);')
    return replace_once(text,'  s += " uno_control_priority=";',
        '  s += " uno_bridge_service_priority="; s += String(NUCLEO_MCSDK_ACIM_BACKEND ? 4 : CONFIG_NUM_PREEMPT_PRIORITIES - 1);\n'
        '  s += " uno_control_priority=";')


def hmi(text):
    text=replace_once(text,'(2026101106, 2026101102)):',
        '(2026101106, 2026101102), (2026101107, 2026101102)):')
    return replace_once(text,'("uno_control_priority", "uno_rpc_priority",',
        '("uno_bridge_service_priority", "uno_control_priority", "uno_rpc_priority",')


def prepare(out):
    before=source_hashes(BASE/'UNOQ_MOTOR'); out.mkdir(parents=True,exist_ok=False)
    shutil.copytree(BASE/'UNOQ_MOTOR',out/'UNOQ_MOTOR')
    shutil.copytree(BASE/'web_hmi',out/'web_hmi',ignore=shutil.ignore_patterns('__pycache__','.venv'))
    for rel,patch in (('UNOQ_MOTOR/UNOQ_MOTOR.ino',sketch),('web_hmi/server.py',hmi)):
        p=out/rel; p.write_text(patch(p.read_text()),encoding='utf-8')
    if before!=source_hashes(BASE/'UNOQ_MOTOR'): raise RuntimeError('Baseline changed')
    result=dict(uno_build=BUILD,nucleo_build=2026101102,baseline_source_sha256=before,
        source_sha256=source_hashes(out/'UNOQ_MOTOR'),
        hmi_sha256=hashlib.sha256((out/'web_hmi/server.py').read_bytes()).hexdigest(),
        expected_live_hmi_sha256=hashlib.sha256((BASE/'web_hmi/server.py').read_bytes()).hexdigest(),
        initialized_priority_before_bridge=True,bridge_service_priority=4,watchdog_ms=300,
        installed=False,hv_release_approved=False,boot_failure_recovery='MCU reset, outputs-off only; no automatic START')
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n'); return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args(); print(json.dumps(prepare(a.outdir.resolve())))
