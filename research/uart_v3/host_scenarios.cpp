// Included after the extracted production MCSDK control functions and mocks.
#include "uart_v3_transport.h"

using V3Frame = std::array<uint8_t, UV3_FRAME>;
#if defined(UV3_INTEGRATED_TEST)
uv3_rx &candidate = uno_transport;
#else
uv3_rx candidate;
#endif
unsigned cases = 0;
unsigned isolated_accepted = 0, strict_rejected = 0;

V3Frame v3_frame(uint8_t flags = 1, uint8_t mode = 3, uint32_t freq = 10000,
                 uint8_t seq = 81) {
  Frame legacy = frame(flags, mode, freq, seq);
  V3Frame result{};
  std::memcpy(result.data(), legacy.data(), UV3_BASE_PAYLOAD);
  result[2] = UV3_VERSION;
  uv3_seal(result.data());
  return result;
}

void dispatch_result(uv3_result result) {
#if defined(UV3_INTEGRATED_TEST)
  uno_transport_result(result);
#else
  if (result == UV3_WAIT) return;
  if (result != UV3_READY) {
    const uint8_t reason = result == UV3_BAD_CRC ? UNO_DIAG_CRC :
        result == UV3_BAD_VERSION ? UNO_DIAG_VERSION : result == UV3_BAD_SEQUENCE ? UNO_DIAG_REPLAY :
        result == UV3_LINK_TIMEOUT || result == UV3_FRAME_TIMEOUT ? UNO_DIAG_TIMEOUT : UNO_DIAG_UART;
    uno_capture_diagnostics(reason, candidate.last_uart_flags, 0);
    uno_link.last_bad_reason = reason;
    uno_link.last_uart_errors = candidate.last_uart_flags;
    uno_saturating_increment(&uno_link.bad_count);
    const uint8_t code = result == UV3_BAD_CRC ? UNO_FAULT_BAD_CRC :
        result == UV3_LINK_TIMEOUT || result == UV3_FRAME_TIMEOUT ? UNO_FAULT_TIMEOUT : UNO_FAULT_INTERNAL;
    uno_latch_fault_reason(code, reason);
    return;
  }
  // Offline adapter to the unchanged production semantic handler, NOT an
  // on-wire v2 fallback. Recreate its expected internal checksum/layout.
  Frame legacy{};
  std::memcpy(legacy.data(), candidate.frame, UV3_BASE_PAYLOAD);
  legacy[2] = UNO_PROTOCOL_VERSION;
  checksum(legacy);
  uno_handle_valid_frame(legacy.data());
  uno_send_reply();
  bool clean_clear = legacy[3] == UNO_FLAG_CLEAR_FAULT && legacy[4] == UNO_MODE_OFF;
  for (unsigned i = 6; i < UV3_BASE_PAYLOAD; ++i) clean_clear = clean_clear && legacy[i] == 0;
  uv3_commit(&candidate, now_ms,
             uno_link.command_enabled && motor_state == RUN,
             uno_link.fault_latched, clean_clear);
#endif
}

uv3_result consume(uint8_t byte, uint8_t flags = 0) {
#if defined(UV3_INTEGRATED_TEST)
  uno_consume_sample(byte, flags);
  return candidate.fault;
#else
  uv3_result result = uv3_byte(&candidate, byte, flags, now_ms);
  dispatch_result(result);
  return result;
#endif
}

void send(const V3Frame &f, int noisy = -1, int noisy2 = -1, uint8_t flags = UV3_NE) {
  for (unsigned i = 0; i < f.size(); ++i)
    consume(f[i], ((int)i == noisy || (int)i == noisy2) ? flags : 0);
}

void tick(uint32_t delta) {
  now_ms += delta;
  dispatch_result(uv3_tick(&candidate, now_ms));
  uno_link_poll();
}

void begin(bool bounded = true, uint32_t start_ms = 4000, uint8_t seq = 78) {
  reset(true);
  now_ms = start_ms;
  uv3_init(&candidate, bounded);
  for (unsigned i = 0; i < 3; ++i) {
    now_ms = start_ms + i * 20U;
    send(v3_frame(1, 3, 10000, (uint8_t)(seq + i)));
  }
  check(starts == 1 && motor_state == RUN && !uno_link.fault_latched,
        "three clean commands establish real mocked MCSDK RUN");
  check(candidate.clean_run_frames == 3 && candidate.run_anchor, "clean anchor established");
}

