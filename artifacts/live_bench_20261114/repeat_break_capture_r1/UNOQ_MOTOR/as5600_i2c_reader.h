#pragma once
#include <stdint.h>

// Fixed, read-only AS5600 transaction. GPIO adapter must use open drain:
// true releases a line, false pulls it LOW. No IRQ masking or bus-clear pulses.
namespace encdiag {
enum Stage : uint8_t {
  OK = 0, SETUP = 1, HW_TRANSFER = 2, BUS_IDLE = 3,
  ADDRESS_WRITE = 4, REGISTER = 5, RESTART = 6, ADDRESS_READ = 7,
  DATA0 = 8, DATA1 = 9, DATA2 = 10, STOP = 11
};
enum Cause : uint8_t {
  NONE = 0, GENERIC_DRIVER = 1, NACK = 2, SCL_TIMEOUT = 3,
  SDA_STUCK = 4, GPIO_ERROR = 5, DEADLINE = 6, SETUP_ERROR = 7
};
struct Result {
  Stage stage = OK;
  Cause cause = NONE;
  uint32_t duration_us = 0;
  uint32_t max_clock_wait_us = 0;
  int scl = -1, sda = -1;
  uint8_t tx_byte = 0, tx_echo = 0, tx_echo_bits = 0;
};

// Io: scl/sda(bool)->int, read_scl/read_sda()->int,
// now_us()->uint32, delay_us(uint32). Timeouts use unsigned wrap-safe deltas.
template <class Io> class Reader {
 public:
  explicit Reader(Io &io) : io_(io) {}
  Result read(uint8_t bytes[3], uint32_t half_period_us) {
    r_ = Result{}; begin_ = io_.now_us(); half_ = half_period_us;
    for (unsigned i = 0; i < 3; ++i) bytes[i] = 0;
    if (start(false) && write(0x6c, ADDRESS_WRITE) && write(0x0b, REGISTER)
        && start(true) && write(0x6d, ADDRESS_READ)) {
      for (unsigned i = 0; i < 3 && r_.cause == NONE; ++i)
        read_byte(bytes[i], i != 2, static_cast<Stage>(DATA0 + i));
    }
    // Attempt normal STOP only while we still own a responsive clock.
    // On a stuck bus, release pins; never silently recover/retry the sample.
    if (r_.cause != SCL_TIMEOUT && r_.cause != DEADLINE && r_.cause != GPIO_ERROR
        && r_.cause != SDA_STUCK) stop();
    io_.sda(true); io_.scl(true);
    r_.scl = io_.read_scl(); r_.sda = io_.read_sda();
    r_.duration_us = io_.now_us() - begin_;
    if (r_.cause == NONE) r_.stage = OK;
    return r_;
  }
 private:
  static constexpr uint32_t kStretchUs = 1000, kDeadlineUs = 5000;
  bool fail(Cause c) { if (r_.cause == NONE) r_.cause = c; return false; }
  bool time_ok() {
    return (uint32_t)(io_.now_us() - begin_) < kDeadlineUs || fail(DEADLINE);
  }
  bool pause() { io_.delay_us(half_); return time_ok(); }
  bool scl(bool release) { return io_.scl(release) >= 0 || fail(GPIO_ERROR); }
  bool sda(bool release) { return io_.sda(release) >= 0 || fail(GPIO_ERROR); }
  bool high() {
    if (!scl(true)) return false;
    const uint32_t from = io_.now_us();
    for (;;) {
      const int level = io_.read_scl();
      const uint32_t wait = io_.now_us() - from;
      if (wait > r_.max_clock_wait_us) r_.max_clock_wait_us = wait;
      if (level < 0) return fail(GPIO_ERROR);
      if (!time_ok()) return false;
      if (level) return true;
      if (wait >= kStretchUs) return fail(SCL_TIMEOUT);
      io_.delay_us(1);
    }
  }
  int sample_sda() {
    const int level = io_.read_sda();
    if (level < 0) fail(GPIO_ERROR);
    return level;
  }
  bool start(bool repeated) {
    r_.stage = repeated ? RESTART : BUS_IDLE;
    if (!sda(true) || !pause() || !high() || !pause()) return false;
    const int level = sample_sda();
    if (level < 0) return false;
    if (!level) return fail(SDA_STUCK);
    return sda(false) && pause() && scl(false);
  }
  bool write(uint8_t byte, Stage stage) {
    r_.stage = stage;
    r_.tx_byte = byte; r_.tx_echo = 0; r_.tx_echo_bits = 0;
    for (unsigned bit = 0; bit < 8; ++bit, byte <<= 1) {
      if (!sda((byte & 0x80) != 0) || !pause() || !high() || !pause()) return false;
      // Observe physical IDR while SCL is high. Do not assume that an ODR
      // write reached the pin or that nobody changed the pin mux at START.
      const int echo = sample_sda();
      if (echo < 0) return false;
      r_.tx_echo = static_cast<uint8_t>((r_.tx_echo << 1) | echo);
      ++r_.tx_echo_bits;
      if (!scl(false)) return false;
    }
    if (!sda(true) || !pause() || !high() || !pause()) return false;
    const int ack = sample_sda();
    if (!scl(false) || ack < 0) return false;
    return ack == 0 || fail(NACK);
  }
  bool read_byte(uint8_t &byte, bool ack, Stage stage) {
    r_.stage = stage; byte = 0;
    if (!sda(true)) return false;
    for (unsigned bit = 0; bit < 8; ++bit) {
      if (!pause() || !high() || !pause()) return false;
      const int level = sample_sda();
      if (level < 0 || !scl(false)) return false;
      byte = static_cast<uint8_t>((byte << 1) | level);
    }
    return sda(!ack) && pause() && high() && pause() && scl(false) && sda(true);
  }
  bool stop() {
    const Stage previous = r_.stage;
    if (r_.cause == NONE) r_.stage = STOP;
    if (!scl(false) || !sda(false) || !pause() || !high() || !pause()
        || !sda(true) || !pause()) return false;
    const int level = sample_sda();
    if (level < 0) return false;
    if (!level) return fail(SDA_STUCK);
    if (r_.cause != NONE) r_.stage = previous;
    return true;
  }
  Io &io_; Result r_; uint32_t begin_ = 0, half_ = 5;
};
}  // namespace encdiag
