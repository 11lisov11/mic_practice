#include "../UNOQ_MOTOR/as5600_teacher.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <initializer_list>

static void feed(As5600Teacher &tracker, uint16_t raw, uint32_t ms, uint8_t status = 0x20) {
  const uint8_t bytes[3] = {status, (uint8_t)(raw >> 8), (uint8_t)raw};
  tracker.update(0, bytes, ms);
}

int main() {
  unsigned cases = 0;
  for (unsigned status = 0; status < 256; ++status) {
    for (unsigned raw = 0; raw < 4096; ++raw) {
      As5600Teacher tracker;
      feed(tracker, (uint16_t)raw, 2, (uint8_t)status);
      const auto sample = tracker.sample();
      assert(sample.bus_ok && sample.raw == raw && sample.reads == 1);
      assert(sample.angle_ok == ((status & 0x38) == 0x20));
      assert(!sample.speed_ok && sample.rpm == 0.0f);
      ++cases;
    }
  }
  for (float rpm : {-6000.0f, -2720.0f, -60.0f, 0.0f, 60.0f, 2720.0f, 6000.0f}) {
    As5600Teacher tracker;
    for (uint32_t ms = 2; ms <= 4000; ms += 2) {
      const int64_t counts = (int64_t)std::llround((double)rpm * ms * 4096.0 / 60000.0);
      feed(tracker, (uint16_t)((counts % 4096 + 4096) % 4096), ms);
    }
    auto sample = tracker.sample();
    assert(sample.angle_ok && sample.speed_ok);
    assert(std::fabs(sample.rpm - rpm) < 2.0f);
    assert(As5600Teacher::fresh(sample, 4099).angle_ok);
    assert(!As5600Teacher::fresh(sample, 4100).angle_ok);
    assert(As5600Teacher::fresh(sample, 4100).rpm == 0.0f);
    const uint8_t empty[3] = {};
    tracker.update(-5, empty, 4101);
    sample = tracker.sample();
    assert(!sample.bus_ok && !sample.angle_ok && !sample.speed_ok);
    assert(sample.errors == 1 && sample.io_error == -5 && sample.rpm == 0.0f);
    feed(tracker, 100, 4102);
    assert(tracker.sample().angle_ok && !tracker.sample().speed_ok);
    ++cases;
  }
  As5600Teacher tracker;
  feed(tracker, 4090, UINT32_MAX - 1U);
  feed(tracker, 5, 0);
  assert(tracker.sample().angle_ok);
  assert(As5600Teacher::fresh(tracker.sample(), 99).angle_ok);
  assert(!As5600Teacher::fresh(tracker.sample(), 100).angle_ok);
  feed(tracker, 25, 2);
  feed(tracker, 50, 4);
  feed(tracker, 100, 40);
  assert(!tracker.sample().speed_ok && tracker.sample().rpm == 0.0f);
  feed(tracker, 2148, 42);
  assert(!tracker.sample().speed_ok);
  feed(tracker, 2148, 42);
  assert(!tracker.sample().speed_ok);
  const uint8_t malformed[3] = {0x20, 0xf1, 0x23};
  tracker.update(0, malformed, 44);
  assert(tracker.sample().bus_ok && !tracker.sample().angle_ok);
  As5600Sample never_read;
  never_read.bus_ok = true;
  assert(!As5600Teacher::fresh(never_read, 0).bus_ok);
  cases += 6;
  std::printf("{\"pass\":true,\"cases\":%u}\n", cases);
}
