"""Replay corrupt commands through unchanged production Nucleo code, offline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from production_mcsdk_link_dynamic_selftest import CASES, generate
from uart_guard_release_selftest import replace_once


TESTS = r'''
unsigned cases, xor_collisions;
void running(uint8_t seq) {
 reset(true);
 feed(frame(UNO_FLAG_ENABLE, UNO_MODE_SCALAR, 10000, seq));
 check(starts == 1 && uno_link.command_enabled && motor_state == RUN,
       "clean initial frame starts simulated motor");
}
void single_bit_errors() {
 for (unsigned seq = 0; seq < 256; ++seq) {
  for (unsigned pos = 2; pos < UNO_FRAME_LEN; ++pos) {
   for (unsigned bit = 0; bit < 8; ++bit) {
    running((uint8_t)(seq - 1));
    Frame bad = frame(UNO_FLAG_ENABLE, UNO_MODE_SCALAR, 20000, (uint8_t)seq);
    bad[pos] ^= (uint8_t)(1U << bit);
    const unsigned previous_ramps = ramps;
    feed(bad);
    check(uno_link.first_reason == UNO_DIAG_CRC && uno_link.fault_latched,
          "single payload or checksum bit always trips checksum guard");
    check(!uno_link.command_enabled && motor_state == IDLE && ramps == previous_ramps,
          "corrupted command never changes ramp and stops existing RUN");
    feed(frame(UNO_FLAG_ENABLE, UNO_MODE_SCALAR, 20000, (uint8_t)(seq + 1)));
    check(starts == 1 && uno_link.fault_latched && !uno_link.command_enabled,
          "later clean ENABLE cannot clear corruption fault or restart");
    ++cases;
   }
  }
 }
}
void lost_sync_and_byte_edits() {
 for (unsigned pos = 0; pos < UNO_FRAME_LEN; ++pos) {
  for (unsigned bit = 0; bit < 8; ++bit) {
   if (pos >= 2) break;
   running(80);
   Frame bad = frame(UNO_FLAG_ENABLE, UNO_MODE_SCALAR, 20000, 81);
   bad[pos] ^= (uint8_t)(1U << bit);
   const unsigned previous_ramps = ramps;
   feed(bad);
   check(ramps == previous_ramps && starts == 1, "bad header cannot update command");
   now_ms += UNO_LINK_TIMEOUT_MS + 1U;
   uno_link_poll();
   check(!uno_link.command_enabled && motor_state == IDLE && uno_link.fault_latched,
         "watchdog stops RUN when damaged header hides whole frame");
   ++cases;
  }
  running(80);
  Frame bad = frame(UNO_FLAG_ENABLE, UNO_MODE_SCALAR, 20000, 81);
  for (unsigned i = 0; i < UNO_FRAME_LEN; ++i) {
   if (i != pos) uno_consume_byte(bad[i]);
  }
  feed(frame(0, UNO_MODE_OFF, 0, 82));
  now_ms += UNO_LINK_TIMEOUT_MS + 1U;
  uno_link_poll();
  check(starts == 1 && !uno_link.command_enabled && motor_state == IDLE,
        "deleted byte followed by STOP cannot leave RUN beyond watchdog");
  ++cases;
  for (unsigned inserted = 0; inserted < 256; ++inserted) {
   running(80);
   for (unsigned i = 0; i < UNO_FRAME_LEN; ++i) {
    if (i == pos) uno_consume_byte((uint8_t)inserted);
    uno_consume_byte(bad[i]);
   }
   feed(frame(0, UNO_MODE_OFF, 0, 82));
   now_ms += UNO_LINK_TIMEOUT_MS + 1U;
   uno_link_poll();
   check(starts == 1 && !uno_link.command_enabled && motor_state == IDLE,
         "inserted byte followed by STOP cannot leave RUN beyond watchdog");
   ++cases;
  }
 }
}
void xor_collision_witness() {
 // Equal bit flips in adjacent frequency bytes cancel under XOR. This is
 // a weakness witness, not an assertion that this caused the physical trip.
 for (unsigned seq = 0; seq < 256; ++seq) {
  running((uint8_t)(seq - 1));
  Frame bad = frame(UNO_FLAG_ENABLE, UNO_MODE_SCALAR, 10000, (uint8_t)seq);
  const auto original_checksum = bad.back();
  bad[6] ^= 0x40;
  bad[7] ^= 0x40;
  check(uno_u32le(&bad[6]) == 26448U && bad.back() == original_checksum,
        "paired-bit witness changes 10 Hz command to 26.448 Hz without checksum change");
  check(uno_crc_xor(bad.data()) == bad.back(), "XOR cannot detect paired-bit witness");
  const unsigned previous_ramps = ramps;
  feed(bad);
  check(!uno_link.fault_latched && uno_link.command_enabled && ramps > previous_ramps,
        "production accepts checksum-preserving frequency corruption");
  ++xor_collisions;
 }
}
int main() {
 single_bit_errors(); lost_sync_and_byte_edits(); xor_collision_witness();
 std::printf("{\"pass\":true,\"cases\":%u,\"assertions\":%u,"
             "\"xor_collision_witnesses\":%u,\"hardware_commands\":0}\n",
             cases, tests, xor_collisions);
}
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    report = {
        "pass": False,
        "scope": "unchanged production parser; host HAL/MCSDK mocks only",
        "hardware_commands": 0,
        "firmware_modified": False,
        "physical_fault_root_cause_identified": False,
        "checksum_qualification_pass": False,
        "warning": "protocol v2 uses XOR, not polynomial CRC; paired errors can pass",
    }
    try:
        program, sources = generate(root)
        helpers = CASES[:CASES.index("void scenarios()")]
        program = replace_once(program, CASES, helpers + TESTS)
        report["sources"] = {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sources
        }
        compiler = shutil.which("g++")
        if not compiler:
            raise RuntimeError("g++ required")
        (out / "host_test.cpp").write_text(program, encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / "test.exe"
            for label, candidate in (
                ("production", program),
                ("crc_guard_removed", replace_once(
                    program,
                    "uno_link.frame[UNO_FRAME_LEN - 1U] != uno_crc_xor(uno_link.frame)",
                    "false")),
            ):
                unit = Path(directory) / "test.cpp"
                unit.write_text(candidate, encoding="utf-8")
                build = subprocess.run(
                    [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                     str(unit), "-o", str(exe)],
                    capture_output=True, text=True, timeout=60,
                )
                (out / f"{label}_compile.log").write_text(
                    build.stdout + build.stderr, encoding="utf-8")
                if build.returncode:
                    raise RuntimeError(f"{label} compile failed")
                run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
                (out / f"{label}_run.log").write_text(
                    run.stdout + run.stderr, encoding="utf-8")
                if label == "production":
                    if run.returncode:
                        raise RuntimeError(run.stderr.strip())
                    report.update(json.loads(run.stdout))
                else:
                    report["mutation_detected"] = run.returncode != 0 and "FAIL " in run.stderr
            report["pass"] = report["pass"] and report["mutation_detected"]
    except Exception as exc:
        report["pass"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