void assert_stopped(const char *name) {
  check(uno_link.fault_latched && !uno_link.command_enabled && motor_state != RUN, name);
}

void crc_vectors_and_corruption() {
  uint8_t data[32] = {};
  check(uv3_crc32c(data, 32) == 0x8a9136aaU, "RFC3720 zero vector");
  std::memset(data, 255, 32);
  check(uv3_crc32c(data, 32) == 0x62a8ab43U, "RFC3720 ones vector");
  for (unsigned i = 0; i < 32; ++i) data[i] = (uint8_t)i;
  check(uv3_crc32c(data, 32) == 0x46dd794eU, "RFC3720 increasing vector");
  for (unsigned i = 0; i < 32; ++i) data[i] = (uint8_t)(31 - i);
  check(uv3_crc32c(data, 32) == 0x113fdb5cU, "RFC3720 decreasing vector");
  const uint8_t digits[] = "123456789";
  check(uv3_crc32c(digits, 9) == 0xe3069283U, "CRC32C check string");
  check(uv3_crc32c(data, 0) == 0, "empty CRC");
  V3Frame original = v3_frame();
  for (unsigned a = 0; a < UV3_FRAME * 8; ++a) {
    V3Frame bad = original;
    bad[a / 8] ^= (uint8_t)(1U << (a % 8));
    check(!uv3_crc_ok(bad.data()), "all single bit changes detected by CRC");
    ++cases;
    for (unsigned b = a + 1; b < UV3_FRAME * 8; ++b) {
      bad = original;
      bad[a / 8] ^= (uint8_t)(1U << (a % 8));
      bad[b / 8] ^= (uint8_t)(1U << (b % 8));
      check(!uv3_crc_ok(bad.data()), "all double bit changes detected by CRC");
      ++cases;
    }
  }
  // Exhaust all burst placements/lengths <=32 with three deterministic shapes.
  // This finite sweep is NOT enumeration of every possible burst interior.
  for (unsigned length = 1; length <= 32; ++length) {
    for (unsigned first = 0; first + length <= UV3_FRAME * 8; ++first) {
      for (unsigned shape = 0; shape < 3; ++shape) {
        V3Frame bad = original;
        for (unsigned i = 0; i < length; ++i)
          if (i == 0 || i == length - 1 || shape == 0 || (shape == 1 && i % 2 == 0))
            bad[(first + i) / 8] ^= (uint8_t)(1U << ((first + i) % 8));
        check(!uv3_crc_ok(bad.data()), "short burst sweep detected");
        ++cases;
      }
    }
  }
  for (unsigned seq = 0; seq < 256; ++seq) {
    V3Frame bad = v3_frame(1, 3, 10000, (uint8_t)seq);
    bad[6] ^= 0x40; bad[7] ^= 0x40;
    check(!uv3_crc_ok(bad.data()), "paired XOR collision rejected for every sequence");
    ++cases;
  }
  for (unsigned pos = 0; pos < UV3_FRAME; ++pos) {
    for (unsigned bit = 0; bit < 8; ++bit) {
      for (int mark : {-1, 10}) {
        begin(); V3Frame bad = original;
        bad[pos] ^= (uint8_t)(1U << bit);
        unsigned before = ramps;
        send(bad, mark);
        check(ramps == before && starts == 1, "corruption cannot change ramp or start");
        if (pos >= 2) check(candidate.fault == UV3_BAD_CRC, "parser CRC rejects even unmarked corruption");
        tick(301);
        assert_stopped("corrupted frame stops by parser deadline or watchdog");
        ++cases;
      }
    }
  }
}

