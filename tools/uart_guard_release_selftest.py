"""Inject UART IRQs at host API/queue boundaries; never access hardware."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from production_mcsdk_link_dynamic_selftest import CASES, generate
from uart_irq_interleaving_audit import AUDIT, SCHEDULE, run_host


API_DECL = r'''
void schedule_event();
void dispatch_rx_irq();
bool rx_irq_enabled=true, fault_published=false;
unsigned event_index, inject_at, fault_flag, starts_after_fault, ramps_after_fault;
bool api_injection_armed;
'''

API_TESTS = r'''
void dispatch_rx_irq() {
 if (rx_irq_enabled && uart_registers.ISR!=0) {
  USART1_IRQHandler(); fault_published=true;
 }
}
void schedule_event() {
 ++event_index;
 if (api_injection_armed && event_index==inject_at) {
  api_injection_armed=false; uart_registers.ISR=fault_flag;
  dispatch_rx_irq();
 }
}
void prepare_frame(unsigned kind) {
 api_injection_armed=false; rx_irq_enabled=true; fault_published=false;
 starts_after_fault=ramps_after_fault=event_index=0; reset(true);
 Frame f=frame(UNO_FLAG_ENABLE,UNO_MODE_SCALAR,10000,81);
 if (kind==1) {
  f=frame(UNO_FLAG_CLEAR_FAULT,UNO_MODE_OFF,0,81);
  uno_latch_fault(UNO_FAULT_ESTOP);
 } else if (kind==2) {
  motor_state=RUN; uno_link.command_enabled=true;
  f=frame(0,UNO_MODE_OFF,0,81);
 }
 for (auto byte:f) check(uno_rx_push(byte), "queue one control frame");
 event_index=0;
}
int main() {
 unsigned cases=0, post_fault_starts=0, post_fault_ramps=0, stop_verified=0;
 for (unsigned kind=0;kind<3;++kind) {
  prepare_frame(kind); uno_link_poll(); const unsigned event_count=event_index;
  for (unsigned flag : {UART_FLAG_NE,UART_FLAG_FE,UART_FLAG_ORE,UART_FLAG_PE}) {
   for (unsigned point=1;point<=event_count;++point) {
    prepare_frame(kind); inject_at=point; fault_flag=flag; api_injection_armed=true;
    uno_link_poll(); dispatch_rx_irq();
    check(!api_injection_armed && fault_published, "scheduled IRQ executes");
    ++cases; post_fault_starts+=starts_after_fault; post_fault_ramps+=ramps_after_fault;
    uno_link_poll();
    check(uno_link.fault_latched && !uno_link.command_enabled && motor_state==IDLE,
          "UART error stops and latches by subsequent poll");
    check(uno_link.last_bad_reason==UNO_DIAG_UART, "UART cause remains visible");
    ++stop_verified;
#if GUARDED
    check(starts_after_fault==0, "no API START entered after a published UART error");
    check(ramps_after_fault==0, "no ramp API entered after a published UART error");
#endif
   }
  }
 }
 std::printf("{\"cases\":%u,\"starts_after_published_fault\":%u,"
             "\"ramps_after_published_fault\":%u,\"stops_verified\":%u,\"checks\":%u}\n",
             cases,post_fault_starts,post_fault_ramps,stop_verified,tests);
}
'''


def replace_once(text: str, before: str, after: str) -> str:
    if text.count(before) != 1:
        raise RuntimeError("Nonunique mock anchor: " + before)
    return text.replace(before, after, 1)


def api_program(program: str) -> str:
    helpers = CASES[:CASES.index("void scenarios()")]
    program = replace_once(program, CASES, helpers + API_TESTS)
    program = replace_once(program, "void HAL_NVIC_DisableIRQ(int) {}",
                           API_DECL + "void HAL_NVIC_DisableIRQ(int) { rx_irq_enabled=false; schedule_event(); }")
    program = replace_once(program, "void HAL_NVIC_EnableIRQ(int) {}",
                           "void HAL_NVIC_EnableIRQ(int) { rx_irq_enabled=true; dispatch_rx_irq(); schedule_event(); }")
    for anchor in (
        "uint32_t HAL_GetTick() {", "MCI_State_t MC_GetSTMStateMotor1() {",
        "int16_t MC_GetMecSpeedReferenceMotor1() {", "uint16_t MC_GetCurrentFaultsMotor1() {",
        "uint16_t MC_GetOccurredFaultsMotor1() {", "bool MC_StopMotor1() {",
        "bool MC_AcknowledgeFaultMotor1() {",
        "template<class T> uint16_t VBS_GetAvBusVoltage_V(T *) {",
        "template<class T> int16_t NTC_GetAvTemp_C(T *) {",
        "template<class T> int HAL_UART_Transmit(T *, uint8_t *data, unsigned size, unsigned) {",
    ):
        program = replace_once(program, anchor, anchor + " schedule_event();")
    anchor = "void MC_ProgramSpeedRampMotor1(int16_t target, uint16_t duration) {"
    program = replace_once(program, anchor,
                           anchor + " if (fault_published) ++ramps_after_fault; schedule_event();")
    anchor = "bool MC_StartMotor1() {"
    program = replace_once(program, anchor,
                           anchor + " if (fault_published) ++starts_after_fault; schedule_event();")
    # Model preemption after the guard predicate and immediately before the
    # actual command API, not only inside other mocked HAL/MCSDK functions.
    anchor = "    if (uno_rx_errors == 0U && uno_rx_overflow == 0U) return false;"
    if anchor in program:
        program = replace_once(program, anchor,
                               "    if (uno_rx_errors == 0U && uno_rx_overflow == 0U) { schedule_event(); return false; }")
    for anchor in ("    MC_ProgramSpeedRampMotor1(target_speed_unit, ramp_ms);",
                   "  if (start_state == IDLE && !MC_StartMotor1()) {",
                   "    if (start_state == IDLE && !MC_StartMotor1()) start_failed = true;"):
        if anchor in program:
            program = replace_once(program, anchor, "  schedule_event();\n" + anchor)
    anchor = "  uno_rx_tail = (uno_rx_tail + 1U) & UNO_RX_MASK;\n  return true;"
    return replace_once(program, anchor, anchor.replace("  return true;", "  schedule_event();\n  return true;"))


def queue_program(program: str) -> str:
    helpers = CASES[:CASES.index("void scenarios()")]
    program = replace_once(program, CASES, helpers + AUDIT)
    program = replace_once(program, "void HAL_NVIC_EnableIRQ(int) {}",
                           SCHEDULE + "void HAL_NVIC_EnableIRQ(int irq) { resume_uart_irq(irq); }")
    anchor = "  uno_rx_tail = (uno_rx_tail + 1U) & UNO_RX_MASK;\n  return true;"
    return replace_once(program, anchor, anchor.replace("  return true;", "  after_rx_pop();\n  return true;"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-source", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--audit-only", action="store_true",
                        help="Record violations instead of stopping at the first assertion")
    args = parser.parse_args()
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    production, sources = generate(root)
    original = args.baseline_source.read_text(encoding="utf-8-sig")
    current = sources[0].read_text(encoding="utf-8-sig")

    def section(text: str) -> str:
        begin = text.index("enum {", text.index("/* USER CODE BEGIN 0 */"))
        end = text.index("static void MX_USART1_UART_Init(void) {", begin)
        return text[begin:end]

    baseline = replace_once(production, section(current), section(original))
    compiler = shutil.which("g++")
    if not compiler:
        raise RuntimeError("g++ required")
    results = {
        "baseline_queue": run_host("#define CANDIDATE 0\n" + queue_program(baseline), "baseline_queue", out, compiler),
        "production_queue": run_host("#define CANDIDATE 1\n" + queue_program(production), "production_queue", out, compiler),
        "baseline_api": run_host("#define GUARDED 0\n" + api_program(baseline), "baseline_api", out, compiler),
        "production_api": run_host(f"#define GUARDED {0 if args.audit_only else 1}\n" + api_program(production), "production_api", out, compiler),
    }
    anchor = "  HAL_NVIC_DisableIRQ(USART1_IRQn);\n  const bool rx_fault_pending"
    if anchor in production:
        unprotected = replace_once(production, anchor, "  const bool rx_fault_pending")
        results["commit_mask_mutation"] = run_host("#define GUARDED 0\n" + api_program(unprotected),
                                                  "commit_mask_mutation", out, compiler)
    report = {
        "schema": "mic_ai.uart_guard_release_test.v1",
        "pass": results["production_queue"]["starts_after_pending_error"] == 0
                and results["production_api"]["starts_after_published_fault"] == 0
                and results["production_api"]["ramps_after_published_fault"] == 0
                and ("commit_mask_mutation" not in results or
                     results["commit_mask_mutation"]["starts_after_published_fault"] > 0)
                and results["baseline_queue"]["starts_after_pending_error"] > 0,
        "results": results,
        "source_sha256": hashlib.sha256(sources[0].read_bytes()).hexdigest(),
        "baseline_sha256": hashlib.sha256(args.baseline_source.read_bytes()).hexdigest(),
        "hardware_access": False,
        "scope": "Host IRQ scheduling at queue, guard-return and command-commit boundaries, ENABLE/CLEAR/STOP. UART-only commit-mask negative control. Not instruction-level exhaustive or physical PWM timing validation.",
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
