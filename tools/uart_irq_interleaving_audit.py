"""Host-only audit of UART faults arriving while production consumes a frame."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from production_mcsdk_link_dynamic_selftest import CASES, generate


SCHEDULE = r'''
unsigned inject_position, pop_position, inject_flag;
bool injection_armed;
void inject_uart_fault();
void resume_uart_irq(int) {
 if (injection_armed && inject_position==0) inject_uart_fault();
}
void after_rx_pop() {
 ++pop_position;
 if (injection_armed && pop_position==inject_position) inject_uart_fault();
}
'''

AUDIT = r'''
void inject_uart_fault() {
 injection_armed=false;
 uart_registers.ISR=inject_flag;
 USART1_IRQHandler();
}
int main() {
 unsigned cases=0, starts_after_pending_error=0, next_poll_stops=0;
 for (unsigned flag : {UART_FLAG_NE,UART_FLAG_FE,UART_FLAG_ORE,UART_FLAG_PE}) {
  for (unsigned prefix=0; prefix<UNO_FRAME_LEN; ++prefix) {
   for (unsigned position=0; position<=UNO_FRAME_LEN-prefix; ++position) {
    injection_armed=false; reset(true);
    Frame pending=frame(UNO_FLAG_ENABLE,UNO_MODE_SCALAR,10000,81);
    for (unsigned i=0; i<prefix; ++i) uno_consume_byte(pending[i]);
    for (unsigned i=prefix; i<UNO_FRAME_LEN; ++i)
     check(uno_rx_push(pending[i]), "queue valid pending frame");
    inject_position=position; pop_position=0; inject_flag=flag; injection_armed=true;
    uno_link_poll();
    check(!injection_armed, "real ISR publishes fault during poll");
#if CANDIDATE
    check(starts==0 && uno_link.fault_latched, "pending UART error prevents queued start");
#else
    check(uno_rx_errors!=0, "original leaves mid-poll fault pending");
#endif
    ++cases;
    if (starts!=0) ++starts_after_pending_error;
    uno_link_poll();
    const uint8_t expected=flag==UART_FLAG_NE ? 4U : flag==UART_FLAG_FE ? 2U :
                           flag==UART_FLAG_ORE ? 8U : 1U;
    check(uno_link.fault_latched && !uno_link.command_enabled && motor_state==IDLE,
          "following poll stops and latches");
    check(uno_link.last_bad_reason==UNO_DIAG_UART && uno_link.last_uart_errors==expected,
          "following poll retains exact UART cause");
    ++next_poll_stops;
    feed(frame(UNO_FLAG_ENABLE,UNO_MODE_SCALAR,10000,82));
    check(starts<=1 && !uno_link.command_enabled, "no automatic restart after latch");
   }
  }
 }
 std::printf("{\"cases\":%u,\"starts_after_pending_error\":%u,"
             "\"next_poll_stops\":%u,\"checks\":%u}\n",
             cases,starts_after_pending_error,next_poll_stops,tests);
 return 0;
}
'''


def candidate_source(source: str) -> str:
    """Keep this unflashed candidate separate from the installed firmware source."""
    poll = source.index("static void uno_link_poll(void) {")
    begin = source.index("  /* Mask only USART1;", poll)
    end = source.index("  uint8_t byte;", begin)
    service = source[begin:end]
    if service.count("    return;\n") != 1:
        raise RuntimeError("RX fault service anchor changed")
    helper = ("static bool uno_abort_pending_rx_fault(void) {\n"
              + service.replace("    return;\n", "    return true;\n")
              + "  return false;\n}\n\n")
    source = (source[:poll] + helper + source[poll:begin]
              + "  if (uno_abort_pending_rx_fault()) return;\n" + source[end:])
    anchor = "static void uno_handle_valid_frame(const uint8_t *frame) {\n"
    if source.count(anchor) != 1:
        raise RuntimeError("Frame dispatch anchor changed")
    source = source.replace(anchor, "static bool uno_abort_pending_rx_fault(void);\n\n"
                            + anchor + "  if (uno_abort_pending_rx_fault()) return;\n", 1)
    anchor = "  while (uno_rx_pop(&byte)) uno_consume_byte(byte);"
    if source.count(anchor) != 1:
        raise RuntimeError("Queue drain anchor changed")
    source = source.replace(anchor,
        "  while (uno_rx_pop(&byte)) {\n"
        "    if (uno_abort_pending_rx_fault()) return;\n"
        "    uno_consume_byte(byte);\n  }", 1)
    return source


def run_host(program: str, label: str, out: Path, compiler: str) -> dict:
    unit = out / f"{label}.cpp"
    unit.write_text(program, encoding="utf-8")
    with tempfile.TemporaryDirectory() as directory:
        exe = Path(directory) / "audit.exe"
        build = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                                str(unit), "-o", str(exe)], capture_output=True, text=True, timeout=60)
        (out / f"{label}_compile.log").write_text(build.stdout + build.stderr, encoding="utf-8")
        if build.returncode:
            raise RuntimeError(f"Host compilation failed: {label}")
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
        (out / f"{label}_run.log").write_text(run.stdout + run.stderr, encoding="utf-8")
        if run.returncode:
            raise RuntimeError(f"Host assertions failed: {label}: {run.stderr}")
        return json.loads(run.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", required=True, type=Path)
    args = parser.parse_args()
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    program, sources = generate(root)
    regression = program
    helpers = CASES[:CASES.index("void scenarios()")]
    program = program.replace(CASES, helpers + AUDIT, 1)
    anchor = "void HAL_NVIC_EnableIRQ(int) {}"
    if program.count(anchor) != 1:
        raise RuntimeError("IRQ mock anchor changed")
    program = program.replace(anchor, SCHEDULE + "void HAL_NVIC_EnableIRQ(int irq) { resume_uart_irq(irq); }")
    anchor = "  uno_rx_tail = (uno_rx_tail + 1U) & UNO_RX_MASK;\n  return true;"
    if program.count(anchor) != 1:
        raise RuntimeError("RX scheduling anchor changed")
    program = program.replace(anchor, anchor.replace("  return true;", "  after_rx_pop();\n  return true;"))
    compiler = shutil.which("g++")
    if not compiler:
        raise RuntimeError("g++ required")
    original = run_host("#define CANDIDATE 0\n" + program, "original", out, compiler)
    candidate = run_host("#define CANDIDATE 1\n" + candidate_source(program), "candidate", out, compiler)
    regression_result = run_host(candidate_source(regression), "candidate_regression", out, compiler)
    original_source = sources[0].read_text(encoding="utf-8-sig")
    corrected_source = candidate_source(original_source)
    patch = "".join(difflib.unified_diff(original_source.splitlines(True), corrected_source.splitlines(True),
                 fromfile="a/" + sources[0].relative_to(root).as_posix(),
                 tofile="b/" + sources[0].relative_to(root).as_posix()))
    (out / "candidate_unflashed.patch").write_text(patch, encoding="utf-8")
    result = dict(original)
    result.update(
        schema="mic_ai.uart_irq_interleaving.v1",
        audit_completed=True,
        no_start_with_already_pending_uart_fault=result["starts_after_pending_error"] == 0,
        hardware_validated=False,
        physical_NE_source_identified=False,
        firmware_modified=False,
        firmware_flashed=False,
        candidate=candidate,
        candidate_regression=regression_result,
        candidate_scheduled_cases_pass=candidate["starts_after_pending_error"] == 0,
        candidate_release_ready=False,
        remaining_scope="No exhaustive instruction-level interleavings, real ISR latency, physical noise or PWM timing validation. Candidate keeps installed build ID and is NOT a deployable release. Extra USART-only critical sections need target timing review.",
        scope="Production parser/poll/IRQ copied into host mocks. Scheduling hooks only at IRQ unmask and RX pop. MC_StartMotor1 calls are NOT evidence of physical PWM pulses. No hardware access.",
        sources={str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
    )
    (out / "report.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
