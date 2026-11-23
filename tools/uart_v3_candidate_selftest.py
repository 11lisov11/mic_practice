"""Offline CRC32C/NE candidate against extracted production control handlers."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from production_mcsdk_link_dynamic_selftest import CASES, PREAMBLE, generate
from prepare_uart_v3_candidate import nucleo_source
from uart_guard_release_selftest import replace_once


MUTATIONS = {
    "CRC_guard_removed": ("if (!uv3_crc_ok(rx->frame))", "if (false)"),
    "hard_error_guard_removed": ("if (flags & (uint8_t)~UV3_NE)", "if (false)"),
    "NE_budget_unbounded": ("if (rx->noise_used >= UV3_NE_BUDGET) return false;",
                            "if (rx->noise_used >= UV3_NE_BUDGET) rx->noise_used = 0;"),
    "changed_command_allowed": ("if (i != 5 && rx->frame[i] != rx->previous[i]) return false;",
                                "if (false && i != 5 && rx->frame[i] != rx->previous[i]) return false;"),
    "clean_recovery_removed": ("rx->clean_run_frames < UV3_CLEAN_REQUIRED ||",
                               "false ||"),
    "frame_deadline_removed": ("rx->index != 0 && (uint32_t)(now_ms - rx->frame_started_ms) > UV3_FRAME_DEADLINE_MS",
                               "false"),
    "sequence_guard_removed": ("rx->run_anchor && rx->frame[3] == 1 &&",
                               "false && rx->run_anchor && rx->frame[3] == 1 &&"),
    "latched_estop_watchdog_not_disarmed": ("rx->link_seen = false;", "(void)rx->link_seen;"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--integrated", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    header_path = root / "research/uart_v3/uart_v3_transport.h"
    scenario_path = root / "research/uart_v3/host_scenarios.cpp"
    report = {"pass": False, "hardware_commands": 0, "hardware_validated": False,
              "flash_ready": False, "installed_firmware_modified": False,
              "scope": "candidate transport with unchanged production semantic handlers and mocked HAL/MCSDK",
              "hypothesis": "isolated intact NE on unchanged RUN heartbeat can be accepted within a bounded budget",
              "limitations": ["No evidence that the recorded physical NE accompanied an intact byte",
                              "ISR per-byte flag association and peer codec are not yet integrated",
                              "8-bit sequence cannot protect against long-delayed replay across wrap",
                              "CRC is not authentication or a safety certification",
                              "Finite corruption sweep, not every possible multi-bit error"]}
    try:
        program, sources = generate(root)
        helpers = CASES[:CASES.index("void scenarios()")]
        if args.integrated:
            original_block = program[len(PREAMBLE):program.index(CASES)]
            macros = original_block[:original_block.index("enum {")]
            candidate = nucleo_source(root)
            begin = candidate.index("enum {", candidate.index("/* USER CODE BEGIN 0 */"))
            end = candidate.index("static void MX_USART1_UART_Init(void) {", begin)
            preamble = replace_once(PREAMBLE, "std::array<uint8_t, 32> reply;",
                                    "std::array<uint8_t, UV3_FRAME> reply;")
            helpers = replace_once(helpers, "void checksum(Frame &f) { f.back()=uno_crc_xor(f.data()); }",
                                   "void checksum(Frame &f) { uv3_seal(f.data()); }")
            helpers = replace_once(helpers, "uno_consume_byte(b)", "uno_consume_sample(b, 0)")
            # Host-only RDR read side effect; firmware still reads the hardware register.
            block = replace_once(candidate[begin:end], "(uint8_t)huart1.Instance->RDR",
                                 "mock_read_rdr()")
            mock_read = "uint8_t mock_read_rdr() { uart_registers.ISR &= ~UART_FLAG_RXNE; return (uint8_t)uart_registers.RDR; }\n"
            program = ('#define UV3_INTEGRATED_TEST 1\n#include "uart_v3_transport.h"\n' +
                       preamble + mock_read + macros + block + helpers + scenario_path.read_text(encoding="utf-8"))
            sources += [root / "tools/prepare_uart_v3_candidate.py",
                        root / "research/uart_v3/nucleo_fifo.c.inc", root / "research/uart_v3/nucleo_parser.c.inc"]
            report["scope"] = "integrated candidate parser/ISR/FIFO with mocked RDR read side effects and HAL/MCSDK"
            report["limitations"][1] = "Physical per-byte flag association and MCU timing remain unqualified"
        else:
            program = replace_once(program, CASES, helpers + scenario_path.read_text(encoding="utf-8"))
        header = header_path.read_text(encoding="utf-8")
        sources += [header_path, scenario_path, Path(__file__).resolve()]
        before = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
        report["source_sha256"] = before
        compiler = shutil.which("g++")
        if not compiler:
            raise RuntimeError("g++ required")
        (out / "host_test.cpp").write_text(program, encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            unit, exe = folder / "host.cpp", folder / "host.exe"
            unit.write_text(program, encoding="utf-8")
            mutations = []
            for label in ["candidate"] + list(MUTATIONS):
                body = header
                if label != "candidate":
                    body = replace_once(body, *MUTATIONS[label])
                (folder / header_path.name).write_text(body, encoding="utf-8")
                built = subprocess.run([compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                                        str(unit), "-o", str(exe)], capture_output=True, text=True, timeout=90)
                (out / f"{label}_compile.log").write_text(built.stdout + built.stderr, encoding="utf-8")
                if built.returncode:
                    raise RuntimeError(f"{label} did not compile")
                run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
                (out / f"{label}_run.log").write_text(run.stdout + run.stderr, encoding="utf-8")
                if label == "candidate":
                    if run.returncode:
                        raise RuntimeError(run.stderr.strip())
                    report.update(json.loads(run.stdout))
                else:
                    mutations.append({"name": label, "detected": run.returncode != 0 and "FAIL " in run.stderr,
                                      "failure": run.stderr.strip()})
            report["mutations"] = mutations
        after = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
        report["sources_unchanged_during_tests"] = before == after
        report["pass"] = report["pass"] and before == after and all(m["detected"] for m in mutations)
    except Exception as exc:
        report["pass"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
