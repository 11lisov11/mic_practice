"""Prepare only the passive HMI peer decoder; never flash or contact the stand."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/live_bench_20261012/local_button/short_trial_candidate_r2/web_hmi/server.py"
BASE_SHA = "88f0764f881b5bbc7cb8e1e0b40954fe7d2e63450edd568cd8b92f83550d2d6b"
CAL_SHA = "a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17"
OLD = "peer != 2026101102"
NEW = "peer not in (2026101102, 2026101204)"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def control_ast(text):
    tree = ast.parse(text)
    tree.body = [node for node in tree.body
                 if not isinstance(node, ast.FunctionDef) or node.name != "break_wire_status"]
    return ast.dump(tree, include_attributes=False)


def compatibility():
    old = ROOT / "artifacts/live_bench_20261011/ipm_break_wifi/candidate_r6/nucleo/Inc"
    new = ROOT / "artifacts/live_bench_20261012/local_button/candidate_r5/nucleo/Inc"
    expected = {
        old / "break_wire.h": "b083e0afaea382882515c9950e16fc2b0454ea2014885ea1372088e98c9ec2b3",
        new / "break_wire.h": "96d7d0b72c0fb32a1a35618e2228b9f16340692d2299836f5ed648fd438966c6",
        old / "first_break_snapshot.h": "68a274abe3239bc6b3103c7d8c3f6e07e80f1ec956c6efabc13a0a4e21f24302",
        new / "first_break_snapshot.h": "68a274abe3239bc6b3103c7d8c3f6e07e80f1ec956c6efabc13a0a4e21f24302",
    }
    for path, digest in expected.items():
        if sha(path) != digest:
            raise RuntimeError("Frozen ABI source changed: " + str(path))
    normalize = lambda text: re.sub(r"\s+", "", text.replace("2026101204UL", "2026101102UL"))
    if normalize((old / "break_wire.h").read_text()) != normalize((new / "break_wire.h").read_text()):
        raise RuntimeError("Diagnostic wire source differs beyond build ID and whitespace")
    return {str(path.relative_to(ROOT)): digest for path, digest in expected.items()}


def prepare(out):
    if sha(BASE) != BASE_SHA:
        raise RuntimeError("Installed frozen HMI baseline changed")
    evidence = compatibility()
    before = BASE.read_text(encoding="utf-8")
    if before.count(OLD) != 1:
        raise RuntimeError("Expected one passive peer predicate")
    after = before.replace(OLD, NEW)
    if control_ast(before) != control_ast(after):
        raise RuntimeError("Change outside the passive decoder")
    canonical = (ROOT / "research/ipm_break/hmi_snapshot.py").read_text(encoding="utf-8")
    function_ast = lambda text: ast.dump(next(n for n in ast.parse(text).body
        if isinstance(n, ast.FunctionDef) and n.name == "break_wire_status"), include_attributes=False)
    if function_ast(canonical) != function_ast(after):
        raise RuntimeError("Canonical passive decoder does not match the candidate")
    compile(after, "server.py", "exec")
    out.mkdir(parents=True, exist_ok=False)
    target = out / "web_hmi/server.py"
    target.parent.mkdir()
    target.write_text(after, encoding="utf-8", newline="\n")
    report = dict(schema="mic_ai.passive_break_decoder_fix.v1", base_sha256=BASE_SHA,
        hmi_sha256=sha(target), pair=[2026101205, 2026101204],
        accepted_snapshot_peers=[2026101102, 2026101204], diagnostic_schema=2,
        diagnostic_bytes=92, abi_source_sha256=evidence, installed=False,
        hardware_commands=0, mcu_firmware_changed=False, calibration_file_modified=False,
        control_guards_changed=False, control_ast_identical=True, hv_release_approved=False)
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.outdir.resolve()), indent=2))
