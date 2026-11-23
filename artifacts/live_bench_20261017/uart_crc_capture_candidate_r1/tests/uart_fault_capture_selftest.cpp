#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>

#include "uart_fault_wire.h"

using Frame = std::array<uint8_t, UV3_FRAME>;

static Frame make_frame() {
  Frame frame{};
  frame[0] = 0xAA;
  frame[1] = 0x55;
  frame[2] = UV3_VERSION;
  frame[3] = 1;
  frame[4] = 3;
  frame[5] = 7;
  frame[6] = 0x34;
  frame[7] = 0x12;
  uv3_seal(frame.data());
  return frame;
}

static uv3_result feed(uv3_rx &rx, const Frame &frame, uint32_t start = 10U,
                       uint8_t marked_index = 0xFFU, uint8_t mark = 0U) {
  uv3_result result = UV3_WAIT;
  for (unsigned i = 0; i < frame.size(); ++i) {
    result = uv3_byte(&rx, frame[i], i == marked_index ? mark : 0U,
                      start + i / 8U);
  }
  return result;
}

static void checksum_capture() {
  uv3_rx rx{};
  uv3_init(&rx, false);
  Frame bad = make_frame();
  bad[19] ^= 0x40U;
  const uv3_result result = feed(rx, bad);
  assert(result == UV3_BAD_CRC);
  assert(rx.fault_latched && rx.fault == UV3_BAD_CRC);
  assert(rx.fault_capture_valid && rx.fault_capture_detail == UV3_DETAIL_CHECKSUM);
  assert(rx.fault_capture_length == UV3_FRAME);
  assert(std::memcmp(rx.fault_capture_frame, bad.data(), bad.size()) == 0);
  assert(rx.fault_capture_uart_flags == 0U && rx.fault_capture_ne_bytes == 0U);
  std::puts("PASS checksum mismatch retained with all 43 received bytes");
}

static void valid_running_and_replay_guard() {
  uv3_rx rx{};
  uv3_init(&rx, false);
  Frame first = make_frame();
  assert(feed(rx, first) == UV3_READY);
  assert(rx.index == 0U && !rx.fault_latched && !rx.fault_capture_valid);
  uv3_commit(&rx, 20U, true, false, false);
  assert(rx.link_seen && rx.run_anchor);

  Frame next = first;
  ++next[5];
  uv3_seal(next.data());
  assert(feed(rx, next, 25U) == UV3_READY);
  uv3_commit(&rx, 35U, true, false, false);
  assert(rx.previous[5] == next[5] && rx.run_anchor && !rx.fault_latched);

  assert(feed(rx, first, 40U) == UV3_BAD_SEQUENCE);
  assert(rx.fault_latched && rx.fault_capture_detail == UV3_DETAIL_SEQUENCE);
  assert(rx.fault_capture_length == UV3_FRAME);
  std::puts("PASS valid RUN heartbeat still advances sequence; replay still fail-stops");
}

static void sync_capture() {
  uv3_rx rx{};
  uv3_init(&rx, false);
  rx.link_seen = true;
  assert(uv3_byte(&rx, 0xAAU, 0U, 20U) == UV3_WAIT);
  assert(uv3_byte(&rx, 0x00U, 0U, 20U) == UV3_BAD_CRC);
  assert(rx.fault_capture_detail == UV3_DETAIL_SYNC_SECOND);
  assert(rx.fault_capture_length == 2U);
  assert(rx.fault_capture_frame[0] == 0xAAU && rx.fault_capture_frame[1] == 0U);

  uv3_init(&rx, false);
  rx.link_seen = true;
  assert(uv3_byte(&rx, 0x7EU, 0U, 30U) == UV3_BAD_CRC);
  assert(rx.fault_capture_detail == UV3_DETAIL_SYNC_START);
  assert(rx.fault_capture_length == 1U && rx.fault_capture_frame[0] == 0x7EU);
  std::puts("PASS sync-start and second-byte errors are distinguishable");
}