void noise_matrix() {
  for (unsigned seq = 0; seq < 256; ++seq) {
    for (unsigned pos = 0; pos < UV3_FRAME; ++pos) {
      begin(true, 4000, (uint8_t)(seq - 3));
      unsigned before = ramps;
      send(v3_frame(1, 3, 10000, (uint8_t)seq), (int)pos);
      check(!uno_link.fault_latched && motor_state == RUN && ramps == before && starts == 1,
            "isolated intact NE cannot cause restart or ramp change");
      check(candidate.accepted_noise_frames == 1 && candidate.observed_noise_bytes == 1,
            "accepted NE remains observable");
      check(candidate.marks[pos] == UV3_NE && candidate.clean_run_frames == 0,
            "byte mark retained and clean recovery required");
      ++isolated_accepted; ++cases;
      begin(false, 4000, (uint8_t)(seq - 3));
      send(v3_frame(1, 3, 10000, (uint8_t)seq), (int)pos);
      assert_stopped("strict CRC32C baseline rejects same intact NE frame");
      ++strict_rejected; ++cases;
    }
  }
  for (unsigned pos = 0; pos < UV3_FRAME; ++pos) {
    for (unsigned mask = 1; mask < 256; ++mask) {
      if (mask == UV3_NE) continue;
      begin(); send(v3_frame(), (int)pos, -1, (uint8_t)mask);
      assert_stopped("all hard UART/unknown flag combinations rejected at every byte");
      check(candidate.fault == UV3_HARD_UART, "hard flag diagnosis retained");
      ++cases;
    }
    for (unsigned other = pos + 1; other < UV3_FRAME; ++other) {
      begin(); send(v3_frame(), (int)pos, (int)other);
      assert_stopped("two noisy bytes exceed per-frame budget");
      ++cases;
    }
    // Every command field differs under a freshly recomputed valid CRC.
    for (unsigned field = 3; field < UV3_PAYLOAD; ++field) {
      if (field == 5) continue;
      begin(); V3Frame changed = v3_frame(); changed[field] ^= 1;
      uv3_seal(changed.data()); send(changed, (int)pos);
      assert_stopped("NE cannot authorize any changed command field");
      ++cases;
    }
    reset(true); uv3_init(&candidate, true); send(v3_frame(), (int)pos);
    check(starts == 0 && uno_link.fault_latched, "NE first start is forbidden");
    ++cases;
    begin(); send(v3_frame(8, 0, 0), (int)pos);
    assert_stopped("noisy CLEAR cannot clear fault or continue run");
    send(v3_frame(1, 3, 10000, 82));
    assert_stopped("clean ENABLE after fault cannot restart");
    send(v3_frame(8, 0, 0, 83));
    check(!uno_link.fault_latched && !candidate.fault_latched && motor_state == IDLE,
          "explicit clean CLEAR may release latch but not restart");
    ++cases;
  }
  begin(); send(v3_frame(), 8);
  send(v3_frame(1, 3, 10000, 82), 8);
  assert_stopped("adjacent noise frames forbidden until three clean commands"); ++cases;
  for (unsigned count = 0; count < 3; ++count) {
    begin(); send(v3_frame(), 8);
    for (unsigned i = 0; i < count; ++i) send(v3_frame(1, 3, 10000, (uint8_t)(82 + i)));
    send(v3_frame(1, 3, 10000, (uint8_t)(82 + count)), 8);
    assert_stopped("fewer than three clean recovery commands cannot authorize NE"); ++cases;
  }
  for (uint32_t origin : {4000U, UINT32_MAX - 70U}) {
    begin(true, origin);
    send(v3_frame(), 8);
    for (unsigned i = 0; i < 3; ++i) { now_ms += 20; send(v3_frame(1,3,10000,(uint8_t)(82+i))); }
    send(v3_frame(1,3,10000,85), 8);
    check(motor_state == RUN && candidate.accepted_noise_frames == 2, "second separated NE accepted");
    for (unsigned i = 0; i < 3; ++i) { now_ms += 20; send(v3_frame(1,3,10000,(uint8_t)(86+i))); }
    send(v3_frame(1,3,10000,89), 8);
    assert_stopped("third NE inside sliding second rejected including tick wrap"); ++cases;
  }
  begin(); send(v3_frame(), 8);
  for (unsigned i=0; i<51; ++i) { now_ms+=20; send(v3_frame(1,3,10000,(uint8_t)(82+i))); }
  send(v3_frame(1,3,10000,133), 8);
  check(motor_state == RUN && !candidate.fault_latched, "budget ages out after real elapsed second"); ++cases;
}

