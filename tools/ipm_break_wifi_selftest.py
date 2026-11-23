"""Offline adversarial checks of the matched diagnostic pair and real HTTP route."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from prepare_ipm_break_wifi import ROOT, prepare
from uart_v3_uno_peer_selftest import PREAMBLE, TESTS
from uno_reply_restart_selftest import function
from ipm_break_snapshot_selftest import host_program


WIRE_TESTS = r'''
static unsigned wire_cases;
void wire_tests() {
 for(unsigned previous:{1U,100U,32768U,50000U,65535U}) {
  check(bw_peer_reset_required(BW_NUCLEO_BUILD,BW_NUCLEO_BUILD,(uint16_t)previous,0,10),"any saturated counter decrease is reboot"); ++wire_cases;
 }
 check(!bw_peer_reset_required(BW_NUCLEO_BUILD,BW_NUCLEO_BUILD,65535,65535,10),"saturated stable count does not reset"); ++wire_cases;
 check(bw_peer_reset_required(2026101006,BW_NUCLEO_BUILD,0,1,10),"identity change resets"); ++wire_cases;
 check(bw_peer_reset_required(BW_NUCLEO_BUILD,BW_NUCLEO_BUILD,0,1,301),"gap resets"); ++wire_cases;
 uint8_t record[BW_BYTES]={}, packet[UV3_FRAME];
 bw_put32(record,0x314b5242); bw_put32(record+4,2); bw_put32(record+8,BW_BYTES);
 bw_put32(record+16,0x80); bw_put32(record+88,1);
 bw_receiver rx{};
 auto pages=[&](uint32_t now) { for(unsigned p=0;p<4;++p) {
   bw_packet(packet,record,1,p); check(bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,now+p*200),"good pages");
 }};
 pages(0); check(rx.complete[1] && !rx.complete[0] && !std::memcmp(rx.data[1],record,92),"assemble 92 bytes"); ++wire_cases;
 bw_reset(&rx); for(unsigned p:{3U,1U,1U,0U,2U}) {
  bw_packet(packet,record,1,p); check(bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,100),"reorder/duplicate page");
 } check(rx.complete[1],"out of order complete"); ++wire_cases;
 for(unsigned pos=0;pos<UV3_FRAME;++pos) for(unsigned bit=0;bit<8;++bit) {
  bw_reset(&rx); bw_packet(packet,record,1,0); packet[pos]^=(uint8_t)(1U<<bit);
  check(!bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,0) && !rx.complete[1],"single-bit diagnostic corruption"); ++wire_cases;
 }
 for(unsigned missing=0;missing<4;++missing) {
  bw_reset(&rx); for(unsigned p=0;p<4;++p) if(p!=missing) {
   bw_packet(packet,record,1,p); bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,0);
  } check(!rx.complete[1],"missing page not committed"); ++wire_cases;
 }
 for(unsigned field:{2U,3U,4U,5U,6U,38U}) {
  bw_reset(&rx); bw_packet(packet,record,1,0); packet[field]=255; uv3_seal(packet);
  check(!bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,0),"CRC-valid invalid metadata"); ++wire_cases;
 }
 bw_reset(&rx); bw_packet(packet,record,1,3); packet[37]=1; uv3_seal(packet);
 check(!bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,0),"padding rejected"); ++wire_cases;
 bw_reset(&rx); bw_packet(packet,record,1,0);
 check(!bw_receive(&rx,packet,2026101006,true,0),"wrong firmware peer"); ++wire_cases;
 check(!bw_receive(&rx,packet,BW_NUCLEO_BUILD,false,0),"active/stale peer rejected"); ++wire_cases;
 bw_reset(&rx); bw_packet(packet,record,1,0); bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,0);
 for(unsigned p=1;p<4;++p) { bw_packet(packet,record,1,p); bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,2001); }
 check(!rx.complete[1],"incomplete assembly expires"); ++wire_cases;
 bw_reset(&rx); bw_packet(packet,record,1,0); bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,UINT32_MAX-5);
 for(unsigned p=1;p<4;++p) { bw_packet(packet,record,1,p); bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,5); }
 check(rx.complete[1],"assembly tick rollover"); ++wire_cases;
 // Correct per-packet CRC does not make a mixed record valid.
 bw_reset(&rx); for(unsigned p=0;p<4;++p) {
  bw_packet(packet,record,1,p); if(p==1) { packet[15]^=1; uv3_seal(packet); }
  bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,100);
 } check(!rx.complete[1],"whole-record CRC rejects mixed pages"); ++wire_cases;
 bw_reset(&rx); bw_packet(packet,record,1,0); bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,100);
 packet[15]^=1; uv3_seal(packet);
 check(!bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,100) && rx.stage[1].mask==0,"conflicting duplicate page"); ++wire_cases;
 for(unsigned offset:{0U,4U,8U,16U,52U,88U}) {
  bw_reset(&rx); uint8_t bad[92]; std::memcpy(bad,record,92); bw_put32(bad+offset,99);
  for(unsigned p=0;p<4;++p) { bw_packet(packet,bad,1,p); bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,0); }
  check(!rx.complete[1],"CRC-valid invalid record ABI"); ++wire_cases;
 }
 bw_reset(&rx); uint8_t empty[92]={}; for(unsigned p=0;p<4;++p) {
  bw_packet(packet,empty,0,p); bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,100);
 } check(rx.complete[0] && bw_u32(rx.data[0])==0,"explicit no-event record"); ++wire_cases;
 bw_reset(&rx); uint8_t different[92]; std::memcpy(different,record,92); bw_put32(different+12,500);
 for(unsigned p=0;p<2;++p) { bw_packet(packet,record,1,p); bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,0); }
 for(unsigned p=2;p<4;++p) { bw_packet(packet,different,1,p); bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,100); }
 check(!rx.complete[1],"different event CRC never spliced"); ++wire_cases;
 // Exercise actual Uno byte parser, not just the assembler.
 flush_partial(); bw_reset(&g_break_wire); g_nucleo_waiting_rsp=true;
 const auto good_before=g_nucleo_rx_good;
 const auto last_before=g_nucleo_last_rx_ms;
 for(unsigned p=0;p<4;++p) {
  Reply diagnostic{}; bw_packet(diagnostic.data(),record,1,p); feed(diagnostic);
 }
 check(g_break_wire.complete[1] && g_nucleo_waiting_rsp && g_nucleo_rx_good==good_before &&
       g_nucleo_last_rx_ms==last_before,"diagnostics cannot ACK or refresh control timestamp"); ++wire_cases;
 Reply diagnostic{}; bw_packet(diagnostic.data(),record,1,0); diagnostic[15]^=1;
 const auto bad_before=g_nucleo_rx_bad_integrity; feed(diagnostic);
 check(g_nucleo_rx_bad_integrity==bad_before+1,"damaged diagnostic cannot hide a control integrity error"); ++wire_cases;
 std::printf("{\"wire_cases\":%u,\"wire_assertions\":%u}\n",wire_cases,tests);
}
'''


def load_module(path):
    spec = importlib.util.spec_from_file_location("ipm_snapshot_candidate_server", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def emitter_program():
    prefix = host_program().split("int main(", 1)[0]
    emitter = (ROOT / "research/ipm_break/nucleo_emitter.inc").read_text()
    return '#include <array>\n#include <vector>\n' + prefix + r'''
#include "break_wire.h"
enum { RUN=6, UNO_REPLY_TIMEOUT_MS=5, HAL_OK=0 };
struct { bool command_enabled; } uno_link;
uint32_t mic_break_diag_tx_errors;
int huart1, mc_state, transmit_status;
std::vector<std::array<uint8_t,UV3_FRAME>> sent;
int MC_GetSTMStateMotor1() { return mc_state; }
bool LL_TIM_IsEnabledAllOutputs(TIM_TypeDef *t) { return (t->BDTR & (1U<<15))!=0; }
int HAL_UART_Transmit(int *,uint8_t *packet,unsigned length,unsigned timeout) {
 assert(length==UV3_FRAME && timeout==5);
 std::array<uint8_t,UV3_FRAME> copy{}; std::memcpy(copy.data(),packet,length);
 sent.push_back(copy); return transmit_status;
}
''' + emitter + r'''
int main() {
 reset(); timer.BDTR&=~(1U<<15); uint32_t now=200; unsigned count=0;
 uno_link.command_enabled=true; mic_send_break_page(now); assert(sent.empty()); ++count;
 uno_link.command_enabled=false; mic_break_start_window=1;
 mic_send_break_page(now); assert(sent.empty()); ++count;
 mic_break_start_window=0; timer.BDTR|=1U<<15;
 mic_send_break_page(now); assert(sent.empty()); ++count;
 timer.BDTR&=~(1U<<15); mc_state=RUN;
 mic_send_break_page(now); assert(sent.empty()); ++count;
 mc_state=0; mic_send_break_page(now); assert(sent.size()==1 && sent[0][2]==BW_VERSION); ++count;
 mic_send_break_page(now+199); assert(sent.size()==1); ++count;
 bw_receiver rx{};
 bw_receive(&rx,sent[0].data(),BW_NUCLEO_BUILD,true,now);
 for(unsigned i=1;i<8;++i) {
  now+=200; mic_send_break_page(now);
  bw_receive(&rx,sent.back().data(),BW_NUCLEO_BUILD,true,now);
 }
 assert(rx.complete[0] && rx.complete[1] && bw_u32(rx.data[0])==0 && bw_u32(rx.data[1])==0); ++count;
 // Actual recorded IRQ is propagated through emitter and assembler, without RUN.
 timer.SR=TIM_SR_BIF; clock_ms=now; mic_break_start_window=1;
 TIMx_BRK_M1_IRQHandler(); mic_break_start_window=0;
 bw_reset(&rx);
 for(unsigned i=0;i<8;++i) {
  now+=200; mic_send_break_page(now); bw_receive(&rx,sent.back().data(),BW_NUCLEO_BUILD,true,now);
 }
 assert(rx.complete[0] && rx.complete[1] && bw_u32(rx.data[1])==MIC_BREAK_MAGIC);
 assert(bw_u32(rx.data[1]+16)&TIM_SR_BIF); ++count;
 transmit_status=1; now+=200; mic_send_break_page(now);
 assert(mic_break_diag_tx_errors==1 && (timer.BDTR&(1U<<12))); ++count;
 mic_break_diag_tx_errors=UINT32_MAX; now+=200; mic_send_break_page(now);
 assert(mic_break_diag_tx_errors==UINT32_MAX); ++count;
 std::printf("{\"pass\":true,\"emitter_cases\":%u}\n",count);
}
'''


def hmi_tests(module):
    checks = []
    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
    base = "DATA state=SAFE mode=VF pwm=0 bp_fw_build=2026101102 fw_build=2026101103 rpc_schema=3 bp_age_ms=10"
    values = [0] * 23
    values[:5] = [0x314B5242, 2, 92, 1200, 0x80]
    values[6] = 0x1000; values[12] = 0x40; values[13] = 1
    values[14] = 1180; values[15] = 100; values[19] = 321; values[20] = 520; values[22] = 1
    text = struct.pack("<23I", *values).hex()
    line = base + f" mc_break1_hex={text} mc_break1_age_ms=100"
    parsed = module.RpcBridge._parse_status_string(line)
    check("real HMI text decoder carries record", parsed["mc_break_snapshots"][1]["captured"])
    record = parsed["mc_break_snapshots"][1]
    check("reference not rotor speed", record["cached_context"]["reference_electrical_hz"] == 10)
    check("context age", record["cached_context"]["age_at_irq_ms"] == 20)
    check("GPIO and BKE decode", record["event"]["pa6_high_at_irq"] and record["event"]["bke_at_irq"])
    for field, bad in (("bp_fw_build", "2026101006"), ("bp_age_ms", "300"), ("mc_break1_age_ms", "5001"),
                       ("mc_break1_age_ms", "-1"), ("mc_break1_age_ms", "nan"), ("mc_break1_hex", "xx")):
        kv = dict(part.split("=", 1) for part in line.split()[1:]); kv[field] = bad
        result = module.break_wire_status(kv)["mc_break_snapshots"][1]
        check("reject " + field + "=" + bad, not result["available"])
    for offset, bad in ((0, 0), (1, 1), (2, 88), (4, 0), (13, 2), (22, 0)):
        altered = values.copy(); altered[offset] = bad
        kv = dict(part.split("=", 1) for part in line.split()[1:]); kv["mc_break1_hex"] = struct.pack("<23I", *altered).hex()
        check("reject ABI word " + str(offset), not module.break_wire_status(kv)["mc_break_snapshots"][1]["captured"])
    kv = dict(part.split("=", 1) for part in line.split()[1:]); kv["mc_break1_hex"] = bytes(92).hex()
    check("no-event not treated as fault", module.break_wire_status(kv)["mc_break_snapshots"][1]["reason"] == "no_recorded_break")
    # Real route: authentication failure, successful read, no commands or heartbeat.
    class RPC:
        reads = 0
        def get(self):
            self.reads += 1
            return True, module.RpcBridge._parse_status_string(line), ""
        def cmd(self, *args):
            raise AssertionError("read-only route issued a command")
    class Logs:
        def add(self, line):
            pass
    counts = {"heartbeat": 0, "log": 0}
    def heartbeat(): counts["heartbeat"] += 1
    def log(data): counts["log"] += 1
    app = SimpleNamespace(rpc=RPC(), logs=Logs(), control_access=SimpleNamespace(enabled=True, read_token=lambda: "test-snapshot-key"),
                          mark_operator_heartbeat=heartbeat, maybe_log_status=log)
    http = module.ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    http.app = app
    worker = threading.Thread(target=http.serve_forever, daemon=True); worker.start()
    url = f"http://127.0.0.1:{http.server_port}/api/break-snapshot"
    try:
        try:
            urlopen(url, timeout=5)
        except HTTPError as exc:
            check("GET snapshot requires key", exc.code == 401 and app.rpc.reads == 0)
        else:
            raise AssertionError("missing auth accepted")
        request = Request(url, headers={"X-UNOQ-Control-Token": "test-snapshot-key"})
        with urlopen(request, timeout=5) as response:
            data = json.load(response)
            check("GET snapshot structured JSON", data["ok"] and data["data"]["mc_break_snapshots"][1]["captured"])
        check("GET did not extend operator heartbeat", counts["heartbeat"] == 0)
        check("GET only read and logged", app.rpc.reads == 1 and counts["log"] == 1)
    finally:
        http.shutdown(); http.server_close(); worker.join(timeout=5)
    return checks


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--outdir", type=Path, required=True)
    args = p.parse_args(); out = args.outdir.resolve(); out.mkdir(parents=True, exist_ok=False)
    prepare(out / "candidate")
    folder = out / "candidate/UNOQ_MOTOR"
    source = (folder / "UNOQ_MOTOR.ino").read_text()
    a = source.index("static bool nucleo_check_reply("); b = source.index("  const bool clear_ack", a)
    integrity = source[a:b] + "  return true;\n}\n"
    preamble = "#include <cstring>\n" + PREAMBLE + r'''
#include "break_wire.h"
static bw_receiver g_break_wire;
bool g_bp_mcsdk_telemetry=true, g_pwm_enabled=false;
uint8_t g_bp_status=1;
uint32_t g_bp_fw_build=BW_NUCLEO_BUILD, g_bp_last_rsp_ms=100;
'''
    code = preamble + integrity + function(source, "nucleo_uart_poll") + TESTS.replace("int main()", "int control_tests()")
    code = code.replace('cases,tests);\n}', 'cases,tests);\n  return 0;\n}', 1)
    code += WIRE_TESTS + "\nint main() { control_tests(); wire_tests(); return 0; }\n"
    unit = out / "host_test.cpp"; unit.write_text(code)
    reports = {}
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / "wire.exe"
        header_path = folder / "uart_v3_transport.h"
        header = header_path.read_text()
        for label, body in (("candidate", header), ("crc_mutation", header.replace(
                "return stored == uv3_crc32c(frame, UV3_PAYLOAD);", "(void)stored; return true;"))):
            header_path.write_text(body)
            build = subprocess.run([shutil.which("g++"), "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                "-I", str(folder), str(unit), "-o", str(exe)], capture_output=True, text=True)
            (out / f"{label}_compile.log").write_text(build.stdout + build.stderr)
            if build.returncode:
                raise RuntimeError("Host build failed: " + label)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            (out / f"{label}_run.log").write_text(run.stdout + run.stderr)
            if label == "candidate":
                if run.returncode:
                    raise RuntimeError(run.stderr)
                reports = [json.loads(line) for line in run.stdout.splitlines()]
            elif run.returncode == 0:
                raise RuntimeError("CRC negative control escaped detection")
        header_path.write_text(header)
        emitter_unit = out / "emitter_test.cpp"
        emitter_unit.write_text(emitter_program())
        build = subprocess.run([shutil.which("g++"), "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
            "-I", str(folder), "-I", str(ROOT / "research/ipm_break"), str(emitter_unit), "-o", str(exe)],
            capture_output=True, text=True)
        (out / "emitter_compile.log").write_text(build.stdout + build.stderr)
        if build.returncode:
            raise RuntimeError("Emitter host build failed")
        run = subprocess.run([str(exe)], capture_output=True, text=True)
        (out / "emitter_run.log").write_text(run.stdout + run.stderr)
        if run.returncode:
            raise RuntimeError("Emitter host assertions failed")
        emitter_report = json.loads(run.stdout)
    module = load_module(out / "candidate/web_hmi/server.py")
    hmi = hmi_tests(module)
    assert 'bw_peer_reset_required(previous_build,g_bp_fw_build,previous_good,g_bp_good_cnt,previous_age)' in source
    report = {"pass": True, "control_parser": reports[0], "wire": reports[1], "emitter": emitter_report, "hmi_cases": len(hmi),
              "hmi_checks": hmi, "CRC_mutation_detected": True, "hardware_commands": 0,
              "scope": "Actual Uno byte parser, shared assembler, actual HMI decoder and authenticated local HTTP route; UART hardware mocked"}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"pass": True, "control_cases": reports[0]["cases"], "wire_cases": reports[1]["wire_cases"],
                      "emitter_cases": emitter_report["emitter_cases"], "hmi_cases": len(hmi)}))


if __name__ == "__main__":
    main()