static void uart_mark_and_timeout_capture() {
  uv3_rx rx{};
  uv3_init(&rx, false);
  assert(uv3_byte(&rx, 0xAAU, UV3_FE, 40U) == UV3_HARD_UART);
  assert(rx.fault_capture_detail == UV3_DETAIL_UART_FE);
  assert(rx.fault_capture_uart_flags == UV3_FE && rx.fault_capture_length == 1U);
  assert(rx.fault_capture_marks[0] == UV3_FE);

  uv3_init(&rx, false);
  assert(uv3_byte(&rx, 0xAAU, 0U, 50U) == UV3_WAIT);
  assert(uv3_tick(&rx, 66U) == UV3_FRAME_TIMEOUT);
  assert(rx.fault_capture_detail == UV3_DETAIL_FRAME_TIMEOUT);
  assert(rx.fault_capture_length == 1U && rx.fault_capture_frame[0] == 0xAAU);
  std::puts("PASS UART FE mark and partial-frame deadline are captured");
}

static void bounded_fail_stop_unchanged() {
  uv3_rx rx{};
  uv3_init(&rx, true);
  Frame bad = make_frame();
  bad[24] ^= 0x01U;
  assert(feed(rx, bad) == UV3_DROPPED);
  assert(!rx.fault_latched && !rx.fault_capture_valid);
  assert(feed(rx, bad, 20U) == UV3_DROPPED);
  assert(!rx.fault_latched && !rx.fault_capture_valid);
  assert(feed(rx, bad, 30U) == UV3_BAD_CRC);
  assert(rx.fault_latched && rx.fault_capture_valid);
  assert(rx.fault == UV3_BAD_CRC && rx.fault_capture_detail == UV3_DETAIL_CHECKSUM);
  assert(std::memcmp(rx.fault_capture_frame, bad.data(), bad.size()) == 0);
  std::puts("PASS bounded two-drop tolerance and existing fail-stop threshold remain intact");
}

static void passive_wire_roundtrip() {
  uv3_rx source{};
  uv3_init(&source, false);
  Frame bad = make_frame();
  bad[12] ^= 0x80U;
  assert(feed(source, bad, 90U) == UV3_BAD_CRC);
  uint8_t record[UFW_RECORD_BYTES]{};
  ufw_make_record(record, &source);
  const uint32_t record_crc = uv3_crc32c(record, sizeof(record));

  ufw_receiver receiver{};
  for (unsigned page = 0; page < UFW_PAGES; ++page) {
    uint8_t packet[UV3_FRAME]{};
    ufw_packet(packet, record, record_crc, page);
    assert(uv3_crc_ok(packet));
    assert(ufw_receive(&receiver, packet, UFW_NUCLEO_BUILD, true, 100U + page));
  }
  assert(receiver.complete && receiver.peer_build == UFW_NUCLEO_BUILD);
  assert(std::memcmp(receiver.data, record, sizeof(record)) == 0);

  ufw_receiver blocked{};
  uint8_t packet[UV3_FRAME]{};
  ufw_packet(packet, record, record_crc, 0U);
  assert(!ufw_receive(&blocked, packet, UFW_NUCLEO_BUILD, false, 200U));
  assert(blocked.bad_pages == 1U && !blocked.complete);

  ufw_receiver wrong_build{};
  assert(!ufw_receive(&wrong_build, packet, UFW_NUCLEO_BUILD - 1U, true, 200U));
  assert(wrong_build.bad_pages == 1U && !wrong_build.complete);
  std::puts("PASS D3 pages round-trip with CRC, peer-build and outputs-off checks");
}

int main() {
  checksum_capture();
  valid_running_and_replay_guard();
  sync_capture();
  uart_mark_and_timeout_capture();
  bounded_fail_stop_unchanged();
  passive_wire_roundtrip();
  return 0;
}