void framing_and_protections() {
  for (unsigned previous=0;previous<256;++previous) {
    for (unsigned incoming=0;incoming<256;++incoming) {
      begin(true,4000,(uint8_t)(previous-2));
      send(v3_frame(1,3,10000,(uint8_t)incoming));
      if((uint8_t)incoming==(uint8_t)(previous+1))
        check(motor_state==RUN && !uno_link.fault_latched,"sequential clean command including wrap accepted");
      else {
        assert_stopped("CRC-valid out-of-order RUN command rejected");
        check(candidate.fault==UV3_BAD_SEQUENCE && uno_link.first_reason==UNO_DIAG_REPLAY,
              "sequence error retains explicit replay diagnosis");
      }
      ++cases;
    }
  }
  for (unsigned prefix = 1; prefix < UV3_FRAME; ++prefix) {
    begin(); V3Frame f = v3_frame();
    for (unsigned i=0; i<prefix; ++i) consume(f[i], i == 0 ? UV3_NE : 0);
    tick(15);
    check(!uno_link.fault_latched, "partial frame allowed exactly 15 ms");
    tick(1); assert_stopped("partial frame stopped at 16 ms without refreshing watchdog"); ++cases;
  }
  for (unsigned pos = 0; pos < UV3_FRAME; ++pos) {
    begin(); auto f=v3_frame();
    for (unsigned i=0; i<f.size(); ++i) if(i!=pos) consume(f[i]);
    tick(301); assert_stopped("deleted byte cannot keep run alive"); ++cases;
    for (unsigned value=0; value<256; ++value) {
      begin();
      for (unsigned i=0; i<f.size(); ++i) {
        if (i==pos) consume((uint8_t)value);
        consume(f[i]);
      }
      tick(301); assert_stopped("inserted byte cannot keep run alive"); ++cases;
    }
  }
  begin(); send(v3_frame(1,3,10000,80), 9);
  assert_stopped("noisy duplicate sequence rejected"); ++cases;
  begin(); send(v3_frame(1,3,10000,79), 9);
  assert_stopped("noisy backwards sequence rejected"); ++cases;
  begin(); send(v3_frame(1,3,10000,82), 9);
  assert_stopped("noisy skipped sequence rejected"); ++cases;
  begin(); tick(300); check(motor_state==RUN,"watchdog boundary 300 ms");
  tick(1); assert_stopped("watchdog boundary 301 ms"); ++cases;
  begin(); consume(0x00,UV3_NE); assert_stopped("orphan NE without header rejected"); ++cases;
  begin(); auto old=v3_frame(); old[2]=2; uv3_seal(old.data()); send(old);
  assert_stopped("version 2 forbidden even with valid v3 CRC"); ++cases;
  begin(); send(v3_frame(0,0,0));
  check(motor_state==IDLE && !uno_link.command_enabled,"clean STOP unaffected"); ++cases;
  begin(); send(v3_frame(2,0,0)); assert_stopped("clean ESTOP unaffected"); ++cases;
  const unsigned bad_before_estop_hold=uno_link.bad_count;
  for(unsigned i=0;i<60;++i) {
    now_ms+=20;send(v3_frame(2,0,0,(uint8_t)(82+i)));tick(0);
    check(uno_link.bad_count==bad_before_estop_hold && uno_link.first_reason==UNO_DIAG_ESTOP,
          "repeated valid ESTOP does not manufacture LINK_TIMEOUT");
  }
  tick(500);
  check(uno_link.bad_count==bad_before_estop_hold && motor_state==IDLE,
        "silence after latched ESTOP cannot create a duplicate timeout fault"); ++cases;
  begin(); bus_v=386; send(v3_frame()); assert_stopped("real production overvoltage guard unchanged"); ++cases;
  begin(); mc_fault=0x400; motor_state=FAULT_NOW; send(v3_frame());
  assert_stopped("real production MCSDK fault stops"); ++cases;
  begin(); tx_succeeds=false; send(v3_frame()); assert_stopped("reply failure still stops"); ++cases;
  reset(true); uv3_init(&candidate,true); test_timer.level_low=true; test_timer.flags=1;
  send(v3_frame(8,0,0));
  check(uno_link.fault_latched && !test_timer.bie && starts==0,"physical sustained break cannot be ACKed"); ++cases;
  reset(); uv3_init(&candidate,true); send(v3_frame());
  check(starts==0 && !uno_link.command_enabled,"zero bus still cannot start"); ++cases;
  begin(); send(v3_frame(),8); send(v3_frame(1,3,10000,82),8);
  assert_stopped("prepare a latched transport error before discharged-bus CLEAR");
  bus_v=0; mc_fault=4; mc_occurred=4; motor_state=FAULT_NOW;
  send(v3_frame(8,0,0,83));
  check(!candidate.fault_latched && !uno_link.fault_latched && starts==1
        && mc_fault==4 && !uno_link.command_enabled,
        "clean CLEAR resets transport without hiding persistent undervoltage or starting");
  send(v3_frame(1,3,10000,84));
  assert_stopped("MCSDK undervoltage still rejects ENABLE after transport CLEAR"); ++cases;
}

