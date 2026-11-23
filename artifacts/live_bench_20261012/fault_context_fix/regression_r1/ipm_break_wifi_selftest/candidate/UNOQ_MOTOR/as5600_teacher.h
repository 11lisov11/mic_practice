#pragma once
#include <stdint.h>

struct As5600Sample {
  uint32_t timestamp_ms = 0;
  uint32_t reads = 0;
  uint32_t errors = 0;
  uint16_t raw = 0;
  uint8_t status = 0;
  int32_t io_error = 0;
  int32_t init_error = 0;
  int32_t scl_level = -1;
  int32_t sda_level = -1;
  bool bus_ok = false;
  bool angle_ok = false;
  bool speed_ok = false;
  float rpm = 0.0f;
};

class As5600Teacher {
 public:
  void update(int32_t error, const uint8_t bytes[3], uint32_t now_ms) {
    sample_.timestamp_ms = now_ms;
    sample_.io_error = error;
    sample_.bus_ok = error == 0;
    sample_.status = error == 0 ? bytes[0] : 0;
    sample_.raw = error == 0 ? ((uint16_t)(bytes[1] & 0x0fU) << 8U) | bytes[2] : 0;
    if (error == 0) increment(sample_.reads);
    else increment(sample_.errors);
    // MD must be set, and neither magnetic-field limit flag may be set.
    sample_.angle_ok = sample_.bus_ok && (sample_.status & 0x38U) == 0x20U
                       && (bytes[1] & 0xf0U) == 0U;
    if (!sample_.angle_ok) {
      reset_speed();
      have_previous_ = false;
      return;
    }
    if (!have_previous_) {
      have_previous_ = true;
      previous_raw_ = sample_.raw;
      previous_ms_ = now_ms;
      reset_speed();
      return;
    }
    const uint32_t dt = now_ms - previous_ms_;
    int32_t delta = (int32_t)sample_.raw - (int32_t)previous_raw_;
    previous_raw_ = sample_.raw;
    previous_ms_ = now_ms;
    if (dt == 0U || dt > 8U || delta == 2048 || delta == -2048) {
      reset_speed();
      return;
    }
    if (delta > 2048) delta -= 4096;
    if (delta < -2048) delta += 4096;
    accumulated_counts_ += delta;
    accumulated_ms_ += dt;
    if (accumulated_ms_ >= 20U) {
      const float instant_rpm = (float)accumulated_counts_ * 60000.0f
                                / (4096.0f * (float)accumulated_ms_);
      sample_.rpm += 0.25f * (instant_rpm - sample_.rpm);
      sample_.speed_ok = true;
      accumulated_counts_ = 0;
      accumulated_ms_ = 0;
    }
  }

  As5600Sample sample() const { return sample_; }

  static As5600Sample fresh(As5600Sample sample, uint32_t now_ms) {
    if (sample.reads == 0U || (uint32_t)(now_ms - sample.timestamp_ms) >= 100U) {
      sample.bus_ok = false;
      sample.angle_ok = false;
      sample.speed_ok = false;
      sample.rpm = 0.0f;
    }
    return sample;
  }

 private:
  static void increment(uint32_t &value) { if (value != UINT32_MAX) ++value; }
  void reset_speed() {
    sample_.speed_ok = false;
    sample_.rpm = 0.0f;
    accumulated_counts_ = 0;
    accumulated_ms_ = 0;
  }
  As5600Sample sample_;
  bool have_previous_ = false;
  uint16_t previous_raw_ = 0;
  uint32_t previous_ms_ = 0;
  int32_t accumulated_counts_ = 0;
  uint32_t accumulated_ms_ = 0;
};

void as5600_teacher_begin();
As5600Sample as5600_teacher_snapshot(uint32_t now_ms);
