"""Exercise the production ISR FIFO drain, overflow, fault bursts and CLEAR offline."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from production_mcsdk_link_dynamic_selftest import CASES, generate
from uart_guard_release_selftest import replace_once


FIFO = r'''
std::deque<uint8_t> rx_fifo;
unsigned fifo_reads;
bool fifo_rx_ready(unsigned flag) {
 if (flag!=UART_FLAG_RXNE || rx_fifo.empty()) return false;
 uart_registers.RDR=rx_fifo.front(); rx_fifo.pop_front(); ++fifo_reads;
 return true;
}
#define __HAL_UART_GET_FLAG(h, flag) (fifo_rx_ready(flag))
'''

TESTS = r'''
unsigned cases;
unsigned register_errors(unsigned mask) {
 return ((mask&1)?UART_FLAG_PE:0)|((mask&2)?UART_FLAG_FE:0)|
        ((mask&4)?UART_FLAG_NE:0)|((mask&8)?UART_FLAG_ORE:0);
}
void setup(bool running=false) {
 reset(true); rx_fifo.clear(); fifo_reads=0;
 if (running) feed(frame(UNO_FLAG_ENABLE,UNO_MODE_SCALAR,10000,80));
}
void queue_fifo(const Frame &f) { for (auto b:f) rx_fifo.push_back(b); }
void inject(unsigned mask) {
 uart_registers.ISR=register_errors(mask); USART1_IRQHandler();
 check(rx_fifo.empty(), "ISR drains all received FIFO bytes");
 check(uart_registers.ISR==0, "ISR clears all selected error flags");
}
void overflow_and_partial_frames() {
 for (unsigned prefix=0;prefix<UNO_FRAME_LEN;++prefix) {
  for (unsigned count=0;count<=160;++count) {
   setup(); Frame pending=frame(UNO_FLAG_ENABLE,UNO_MODE_SCALAR,10000,81);
   for (unsigned i=0;i<prefix;++i) rx_fifo.push_back(pending[i]);
   inject(0); uno_link_poll();
   check(starts==0 && !uno_link.fault_latched, "partial frame cannot start");
   for (unsigned i=0;i<count;++i) {
    const unsigned pos=prefix+i;
    Frame f=frame(UNO_FLAG_ENABLE,UNO_MODE_SCALAR,10000,(uint8_t)(81+pos/UNO_FRAME_LEN));
    rx_fifo.push_back(f[pos%UNO_FRAME_LEN]);
   }
   inject(0);
   check(fifo_reads==prefix+count, "FIFO reads equal delivered bytes");
   check((uno_rx_overflow!=0)==(count>=UNO_RX_SIZE), "ISR publishes overflow at exact ring capacity");
   uno_link_poll();
   if (count>=UNO_RX_SIZE) {
    check(starts==0 && uno_link.fault_latched && !uno_link.command_enabled,
          "overflow cannot consume queued ENABLE");
    check(uno_link.first_reason==UNO_DIAG_RX_BUFFER && uno_link.last_bad_reason==UNO_DIAG_RX_BUFFER,
          "overflow remains distinct from UART hardware errors");
    check(uno_rx_head==uno_rx_tail && uno_link.parser_state==0,
          "overflow clears ring and partial parser");
   } else {
    check(!uno_link.fault_latched && starts==(prefix+count>=UNO_FRAME_LEN ? 1U : 0U),
          "nonoverflow complete frames start once, partial frames never start");
   }
   ++cases;
  }
 }
}
void error_data_and_clear() {
 for (unsigned mask=1;mask<16;++mask) {
  for (unsigned count=0;count<=160;++count) {
   setup(true);
   Frame pending=frame(UNO_FLAG_ENABLE,UNO_MODE_SCALAR,10000,81);
   for (unsigned i=0;i<count;++i) rx_fifo.push_back(pending[i%UNO_FRAME_LEN]);
   inject(mask);
   check(uno_rx_head==uno_rx_tail && uno_rx_overflow==0,
         "error-marked FIFO bytes are drained but never queued");
   uno_link_poll();
   check(starts==1 && motor_state==IDLE && uno_link.fault_latched && !uno_link.command_enabled,
         "all error combinations stop existing RUN without restart");
   check(uno_link.first_reason==UNO_DIAG_UART && uno_link.first_uart_errors==mask,
         "exact combined UART cause survives FIFO draining");
   queue_fifo(frame(UNO_FLAG_ENABLE,UNO_MODE_SCALAR,10000,82)); inject(0); uno_link_poll();
   check(starts==1 && uno_link.fault_latched, "ENABLE after error cannot auto-clear");
   queue_fifo(frame(UNO_FLAG_CLEAR_FAULT,UNO_MODE_OFF,0,83)); inject(mask); uno_link_poll();
   check(uno_link.fault_latched && uno_link.first_uart_errors==mask,
         "CLEAR received with hardware error cannot erase diagnostics");
   queue_fifo(frame(UNO_FLAG_CLEAR_FAULT,UNO_MODE_OFF,0,84)); inject(0); uno_link_poll();
   check(!uno_link.fault_latched && !uno_link.command_enabled && starts==1,
         "subsequent clean CLEAR never starts motor");
   ++cases;
  }
 }
}
void sequential_faults_and_timeouts() {
 for (unsigned first=1;first<16;++first) for (unsigned second=1;second<16;++second) {
  setup(true); inject(first); uno_link_poll(); inject(second); uno_link_poll();
  check(uno_link.first_uart_errors==first && uno_link.last_uart_errors==second,
        "first and latest UART errors remain separately identifiable");
  check(uno_link.bad_count==2 && !uno_link.command_enabled && motor_state==IDLE,
        "consecutive errors counted and latched without restart");
  uno_link.bad_count=UINT16_MAX; inject(second); uno_link_poll();
  check(uno_link.bad_count==UINT16_MAX, "bad counter never wraps under error bursts");
  ++cases;
 }
 for (unsigned delta=0;delta<=600;++delta) for (unsigned wrap=0;wrap<2;++wrap) {
  setup(); now_ms=wrap ? UINT32_MAX-150U : 3500U;
  queue_fifo(frame(UNO_FLAG_ENABLE,UNO_MODE_SCALAR,20000,81)); inject(0); uno_link_poll();
  const unsigned programmed=ramps;
  now_ms+=delta; uno_link_poll();
  check(uno_link.fault_latched==(delta>UNO_LINK_TIMEOUT_MS), "link timeout exact boundary and tick wrap");
  check(ramps==programmed, "loss of UART never reprograms ramp");
  if (delta>UNO_LINK_TIMEOUT_MS) {
   check(!uno_link.command_enabled && motor_state==IDLE && uno_link.first_reason==UNO_DIAG_TIMEOUT,
         "link loss stops existing ramp and preserves timeout reason");
   queue_fifo(frame(UNO_FLAG_ENABLE,UNO_MODE_SCALAR,20000,82)); inject(0); uno_link_poll();
   check(starts==1 && uno_link.fault_latched, "reconnected UART cannot restart after timeout");
  }
  ++cases;
 }
}
int main() {
 overflow_and_partial_frames(); error_data_and_clear(); sequential_faults_and_timeouts();
 std::printf("{\"pass\":true,\"cases\":%u,\"assertions\":%u,\"hardware_commands\":0}\n",cases,tests);
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    program, sources = generate(root)
    program = replace_once(program, "#include <array>", "#include <array>\n#include <deque>")
    program = replace_once(program, "#define __HAL_UART_GET_FLAG(h, flag) (false)", FIFO)
    helpers = CASES[:CASES.index("void scenarios()")]
    program = replace_once(program, CASES, helpers + TESTS)
    compiler = shutil.which("g++")
    if not compiler:
        raise RuntimeError("g++ required")
    mutations = {
        "overflow_not_published": ("uno_rx_overflow = 1U;", "uno_rx_overflow = 0U;"),
        "error_bytes_queued": ("uno_rx_errors == 0U && uno_rx_overflow == 0U && !uno_rx_push(byte)",
                               "!uno_rx_push(byte)"),
        "first_fault_overwritten": ("if (uno_link.first_reason != UNO_DIAG_NONE) return;", "/* overwritten */"),
        "watchdog_one_ms_early": ("> UNO_LINK_TIMEOUT_MS) {", ">= UNO_LINK_TIMEOUT_MS) {"),
    }
    report = {"pass": False, "sources": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                                          for p in sources}, "mutations": {},
              "scope": "Production ISR with simulated FIFO; no electrical timing or physical PWM proof"}
    with tempfile.TemporaryDirectory() as temp:
        for label in ("production", *mutations):
            candidate = program
            if label != "production":
                before, after = mutations[label]
                candidate = replace_once(program, before, after)
            unit = out / (label + ".cpp")
            unit.write_text(candidate, encoding="utf-8")
            exe = Path(temp) / (label + ".exe")
            build = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                                    str(unit), "-o", str(exe)], capture_output=True, timeout=60)
            (out / (label + "_compile.log")).write_bytes(build.stdout + build.stderr)
            if build.returncode:
                raise RuntimeError("Compilation failed: " + label)
            result = subprocess.run([str(exe)], capture_output=True, timeout=30)
            (out / (label + "_run.log")).write_bytes(result.stdout + result.stderr)
            if label == "production":
                if result.returncode:
                    report["error"] = result.stderr.decode("utf-8", errors="replace")
                    break
                report.update(json.loads(result.stdout))
            else:
                report["mutations"][label] = {"detected": result.returncode != 0 and b"FAIL " in result.stderr,
                                              "failure": result.stderr.decode("utf-8", errors="replace").strip()}
    report["pass"] = (report["pass"] and len(report["mutations"]) == len(mutations)
                      and all(m["detected"] for m in report["mutations"].values()))
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
