"""Exercise archive validation with coherent but invalid metadata and damaged files."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import zipfile

from package_uart_guard_update import verify_archive, verify_payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    with zipfile.ZipFile(args.archive) as archive:
        payload = {name: archive.read(name) for name in archive.namelist()}
    cases = {"valid_archive": verify_archive(args.archive)["pass"]}

    def edit_json(files, name, update):
        value = json.loads(files[name])
        update(value)
        files[name] = (json.dumps(value, indent=2) + "\n").encode("utf-8")
        if name != "manifest.json":
            manifest = json.loads(files["manifest.json"])
            entry = next(e for e in manifest["files"] if e["file"] == name)
            entry.update(bytes=len(files[name]), sha256=hashlib.sha256(files[name]).hexdigest())
            files["manifest.json"] = json.dumps(manifest).encode("utf-8")

    def rejected(name, update):
        files = dict(payload)
        update(files)
        try:
            verify_payload(files)
            cases[name] = False
        except (ValueError, KeyError):
            cases[name] = True

    for name in ("nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin", "uno_q/UNOQ_MOTOR.ino.elf-zsk.bin",
                 "linux/web_hmi/server.py", "source/nucleo/Src/main.c"):
        rejected("damaged_" + name, lambda f, n=name: f.__setitem__(n, f[n] + b"!"))
    rejected("missing_image", lambda f: f.pop("nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex"))
    rejected("unexpected_file", lambda f: f.__setitem__("unexpected.bin", b"x"))
    rejected("wrong_build_pair", lambda f: edit_json(f, "manifest.json",
             lambda m: m["builds"].update(nucleo=2026100710)))
    rejected("false_hardware_claim", lambda f: edit_json(f, "manifest.json",
             lambda m: m.update(hardware_acceptance=True)))
    rejected("failing_child_with_green_summary", lambda f: edit_json(f, "reports/regression/report.json",
             lambda m: m["tests"][0].update(**{"pass": False, "exit_code": 1})))
    rejected("failing_detail_with_green_summary", lambda f: edit_json(f,
             "reports/regression/production_mcsdk_link_dynamic_selftest/report.json",
             lambda m: m.update(**{"pass": False})))
    rejected("repeated_test_names", lambda f: edit_json(f, "reports/regression/report.json",
             lambda m: m["tests"].__setitem__(1, copy.deepcopy(m["tests"][0]))))
    rejected("source_changed_after_tests", lambda f: edit_json(f, "reports/regression/report.json",
             lambda m: m.update(sources_unchanged_during_tests=False)))
    rejected("source_hash_mismatch_with_rehashed_manifest", lambda f: edit_json(f,
             "reports/regression/report.json", lambda m: m["source_sha256"].update(
                 {"web_hmi/server.py": "0" * 64})))
    report = {"pass": all(cases.values()), "cases": cases, "hardware_commands": 0,
              "scope": "Archive integrity and false qualification claims; not cryptographic authentication"}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
