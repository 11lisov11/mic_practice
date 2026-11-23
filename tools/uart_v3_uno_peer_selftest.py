"""Exercise the generated Uno v3 reply parser/decoder, with no hardware."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from prepare_uart_v3_candidate import UNO_BUILD, NUCLEO_BUILD, prepare
from uno_reply_restart_selftest import function
from uart_guard_release_selftest import replace_once


PREAMBLE = r'''
#include <array>
#include <cstdint>
#include <cstdio>
#include <deque>
#include <cstdlib>
#include "uart_v3_transport.h"
#include "nucleo_fault_diagnostics.h"
#include "link_timing.h"
constexpr unsigned BP_FRAME_LEN=UV3_FRAME, BP_REPLY_TIMEOUT_MS=100;
constexpr uint8_t BP_VER=UV3_VERSION;
struct SerialStub {
  std::deque<uint8_t> bytes;
  int available() { return int(bytes.size()); }
  int read() { int v=bytes.front(); bytes.pop_front(); return v; }
} NUCLEO_SERIAL;
struct Superseded { bool consume(uint8_t,uint32_t,uint32_t) { return false; } } g_nucleo_superseded;
uint8_t g_bp_ping_prev=0, g_nucleo_waiting_seq=7;
uint32_t g_bp_ping_pairs=0,g_bp_ping_ms=0,g_nucleo_last_rx_ms=0,g_link_led_ms=0;
uint16_t g_nucleo_rx_superseded=0,g_nucleo_rx_good=0,g_nucleo_rx_bad=0;
uint16_t g_nucleo_rx_bad_integrity=0,g_nucleo_rx_bad_sequence=0;
bool g_nucleo_waiting_rsp=true;
uint32_t millis() { return 100; }
uint32_t micros() { return 100000; }
unsigned tests=0,cases=0;
void check(bool ok,const char *name) {
  ++tests;
  if(!ok) { std::fprintf(stderr,"FAIL %s\n",name); std::exit(1); }
}
'''

TESTS = r'''
using Reply=std::array<uint8_t,UV3_FRAME>;
void feed(const Reply &p,unsigned n=UV3_FRAME) {
  for(unsigned i=0;i<n;++i) NUCLEO_SERIAL.bytes.push_back(p[i]);
  nucleo_uart_poll();
}
void flush_partial() {
  for(unsigned i=0;i<UV3_FRAME*2;++i) NUCLEO_SERIAL.bytes.push_back(0);
  nucleo_uart_poll();
}
Reply reply() {
  Reply a{}; a[0]=0x55; a[1]=0xaa; a[2]=BP_VER; a[4]=7;
  a[11]=0x90 | 12; a[12]=0x44; a[13]=6; a[15]=4;
  a[27]=4; a[28]=4; a[30]=145;
  a[31]=2; a[33]=3; a[37]=4;
  uv3_seal(a.data()); return a;
}
int main() {
  LinkTiming timing;
  timing.tx(1,10,UV3_FRAME,false);
  check(timing.tx_short_writes==0,"full v3 frame is not misclassified as a short write");
  timing.tx(2,10,UV3_FRAME-1,false);
  check(timing.tx_short_writes==1,"genuine incomplete v3 write remains observable");
  auto clean=reply();
  feed(clean); check(g_nucleo_rx_good==1 && g_nucleo_rx_bad==0,"clean v3 reply accepted");
  auto d=decode_nucleo_fault_diagnostics(clean.data(),true,2026101006U);
  check(d.valid && d.uart_errors==4 && d.reason==12 && d.motor_state==6
        && d.current_faults==4 && d.occurred_faults==0x404 && d.sequence==145,
        "new build keeps first fault decoder working");
  for(unsigned pos=0;pos<UV3_FRAME;++pos) for(unsigned bit=0;bit<8;++bit) {
    flush_partial(); auto bad=clean; bad[pos]^=(uint8_t)(1U<<bit);
    auto before=g_nucleo_rx_good;
    feed(bad);
    check(g_nucleo_rx_good==before,"every single-bit reply corruption rejected"); ++cases;
  }
  flush_partial(); auto before=g_nucleo_rx_bad_sequence;
  auto old=clean; old[4]=6; uv3_seal(old.data()); feed(old);
  check(g_nucleo_rx_bad_sequence==before+1,"CRC-valid stale reply rejected"); ++cases;
  flush_partial(); before=g_nucleo_rx_bad_integrity;
  old=clean; old[2]=2; uv3_seal(old.data()); feed(old);
  check(g_nucleo_rx_bad_integrity==before+1,"v2 reply rejected despite valid CRC32C"); ++cases;
  for(unsigned prefix=1;prefix<UV3_FRAME;++prefix) {
    flush_partial(); auto good=g_nucleo_rx_good;
    feed(clean,prefix); check(g_nucleo_rx_good==good,"partial reply not committed");
    auto newer=clean; newer[15]=2; uv3_seal(newer.data()); feed(newer);
    // A lone 0x55 before a complete 0x55/0xaa header is legal resynchronization.
    check(g_nucleo_rx_good==good+(prefix==1 ? 1 : 0),
          "mixed reply rejected; lone header byte resynchronizes to complete reply");
    good=g_nucleo_rx_good;
    feed(newer);
    check(g_nucleo_rx_good==good+1,"parser recovers next complete frame"); ++cases;
  }
  std::printf("{\"pass\":true,\"cases\":%u,\"assertions\":%u,\"hardware_commands\":0}\n",cases,tests);
}
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {"pass": False, "hardware_commands": 0, "hardware_validated": False,
              "scope": "generated Uno reply parser and fault decoder; UART/RPC state mocked",
              "uno_build": UNO_BUILD, "nucleo_build": NUCLEO_BUILD}
    try:
        compiler = shutil.which("g++")
        if not compiler:
            raise RuntimeError("g++ required")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            snapshot = folder / "candidate"
            prepare(root, snapshot)
            sketch = snapshot / "UNOQ_MOTOR/UNOQ_MOTOR.ino"
            source = sketch.read_text(encoding="utf-8")
            a = source.index("static bool nucleo_check_reply(")
            b = source.index("  const bool clear_ack", a)
            integrity = source[a:b] + "  return true;\n}\n"
            code = PREAMBLE + integrity + function(source, "nucleo_uart_poll") + TESTS
            report["generated_uno_sha256"] = hashlib.sha256(sketch.read_bytes()).hexdigest()
            (out / "host_test.cpp").write_text(code, encoding="utf-8")
            unit, exe = folder / "test.cpp", folder / "test.exe"
            unit.write_text(code, encoding="utf-8")
            header_path = snapshot / "UNOQ_MOTOR/uart_v3_transport.h"
            header = header_path.read_text(encoding="utf-8")
            for label, body in (("candidate", header), ("CRC_removed", replace_once(
                    header, "return stored == uv3_crc32c(frame, UV3_PAYLOAD);",
                    "(void)stored; return true;"))):
                header_path.write_text(body, encoding="utf-8")
                build = subprocess.run([compiler,"-std=c++17","-O2","-Wall","-Wextra","-Werror",
                                        "-I",str(snapshot / "UNOQ_MOTOR"),str(unit),"-o",str(exe)],
                                       capture_output=True,text=True,timeout=90)
                (out / f"{label}_compile.log").write_text(build.stdout+build.stderr,encoding="utf-8")
                if build.returncode:
                    raise RuntimeError(f"{label} compile failed")
                run = subprocess.run([str(exe)],capture_output=True,text=True,timeout=60)
                (out / f"{label}_run.log").write_text(run.stdout+run.stderr,encoding="utf-8")
                if label=="candidate":
                    if run.returncode:
                        raise RuntimeError(run.stderr.strip())
                    report.update(json.loads(run.stdout))
                else:
                    report["CRC_mutation_detected"] = run.returncode!=0 and "FAIL " in run.stderr
            report["pass"] = report["pass"] and report["CRC_mutation_detected"]
    except Exception as exc:
        report.update(error=f"{type(exc).__name__}: {exc}")
        report["pass"] = False
    (out / "report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
