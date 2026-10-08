"""Reproduce asynchronous MCSDK ACK and test the current diagnostic fix."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from production_mcsdk_link_dynamic_selftest import CASES, generate


TESTS = r'''
void check(bool ok, const char *name) {
 ++tests;
 if (!ok) { std::fprintf(stderr, "FAIL %s\n", name); std::exit(1); }
}
using Frame = std::array<uint8_t, UNO_FRAME_LEN>;
Frame frame(uint8_t flags, uint8_t mode, uint8_t seq) {
 Frame f{}; f[0]=UNO_CMD_HDR0; f[1]=UNO_CMD_HDR1; f[2]=UNO_PROTOCOL_VERSION;
 f[3]=flags; f[4]=mode; f[5]=seq; f.back()=uno_crc_xor(f.data()); return f;
}
void feed(const Frame &f) { for (auto b : f) uno_consume_byte(b); }
void reset() {
 now_ms=3500; bus_v=310; mc_fault=mc_occurred=0; motor_state=IDLE;
 starts=stops=ramps=0; start_succeeds=tx_succeeds=true; test_timer={};
 uart_registers={}; reply={}; uno_link_init();
}
int main() {
 reset(); motor_state=FAULT_OVER; mc_occurred=4;
 feed(frame(UNO_FLAG_CLEAR_FAULT, UNO_MODE_OFF, 32));
 check(motor_state==FAULT_OVER && mc_occurred==0, "ACK is asynchronous, masks clear");
 check(reply[3]&UNO_STATUS_FAULT, "state guard still blocks during ACK transition");
#if CANDIDATE
 check(uno_link.first_reason==UNO_DIAG_NONE, "no empty post-ACK fault snapshot");
#else
 check(uno_link.first_reason==UNO_DIAG_MCSDK && uno_link.first_current_faults==0
       && uno_link.first_occurred_faults==0, "reproduce empty stale snapshot");
#endif
 motor_state=IDLE; uno_send_reply();
 check(!(reply[3]&UNO_STATUS_FAULT), "scheduler completes ACK, fault inactive");
 motor_state=RUN; uno_link.command_enabled=true; uno_rx_errors=4;
 uno_link_poll(); uno_send_reply();
 check(uno_link.fault_latched && !uno_link.command_enabled, "NE still stops and latches");
 check(uno_link.last_bad_reason==UNO_DIAG_UART && uno_link.last_uart_errors==4,
       "last cause records NE in both versions");
#if CANDIDATE
 check(uno_link.first_reason==UNO_DIAG_UART && uno_link.first_uart_errors==4,
       "candidate preserves actual first cause after ACK");
#else
 check(uno_link.first_reason==UNO_DIAG_MCSDK && uno_link.first_uart_errors==0,
       "original masks actual first cause after ACK");
#endif
 for (uint16_t mask : {1,2,4,8,16,32,64,128,256,512,1024,2048,4096,8192,16384,32768}) {
  reset(); motor_state=FAULT_OVER; mc_fault=mask; uno_send_reply();
  check(uno_link.first_reason==UNO_DIAG_MCSDK && uno_link.first_current_faults==mask,
        "real current faults remain captured");
  reset(); motor_state=FAULT_OVER; mc_occurred=mask; uno_send_reply();
  check(uno_link.first_reason==UNO_DIAG_MCSDK && uno_link.first_occurred_faults==mask,
        "real occurred faults remain captured");
 }
 reset(); motor_state=FAULT_OVER; feed(frame(UNO_FLAG_ENABLE, UNO_MODE_SCALAR, 1));
 check(uno_link.fault_latched && starts==0, "ENABLE cannot bypass FAULT_OVER");
 reset(); motor_state=FAULT_NOW; uno_send_reply();
 check(uno_link.first_reason==UNO_DIAG_MCSDK, "FAULT_NOW diagnostics retained");
 std::printf("{\"pass\":true,\"checks\":%u}\n", tests); return 0;
}
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", required=True, type=Path)
    args = parser.parse_args()
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    program, sources = generate(root)
    program = program.replace(CASES, TESTS)
    old_stop = "bool MC_StopMotor1() { ++stops; if (!mc_fault) motor_state=IDLE; return true; }"
    old_ack = "bool MC_AcknowledgeFaultMotor1() { if (!mc_fault) motor_state=IDLE; return !mc_fault; }"
    assert old_stop in program and old_ack in program
    program = program.replace(old_stop, "bool MC_StopMotor1() { ++stops; return true; }")
    program = program.replace(old_ack, "bool MC_AcknowledgeFaultMotor1() { "
                              "if (motor_state!=FAULT_OVER || mc_fault) return false; "
                              "mc_occurred=0; return true; }")
    old_capture = "if (mcsdk_fault) uno_capture_diagnostics(UNO_DIAG_MCSDK, 0U, 0U);"
    new_capture = ("if (mcsdk_fault && (motor_state != FAULT_OVER ||\n"
                   "      mcsdk_faults != MC_NO_FAULTS || MC_GetOccurredFaultsMotor1() != MC_NO_FAULTS)) {\n"
                   "    uno_capture_diagnostics(UNO_DIAG_MCSDK, 0U, 0U);\n  }")
    assert program.count(new_capture) == 1
    compiler = shutil.which("g++")
    if not compiler:
        raise RuntimeError("g++ is required")
    report = {"schema": "mic_ai.async_clear_diagnostics.v1", "pass": False,
              "hardware_validated": False, "production_source_fix_tested": True,
              "candidate_deployed": False,
              "candidate_replacement": {"old": old_capture, "new": new_capture},
              "sources": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sources}, "runs": {}}
    with tempfile.TemporaryDirectory() as directory:
        for label, candidate in (("original_reproduces_bug", False),
                                 ("diagnostic_candidate", True)):
            text = program if candidate else program.replace(new_capture, old_capture)
            text = f"#define CANDIDATE {int(candidate)}\n" + text
            unit = out / f"{label}.cpp"
            unit.write_text(text, encoding="utf-8")
            exe = Path(directory) / f"{label}.exe"
            build = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                                    str(unit), "-o", str(exe)], capture_output=True, text=True, timeout=60)
            (out / f"{label}_compile.log").write_text(build.stdout + build.stderr, encoding="utf-8")
            if build.returncode:
                raise RuntimeError(f"Compilation failed: {label}")
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
            (out / f"{label}_run.log").write_text(run.stdout + run.stderr, encoding="utf-8")
            if run.returncode:
                raise RuntimeError(f"Test failed: {label}: {run.stderr}")
            report["runs"][label] = json.loads(run.stdout)
    report["pass"] = all(r["pass"] for r in report["runs"].values())
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
