"""Prepare a one-function compatibility correction; never accesses hardware."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/live_bench_20261018/uart_tx_dma_manual_hmi_fix_r1'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    before = (OUT / 'server_before.py').read_bytes()
    installed = ROOT / 'artifacts/live_bench_20261018/uart_tx_dma_fix_r2/web_hmi/server.py'
    assert before == installed.read_bytes(), 'remote source differs from installed package'
    source = before.decode('utf-8')
    tree = ast.parse(source)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'manual_scalar_supported')
    lines = source.splitlines(keepends=True)
    old = ''.join(lines[fn.lineno-1:fn.end_lineno])
    assert '(2026101813,2026101812)' not in old
    new = old.replace('(2026101807,2026101806))', '(2026101807,2026101806),(2026101813,2026101812))')
    assert new != old
    changed = source.replace(old, new, 1)
    a = ast.parse(changed)
    for t in (tree, a):
        t.body = [n for n in t.body if not (isinstance(n, ast.FunctionDef) and n.name == 'manual_scalar_supported')]
    assert ast.dump(tree) == ast.dump(a), 'change extends beyond compatibility function'
    env = {'_as_int': lambda d,k,v: int(d.get(k,v))}
    exec(new, env)
    supported = env['manual_scalar_supported']
    cases = []
    for pair in ((2026101505,2026101504),(2026101507,2026101506),(2026101703,2026101702),(2026101807,2026101806),(2026101813,2026101812)):
        for cap in (0,1):
            d = dict(fw_build=pair[0],mc_fw_build=pair[1],manual_scalar_capable=cap)
            assert supported(d) == bool(cap)
            cases.append([pair,cap,bool(cap)])
    for pair in ((2026101813,2026101810),(2026101811,2026101812),(0,0)):
        assert not supported(dict(fw_build=pair[0],mc_fw_build=pair[1],manual_scalar_capable=1))
    assert not supported(None)
    candidate = changed.encode('utf-8')
    (OUT/'server.py').write_bytes(candidate)
    report = dict(pass_=True, original_sha256=sha(before), candidate_sha256=sha(candidate),
                  only_function_changed='manual_scalar_supported', cases=cases,
                  mismatched_pairs_rejected=True, authentication_and_all_start_guards_unchanged=True,
                  mcu_images_changed=False, hardware_commands=0)
    report['pass'] = report.pop('pass_')
    (OUT/'offline_check.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__': main()
