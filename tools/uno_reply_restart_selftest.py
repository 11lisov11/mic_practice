"""Reproduce a truncated peer reply across restart using the actual Uno parser."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def function(source, name):
    match = re.search(r"static (?:void|uint8_t) " + name + r"\([^;]*?\)\s*\{", source)
    if not match:
        raise RuntimeError("Missing function: " + name)
    depth, end = 1, match.end()
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    path = root / "UNOQ_MOTOR/UNOQ_MOTOR.ino"
    source = path.read_text(encoding="utf-8-sig")
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    code = r'''
#include <array>
#include <cstdint>
#include <cstdio>
#include <deque>
#include <cstdlib>
constexpr unsigned BP_FRAME_LEN=32, BP_CRC_OFF=31, BP_REPLY_TIMEOUT_MS=100;
constexpr uint8_t BP_VER=2;
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
'''
    code += function(source, "nucleo_crc8")
    code += r'''
bool nucleo_check_reply(const uint8_t *p,bool,uint8_t seq) {
 return p[2]==BP_VER && p[4]==seq && nucleo_crc8(p,BP_CRC_OFF)==p[BP_CRC_OFF];
}
'''
    code += function(source, "nucleo_uart_poll")
    code += r'''
void check(bool v) { if(!v) { std::fprintf(stderr,"parser restart assertion failed\n"); std::exit(1); } }
void feed(const std::array<uint8_t,32>& p,unsigned n=32) {
 for(unsigned i=0;i<n;++i) NUCLEO_SERIAL.bytes.push_back(p[i]);
 nucleo_uart_poll();
}
int main() {
 std::array<uint8_t,32> a{};
 a[0]=0x55; a[1]=0xAA; a[2]=BP_VER; a[4]=7; a[15]=1; a[31]=nucleo_crc8(a.data(),31);
 feed(a); check(g_nucleo_rx_good==1 && g_nucleo_rx_bad==0);
 feed(a,16); check(g_nucleo_rx_bad==0);
 auto b=a; b[15]=2; b[31]=nucleo_crc8(b.data(),31);
 feed(b); check(g_nucleo_rx_bad_integrity==1 && g_nucleo_rx_bad_sequence==0);
 feed(b); check(g_nucleo_rx_good==2 && g_nucleo_rx_bad_integrity==1);
 for(unsigned i=0;i<100;++i) feed(b);
 check(g_nucleo_rx_good==102 && g_nucleo_rx_bad_integrity==1);
 std::puts("PASS: partial old reply + restarted peer => one rejected mixed frame, recovery on next complete frame");
}
'''
    compiler = shutil.which("g++")
    if not compiler:
        raise RuntimeError("g++ required")
    with tempfile.TemporaryDirectory() as tmp:
        unit, exe = Path(tmp) / "reply.cpp", Path(tmp) / "reply.exe"
        unit.write_text(code, encoding="utf-8")
        build = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                                str(unit), "-o", str(exe)], capture_output=True, text=True)
        (out / "build.log").write_text(build.stdout + build.stderr, encoding="utf-8")
        if build.returncode:
            raise RuntimeError("Parser harness compile failed")
        run = subprocess.run([str(exe)], capture_output=True, text=True)
        (out / "run.log").write_text(run.stdout + run.stderr, encoding="utf-8")
    report = {"pass": run.returncode == 0, "hardware_commands": 0,
              "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "scope": "actual parser with host serial/clock/reply-state stubs",
              "peer_restart_corruption_mechanism_reproduced": run.returncode == 0,
              "physical_cause_proven": False, "powered_command_CRC_cause_proven": False}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return run.returncode


if __name__ == "__main__":
    raise SystemExit(main())
