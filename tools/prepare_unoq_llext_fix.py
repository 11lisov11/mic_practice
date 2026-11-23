"""Remove TLS references from the dynamically loaded UNO Q control sketch."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from prepare_unoq_bridge_boot_fix import ROOT, source_hashes
from prepare_mcsdk_logic_bench import replace_once

BASE = ROOT / 'artifacts/live_bench_20261012/bridge_boot_fix/candidate_r1'
BUILD = 2026101108


def sketch(text):
    text = replace_once(text, 'FW_BUILD_ID = 2026101107U', f'FW_BUILD_ID = {BUILD}U')
    old = 'k_thread_priority_set(k_current_get(), 4)'
    if text.count(old) != 2:
        raise RuntimeError('Expected the two setup priority promotions')
    return text.replace(old, 'k_thread_priority_set(k_sched_current_thread_query(), 4)')


def hmi(text):
    return replace_once(text, '(2026101107, 2026101102)):',
                        '(2026101107, 2026101102), (2026101108, 2026101102)):')


def prepare(out):
    before = source_hashes(BASE / 'UNOQ_MOTOR')
    out.mkdir(parents=True, exist_ok=False)
    shutil.copytree(BASE / 'UNOQ_MOTOR', out / 'UNOQ_MOTOR')
    shutil.copytree(BASE / 'web_hmi', out / 'web_hmi',
                    ignore=shutil.ignore_patterns('__pycache__', '.venv'))
    for rel, patch in (('UNOQ_MOTOR/UNOQ_MOTOR.ino', sketch), ('web_hmi/server.py', hmi)):
        p = out / rel
        p.write_text(patch(p.read_text()), encoding='utf-8')
    if before != source_hashes(BASE / 'UNOQ_MOTOR'):
        raise RuntimeError('Baseline changed')
    result = dict(uno_build=BUILD, nucleo_build=2026101102,
                  baseline_source_sha256=before, source_sha256=source_hashes(out / 'UNOQ_MOTOR'),
                  hmi_sha256=hashlib.sha256((out / 'web_hmi/server.py').read_bytes()).hexdigest(),
                  tls_free_current_thread_query=True, installed=False, hv_release_approved=False)
    (out / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(prepare(a.outdir.resolve())))
