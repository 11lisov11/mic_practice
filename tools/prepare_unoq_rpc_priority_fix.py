"""Isolate MCSDK supervision from bulk RouterBridge responses without changing motor protocol."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from prepare_unoq_rx_fix import ROOT
from prepare_ipm_break_wifi import source_hashes
from prepare_mcsdk_logic_bench import replace_once

BASE=ROOT/'artifacts/live_bench_20261011/idle_deadline_fix/candidate_r2'
BUILD=2026101106


def sketch(text):
    text=replace_once(text,'FW_BUILD_ID = 2026101105U',f'FW_BUILD_ID = {BUILD}U')
    # UNO Q's postvariant.h includes RouterBridge from Arduino.h already.
    text=replace_once(text,'#include <Arduino.h>',
        '// Rename the vendor fallback before postvariant.h implicitly includes RouterBridge.\n'
        '#define __loopHook mic_router_compat_hook\n'
        '#include <Arduino.h>\n'
        '#undef __loopHook')
    text=replace_once(text,'#include <Arduino_RouterBridge.h>',
        '#include <Arduino_RouterBridge.h>\n'
        'static_assert(UPDATE_THREAD_PRIORITY == 5, "Review RouterBridge scheduling after library update");')
    text=replace_once(text,'void loop() {\n#if USE_ROUTER_BRIDGE',
        '#if USE_ROUTER_BRIDGE\n'
        'void __loopHook() {\n'
        '  if (!NUCLEO_MCSDK_ACIM_BACKEND) mic_router_compat_hook();\n'
        '}\n'
        '#endif\n'
        'void loop() {\n#if USE_ROUTER_BRIDGE')
    text=replace_once(text,'  g_last_control_us = micros();',
        '  // MCSDK supervision outranks bulk RPC TX, but sleeps each tick so RPC can progress.\n'
        '#if USE_ROUTER_BRIDGE\n'
        '  if (NUCLEO_MCSDK_ACIM_BACKEND) k_thread_priority_set(k_current_get(), 4);\n'
        '#endif\n'
        '  g_last_control_us = micros();')
    text=replace_once(text,'  k_yield();\n#endif\n}',
        '  if (NUCLEO_MCSDK_ACIM_BACKEND) k_msleep(1);\n'
        '  else k_yield();\n#endif\n}')
    return replace_once(text,'  s += " uno_local_adc_acquired=";',
        '  s += " uno_control_priority="; s += String(NUCLEO_MCSDK_ACIM_BACKEND ? 4 : CONFIG_MAIN_THREAD_PRIORITY);\n'
        '  s += " uno_rpc_priority="; s += String(UPDATE_THREAD_PRIORITY);\n'
        '  s += " uno_local_adc_acquired=";')


def sensor(text):
    text=replace_once(text,'CONFIG_NUM_PREEMPT_PRIORITIES - 1, 0, K_NO_WAIT);','4, 0, K_NO_WAIT);')
    return replace_once(text,'// Lowest preemptible priority; I2C waits leave UART/RPC runnable.',
        '// I2C blocks outside control ownership; sampling is not starved by bulk RPC TX.')


def hmi(text):
    text=replace_once(text,'(2026101105, 2026101102)):',
        '(2026101105, 2026101102), (2026101106, 2026101102)):')
    return replace_once(text,'**{k: int(kv[k]) for k in ("uno_local_adc_acquired",',
        '**{k: int(kv[k]) for k in ("uno_control_priority", "uno_rpc_priority", "uno_local_adc_acquired",')


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    before=source_hashes(BASE/'UNOQ_MOTOR')
    shutil.copytree(BASE/'UNOQ_MOTOR',out/'UNOQ_MOTOR')
    shutil.copytree(BASE/'web_hmi',out/'web_hmi',ignore=shutil.ignore_patterns('__pycache__','.venv'))
    for rel,patch in (('UNOQ_MOTOR/UNOQ_MOTOR.ino',sketch),
            ('UNOQ_MOTOR/as5600_teacher.cpp',sensor),('web_hmi/server.py',hmi)):
        p=out/rel; p.write_text(patch(p.read_text()),encoding='utf-8')
    if source_hashes(BASE/'UNOQ_MOTOR')!=before: raise RuntimeError('Baseline changed')
    # Correct the stale comment without changing sensor logic or Wire bus configuration.
    p=out/'UNOQ_MOTOR/as5600_teacher.cpp'
    p.write_text(p.read_text().replace('// Lowest preemptible priority; I2C waits leave UART/RPC runnable.',
        '// I2C blocks outside control ownership; sampling is not starved by bulk RPC TX.'),encoding='utf-8')
    manifest=dict(uno_build=BUILD,nucleo_build=2026101102,baseline_source_sha256=before,
        source_sha256=source_hashes(out/'UNOQ_MOTOR'),
        hmi_sha256=hashlib.sha256((out/'web_hmi/server.py').read_bytes()).hexdigest(),
        expected_live_hmi_sha256=hashlib.sha256((BASE/'web_hmi/server.py').read_bytes()).hexdigest(),
        control_priority=4,rpc_priority=5,sensor_priority=4,control_sleep_ms=1,
        dedicated_bridge_updater=True,no_independent_enable_replay_thread=True,
        installed=False,hv_release_approved=False,watchdog_ms=300)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args(); print(json.dumps(prepare(a.outdir.resolve())))
