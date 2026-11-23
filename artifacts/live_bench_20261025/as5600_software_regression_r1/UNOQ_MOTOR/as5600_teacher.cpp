#include "as5600_teacher.h"
#include "as5600_i2c_reader.h"
#include <Arduino.h>
#include <zephyrPinctrl.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <stm32u5xx_ll_i2c.h>
#include <stm32u5xx_ll_gpio.h>

namespace {
K_THREAD_STACK_DEFINE(sensor_stack, 2048);
k_thread sensor_thread;
As5600Sample published;
bool started = false;
uint8_t requested_mode = 0, active_mode = 255;
bool switching = true;

uint32_t pin_config() {
  // Only PB10/PB11; unrelated GPIOB pins are excluded from comparisons.
  return ((GPIOB->MODER >> 20) & 15U) |
         (((GPIOB->OTYPER >> 10) & 3U) << 4) |
         (((GPIOB->PUPDR >> 20) & 15U) << 6) |
         (((GPIOB->OSPEEDR >> 20) & 15U) << 10) |
         (((GPIOB->AFR[1] >> 8) & 255U) << 14);
}

struct GpioIo {
  const device *gpio;
  int scl(bool release) { return gpio_pin_set_raw(gpio, 10, release); }
  int sda(bool release) { return gpio_pin_set_raw(gpio, 11, release); }
  int read_scl() { return gpio_pin_get_raw(gpio, 10); }
  int read_sda() { return gpio_pin_get_raw(gpio, 11); }
  uint32_t now_us() { return micros(); }
  void delay_us(uint32_t us) { k_busy_wait(us); }
};

int configure(const device *bus, GpioIo &io, uint8_t mode,
              uint32_t scl_pull, uint32_t sda_pull) {
  if (!device_is_ready(bus) || !device_is_ready(io.gpio)) return -ENODEV;
  // Only this worker owns I2C2; handover happens after the previous transfer.
  LL_I2C_Disable(I2C2);
  if (mode == 0 || mode == 3) {
    int rc = zephyr::arduino::init_dev_apply_pinctrl(bus);
    if (rc) return rc;
    return i2c_configure(bus, I2C_MODE_CONTROLLER | I2C_SPEED_SET(I2C_SPEED_STANDARD));
  }
  auto flags = [](uint32_t pull) -> gpio_flags_t {
    // Preserve pulls from native pinctrl: do not improve the bus covertly.
    return GPIO_INPUT | GPIO_OUTPUT_HIGH | GPIO_OPEN_DRAIN |
      (pull == LL_GPIO_PULL_UP ? GPIO_PULL_UP :
       pull == LL_GPIO_PULL_DOWN ? GPIO_PULL_DOWN : 0);
  };
  int rc = gpio_pin_configure(io.gpio, 10, flags(scl_pull));
  if (!rc) rc = gpio_pin_configure(io.gpio, 11, flags(sda_pull));
  return rc;
}

void sensor_worker(void *, void *, void *) {
  const device *bus = DEVICE_DT_GET(DT_NODELABEL(i2c2));
  GpioIo io{DEVICE_DT_GET(DT_NODELABEL(gpiob))};
  int setup = zephyr::arduino::init_dev_apply_pinctrl(bus);
  const uint32_t scl_pull = LL_GPIO_GetPinPull(GPIOB, LL_GPIO_PIN_10);
  const uint32_t sda_pull = LL_GPIO_GetPinPull(GPIOB, LL_GPIO_PIN_11);
  As5600Teacher tracker;
  encdiag::Reader<GpioIo> reader(io);
  uint32_t epoch = 0, first_error_ms = 0, first_stage = 0, first_cause = 0;
  uint32_t first_duration = 0;
  uint32_t last_error_ms = 0, last_mode = 0, last_stage = 0, last_cause = 0, last_us = 0;
  uint32_t expected_cfg = 0, last_cfg_before = 0, last_cfg_after = 0;
  uint32_t last_tx = 0, last_echo = 0, last_echo_bits = 0;
  for (;;) {
    unsigned key = irq_lock();
    const uint8_t mode = requested_mode;
    const bool change = active_mode != mode;
    irq_unlock(key);
    if (change) {
      if (!setup || epoch != 0) setup = configure(bus, io, mode, scl_pull, sda_pull);
      // LEGACY restores the original worker priority without changing motor,
      // UART, RPC or IRQ priorities. Other modes keep installed priority 4.
      k_thread_priority_set(&sensor_thread,
          mode == 3 ? CONFIG_NUM_PREEMPT_PRIORITIES - 1 : 4);
      expected_cfg = pin_config();
      // Reset speed history, never the lifetime read/error counters.
      const auto old = tracker.sample();
      tracker = As5600Teacher{};
      tracker.seed_counters(old.reads, old.errors);
      ++epoch;
    }
    uint8_t bytes[3] = {};
    encdiag::Result diag;
    const uint32_t cfg_before = pin_config();
    int error = setup;
    if (setup) { diag.stage = encdiag::SETUP; diag.cause = encdiag::SETUP_ERROR; }
    else if (mode == 0 || mode == 3) {
      const uint32_t begin = micros();
      error = i2c_burst_read(bus, 0x36, 0x0b, bytes, sizeof(bytes));
      diag.duration_us = micros() - begin;
      // Zephyr may clear ISR before return: never label generic EIO as NACK.
      if (error) { diag.stage = encdiag::HW_TRANSFER; diag.cause = encdiag::GENERIC_DRIVER; }
    } else {
      diag = reader.read(bytes, mode == 1 ? 5U : 20U);
      error = diag.cause == encdiag::NONE ? 0 : -EIO;
    }
    const uint32_t cfg_after = pin_config();
    const uint32_t now = millis();
    tracker.update(error, bytes, now);
    As5600Sample sample = tracker.sample();
    sample.init_error = setup;
    sample.scl_level = device_is_ready(io.gpio) ? io.read_scl() : -1;
    sample.sda_level = device_is_ready(io.gpio) ? io.read_sda() : -1;
    if (error && first_cause == 0) {
      first_error_ms = now; first_stage = diag.stage; first_cause = diag.cause;
      first_duration = diag.duration_us;
    }
    if (error) {
      last_error_ms = now; last_mode = mode; last_stage = diag.stage;
      last_cause = diag.cause; last_us = diag.duration_us;
      last_cfg_before = cfg_before; last_cfg_after = cfg_after;
      last_tx = diag.tx_byte; last_echo = diag.tx_echo; last_echo_bits = diag.tx_echo_bits;
    }
    sample.diag_mode = mode; sample.diag_epoch = epoch;
    sample.diag_stage = diag.stage; sample.diag_cause = diag.cause;
    sample.diag_us = diag.duration_us; sample.diag_wait_us = diag.max_clock_wait_us;
    sample.diag_first_ms = first_error_ms; sample.diag_first_stage = first_stage;
    sample.diag_first_cause = first_cause; sample.diag_first_us = first_duration;
    sample.diag_last_ms = last_error_ms; sample.diag_last_mode = last_mode;
    sample.diag_last_stage = last_stage; sample.diag_last_cause = last_cause;
    sample.diag_last_us = last_us;
    sample.diag_thread_priority = k_thread_priority_get(&sensor_thread);
    sample.diag_cfg_expected = expected_cfg;
    sample.diag_cfg_before = cfg_before; sample.diag_cfg_after = cfg_after;
    sample.diag_cfg_match = (cfg_before == expected_cfg && cfg_after == expected_cfg);
    sample.diag_last_cfg_before = last_cfg_before;
    sample.diag_last_cfg_after = last_cfg_after;
    sample.diag_tx_byte = diag.tx_byte; sample.diag_tx_echo = diag.tx_echo;
    sample.diag_tx_bits = diag.tx_echo_bits;
    sample.diag_last_tx_byte = last_tx; sample.diag_last_tx_echo = last_echo;
    sample.diag_last_tx_bits = last_echo_bits;
    key = irq_lock();
    published = sample; active_mode = mode;
    switching = requested_mode != active_mode;
    irq_unlock(key);
    k_msleep(error == 0 ? 2 : 100);
  }
}
}  // namespace

void as5600_teacher_begin() {
  if (started) return;
  started = true;
  k_thread_create(&sensor_thread, sensor_stack, K_THREAD_STACK_SIZEOF(sensor_stack),
                  sensor_worker, nullptr, nullptr, nullptr, 4, 0, K_NO_WAIT);
}
As5600Sample as5600_teacher_snapshot(uint32_t now_ms) {
  const unsigned key = irq_lock();
  As5600Sample sample = published;
  irq_unlock(key);
  return As5600Teacher::fresh(sample, now_ms);
}
bool as5600_diag_select(uint8_t mode) {
  if (mode > 3 || !started) return false;
  const unsigned key = irq_lock();
  if (switching) { irq_unlock(key); return false; }
  requested_mode = mode; switching = requested_mode != active_mode;
  irq_unlock(key);
  return true;
}
bool as5600_diag_ready() {
  const unsigned key = irq_lock();
  // A failed sensor must not become a scalar-drive interlock. Only serialize
  // pin handover with START; sensor validity remains observational.
  const bool ready = started && !switching;
  irq_unlock(key);
  return ready;
}
