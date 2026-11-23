
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
static bool nucleo_check_reply(const uint8_t *rx, bool require_sequence, uint8_t expected_sequence) {
  if (!rx) return false;
  if (rx[0] != 0x55 || rx[1] != 0xAA) return false;
  if (rx[2] != BP_VER) return false;
  if (!uv3_crc_ok(rx)) return false;
  if (require_sequence && rx[4] != expected_sequence) return false;
  return true;
}
static void nucleo_uart_poll() {
  static uint8_t st = 0;
  static uint8_t idx = 0;
  static uint8_t buf[BP_FRAME_LEN];
  while (NUCLEO_SERIAL.available() > 0) {
    uint8_t b = (uint8_t)NUCLEO_SERIAL.read();
    // Detect the motor controller's boot ping (0x5A 0xA5 ...) to diagnose RX wiring/baud
    // even when no valid reply frames are received yet.
    if (g_bp_ping_prev == 0x5A && b == 0xA5) {
      if (g_bp_ping_pairs < 0xFFFFFFFFu) g_bp_ping_pairs++;
      g_bp_ping_ms = millis();
    }
    g_bp_ping_prev = b;
    if (st == 0) {
      if (b == 0x55) {
        buf[0] = b;
        st = 1;
      }
      continue;
    }
    if (st == 1) {
      if (b == 0xAA) {
        buf[1] = b;
        idx = 2;
        st = 2;
      } else if (b == 0x55) {
        buf[0] = b;
        st = 1;
      } else {
        st = 0;
      }
      continue;
    }
    // st == 2
    buf[idx++] = b;
    if (idx >= sizeof(buf)) {
      st = 0;
      idx = 0;
      const bool integrity_ok = buf[0] == 0x55 && buf[1] == 0xAA &&
          buf[2] == BP_VER && uv3_crc_ok(buf);
      if (integrity_ok && g_nucleo_superseded.consume(
              buf[4], micros(), BP_REPLY_TIMEOUT_MS * 1000U)) {
        if (g_nucleo_rx_superseded < 0xFFFFu) g_nucleo_rx_superseded++;
      } else if (g_nucleo_waiting_rsp &&
          nucleo_check_reply(buf, true, g_nucleo_waiting_seq)) {
        if (g_nucleo_rx_good < 0xFFFFu) g_nucleo_rx_good++;
        g_nucleo_last_rx_ms = millis();
        g_link_led_ms = g_nucleo_last_rx_ms;
      } else {
        if (g_nucleo_rx_bad < 0xFFFFu) g_nucleo_rx_bad++;
        if (!integrity_ok) {
          if (g_nucleo_rx_bad_integrity < 0xFFFFu) g_nucleo_rx_bad_integrity++;
        } else if (g_nucleo_rx_bad_sequence < 0xFFFFu) {
          g_nucleo_rx_bad_sequence++;
        }
      }
    }
  }
}
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
