#pragma once
#include <Arduino.h>
#include <zephyrSerial.h>
#include <zephyr/drivers/uart.h>
#include "bounded_rx.h"

// Same physical UART and unchanged vendor TX; only RX storage/observability differ.
class NucleoBufferedSerial : public arduino::ZephyrSerial {
 public:
  struct Stats { uint32_t dropped, errors, error_flags, high_water, pending; };
  explicit NucleoBufferedSerial(const device *dev) : ZephyrSerial(dev) {}
  void begin(unsigned long baud) {
    ZephyrSerial::begin(baud);
    const unsigned key = irq_lock();
    uart_irq_callback_user_data_set(uart, dispatch, this);
    uart_irq_err_enable(uart);
    irq_unlock(key);
  }
  int available() override {
    const unsigned key = irq_lock();
    const int value = queue.count;
    irq_unlock(key); return value;
  }
  int read() override { return read_byte(true); }
  int peek() override { return read_byte(false); }
  Stats stats() {
    const unsigned key = irq_lock();
    const Stats value{queue.dropped, errors, error_flags, queue.high_water, queue.count};
    irq_unlock(key); return value;
  }
 private:
  BoundedRx<1024> queue;
  uint32_t errors = 0, error_flags = 0;
  int read_byte(bool consume) {
    const unsigned key = irq_lock();
    const int value = queue.read(consume);
    irq_unlock(key); return value;
  }
  static void dispatch(const device *, void *arg) {
    static_cast<NucleoBufferedSerial *>(arg)->receive_irq();
  }
  void receive_irq() {
    if (!uart_irq_update(uart)) return;
    const int flags = uart_err_check(uart);
    if (flags > 0) {
      if (errors != UINT32_MAX) ++errors;
      error_flags |= static_cast<uint32_t>(flags);
    }
    uint8_t bytes[8]; int length;
    while (uart_irq_rx_ready(uart) && (length = uart_fifo_read(uart, bytes, sizeof(bytes))) > 0)
      for (int i = 0; i < length; ++i) queue.put(bytes[i]);
    // RX FIFO is drained; let the existing core handle its TX queue.
    ZephyrSerial::IrqHandler();
  }
};
