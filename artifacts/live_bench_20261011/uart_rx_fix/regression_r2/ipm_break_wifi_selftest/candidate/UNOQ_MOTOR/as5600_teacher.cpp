#include "as5600_teacher.h"
#include <Arduino.h>
#include <zephyrPinctrl.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>

namespace {
constexpr uint16_t kAddress = 0x36;
constexpr uint8_t kStatusRegister = 0x0b;
constexpr size_t kStackSize = 2048;
K_THREAD_STACK_DEFINE(sensor_stack, kStackSize);
k_thread sensor_thread;
As5600Sample published;
bool started = false;

void publish(const As5600Sample &sample) {
  const unsigned int key = irq_lock();
  published = sample;
  irq_unlock(key);
}

void sensor_worker(void *, void *, void *) {
  // Header I2C2: SCL PB10/D21, SDA PB11/D20; not Qwiic/I2C4.
  const device *bus = DEVICE_DT_GET(DT_NODELABEL(i2c2));
  const device *gpio = DEVICE_DT_GET(DT_NODELABEL(gpiob));
  As5600Teacher tracker;
  int setup_error = zephyr::arduino::init_dev_apply_pinctrl(bus);
  if (setup_error == 0 && !device_is_ready(bus)) setup_error = -ENODEV;
  if (setup_error == 0) {
    setup_error = i2c_configure(bus, I2C_MODE_CONTROLLER | I2C_SPEED_SET(I2C_SPEED_STANDARD));
  }
  for (;;) {
    uint8_t bytes[3] = {};
    const int error = setup_error != 0 ? setup_error
        : i2c_burst_read(bus, kAddress, kStatusRegister, bytes, sizeof(bytes));
    tracker.update(error, bytes, millis());
    As5600Sample sample = tracker.sample();
    sample.init_error = setup_error;
    if (device_is_ready(gpio)) {
      sample.scl_level = gpio_pin_get_raw(gpio, 10);
      sample.sda_level = gpio_pin_get_raw(gpio, 11);
    }
    publish(sample);
    k_msleep(error == 0 ? 2 : 100);
  }
}
}  // namespace

void as5600_teacher_begin() {
  if (started) return;
  started = true;
  // Lowest preemptible priority; I2C waits leave UART/RPC runnable.
  k_thread_create(&sensor_thread, sensor_stack, K_THREAD_STACK_SIZEOF(sensor_stack),
                  sensor_worker, nullptr, nullptr, nullptr,
                  CONFIG_NUM_PREEMPT_PRIORITIES - 1, 0, K_NO_WAIT);
}

As5600Sample as5600_teacher_snapshot(uint32_t now_ms) {
  const unsigned int key = irq_lock();
  As5600Sample sample = published;
  irq_unlock(key);
  return As5600Teacher::fresh(sample, now_ms);
}