#if defined(UV3_INTEGRATED_TEST)
void irq_sample(uint8_t byte, uint8_t marks = 0) {
  uart_registers.RDR = byte;
  uart_registers.ISR = UART_FLAG_RXNE | ((marks & UV3_PE) ? UART_FLAG_PE : 0U)
      | ((marks & UV3_FE) ? UART_FLAG_FE : 0U) | ((marks & UV3_NE) ? UART_FLAG_NE : 0U)
      | ((marks & UV3_ORE) ? UART_FLAG_ORE : 0U);
  USART1_IRQHandler();
  check(uart_registers.ISR == 0, "IRQ read and clear mocked sample flags");
}
void irq_and_fifo() {
  for (unsigned pos=0; pos<UV3_FRAME; ++pos) {
    begin(); auto f=v3_frame();
    for (unsigned i=0; i<f.size(); ++i) irq_sample(f[i], i==pos ? UV3_NE : 0);
    check(uno_rx_errors==0, "NE byte retained without global hard fault");
    uno_link_poll();
    check(candidate.marks[pos]==UV3_NE && candidate.accepted_noise_frames==1
          && motor_state==RUN && starts==1, "IRQ publishes NE beside exact queued byte");
    ++cases;
    for (unsigned marks=1; marks<16; ++marks) {
      if(marks==UV3_NE) continue;
      begin();
      for (unsigned i=0; i<f.size(); ++i) irq_sample(f[i], i==pos ? (uint8_t)marks : 0);
      uno_link_poll(); assert_stopped("hard IRQ invalidates all queued commands");
      check(uno_link.first_uart_errors==marks, "combined UART flags retained in first fault"); ++cases;
    }
  }
  begin(); uart_registers.ISR=UART_FLAG_NE; USART1_IRQHandler(); uno_link_poll();
  assert_stopped("IRQ NE without RDR is never tolerated"); ++cases;
  begin();
  for(unsigned i=0; i<127; ++i) check(uno_rx_push((uint8_t)i, (uint8_t)(i%8)), "ring capacity");
  check(!uno_rx_push(255,4), "ring overflow never overwrites old data");
  for(unsigned i=0; i<127; ++i) {
    uint8_t byte,marks; check(uno_rx_pop(&byte,&marks) && byte==i && marks==i%8,"byte/mark order exact");
  }
  for(unsigned round=0; round<300; ++round) {
    for(unsigned i=0; i<100; ++i) check(uno_rx_push((uint8_t)i,(uint8_t)(i%8)),"wrap push");
    for(unsigned i=0; i<100; ++i) {
      uint8_t byte,marks; check(uno_rx_pop(&byte,&marks) && byte==i && marks==i%8,"wrap byte/mark preserved");
    }
  }
  uno_rx_overflow=1; uno_link_poll(); assert_stopped("overflow stops real handler"); ++cases;
  begin(); send(v3_frame(),8); uno_send_reply();
  check(uv3_crc_ok(reply.data()) && reply[31]==1 && reply[32]==0 && reply[33]==1
        && reply[34]==0 && reply[37]==UV3_NE, "CRC protected accepted-noise telemetry"); ++cases;
  candidate.accepted_noise_frames=UINT32_MAX; candidate.observed_noise_bytes=UINT32_MAX;
  uno_send_reply();
  check(reply[31]==255 && reply[32]==255 && reply[33]==255 && reply[34]==255,
        "diagnostic counters saturate instead of wrapping"); ++cases;
}
#endif

int main() {
  crc_vectors_and_corruption(); noise_matrix(); framing_and_protections();
#if defined(UV3_INTEGRATED_TEST)
  irq_and_fifo();
#endif
  std::printf("{\"pass\":true,\"cases\":%u,\"assertions\":%u,"
              "\"intact_isolated_NE_accepted\":%u,\"strict_baseline_NE_rejected\":%u,"
              "\"hardware_commands\":0}\n", cases,tests,isolated_accepted,strict_rejected);
}
