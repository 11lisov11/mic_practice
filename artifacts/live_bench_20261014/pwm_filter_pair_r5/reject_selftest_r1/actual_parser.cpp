#include <cstring>

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

#include "break_wire.h"
static bw_receiver g_break_wire;
uint8_t g_rx_rejected[UV3_FRAME];
uint32_t g_rx_rejected_ms=0,g_rx_poll_ms=0,g_rx_poll_gap_max_ms=0;
bool g_bp_mcsdk_telemetry=true,g_pwm_enabled=false;
uint8_t g_bp_status=1;
uint32_t g_bp_fw_build=BW_NUCLEO_BUILD,g_bp_last_rsp_ms=100;
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
  const uint32_t poll_ms = millis();
  if (g_rx_poll_ms) LinkTiming::maximum(g_rx_poll_gap_max_ms, poll_ms-g_rx_poll_ms);
  g_rx_poll_ms = poll_ms;
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
      if (!uv3_crc_ok(buf)) {
        memcpy(g_rx_rejected,buf,sizeof(buf)); g_rx_rejected_ms=millis();
      }
      if (buf[2] == BW_VERSION) {
        const bool had_rejection=g_break_wire.first_reject.valid;
        const uint32_t observed_ms=millis();
        const uint32_t observed_age=(uint32_t)(observed_ms-g_bp_last_rsp_ms);
        const bool fresh_off = g_bp_mcsdk_telemetry && !g_pwm_enabled &&
            (g_bp_status & 0x22U) == 0U && observed_age < 300U;
        if (!uv3_crc_ok(buf)) {
          (void)bw_note_reject(&g_break_wire,BW_REJECT_FRAME_CRC,buf,g_bp_fw_build,fresh_off,observed_ms);
          if (g_nucleo_rx_bad < 0xFFFFU) ++g_nucleo_rx_bad;
          if (g_nucleo_rx_bad_integrity < 0xFFFFU) ++g_nucleo_rx_bad_integrity;
        } else {
          (void)bw_receive(&g_break_wire,buf,g_bp_fw_build,fresh_off,observed_ms);
        }
        if (!had_rejection && g_break_wire.first_reject.valid) {
          g_break_wire.first_reject.bp_status=g_bp_status;
          g_break_wire.first_reject.pwm_enabled=g_pwm_enabled;
          g_break_wire.first_reject.rsp_age_ms=observed_age;
        }
        continue;
      }
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
int control_tests() {
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
 return 0;
}

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

void observation_tests(){
 flush_partial();bw_reset(&g_break_wire);g_bp_status=0x63;g_pwm_enabled=true;g_bp_last_rsp_ms=65;
 uint8_t empty[BW_BYTES]={};Reply p{};bw_packet(p.data(),empty,0,0);
 const auto last=g_nucleo_last_rx_ms;g_nucleo_waiting_rsp=true;
 feed(p);
 check(g_break_wire.bad_pages==1 && g_break_wire.first_reject.valid,"first reject retained");
 const auto first=g_break_wire.first_reject;
 check(first.reason==BW_REJECT_NOT_FRESH_OFF && first.now_ms==100 && first.rsp_age_ms==35 &&
   first.bp_status==0x63 && first.pwm_enabled==1 && !first.fresh_off,"caller captures actual off-transition context");
 check(!memcmp(first.packet,p.data(),UV3_FRAME) && uv3_crc_ok(first.packet),"complete CRC-valid raw page retained");
 check(g_nucleo_last_rx_ms==last && g_nucleo_waiting_rsp,"reject cannot acknowledge control");
 p[15]^=1;const auto old_crc=g_nucleo_rx_bad_integrity;feed(p);
 check(g_nucleo_rx_bad_integrity==old_crc+1 && g_break_wire.bad_pages==2,"later corruption still counted");
 check(!memcmp(&first,&g_break_wire.first_reject,sizeof(first)),"later reject cannot overwrite first");
 bw_reset(&g_break_wire);check(!g_break_wire.first_reject.valid && g_break_wire.bad_pages==0,"peer reset clears diagnostic as before");
}

int main(){control_tests();wire_tests();observation_tests();return 0;}
