#include "reader.h"
#include <cassert>
#include <cstdio>
#include <deque>
#include <vector>
using namespace encdiag;

struct FakeIo {
  uint32_t time = 0;
  bool clock = true, data = true;
  bool scl_stuck = false, gpio_error = false;
  bool long_preemption = false;
  unsigned reads = 0;
  std::deque<int> slave;
  std::vector<bool> master_on_rise;
  int scl(bool release) {
    if (gpio_error) return -1;
    if (release && !clock) master_on_rise.push_back(data);
    clock = release; return 0;
  }
  int sda(bool release) { data = release; return gpio_error ? -1 : 0; }
  int read_scl() { ++reads; return scl_stuck ? 0 : 1; }
  int read_sda() {
    if (gpio_error) return -1;
    assert(!slave.empty());
    int v = slave.front(); slave.pop_front(); return v;
  }
  uint32_t now_us() { return time; }
  void delay_us(uint32_t us) { time += us + (long_preemption ? 6000 : 0); }
  void data_byte(unsigned byte) {
    for (int b = 7; b >= 0; --b) slave.push_back((byte >> b) & 1);
  }
  void write_echo(unsigned byte) { data_byte(byte); slave.push_back(0); }
  void good() {
    slave = {1}; write_echo(0x6c); write_echo(0x0b);
    slave.push_back(1); write_echo(0x6d);
    data_byte(0x20); data_byte(0x01); data_byte(0xa5);
    slave.push_back(1); slave.push_back(1); // STOP high and final sample
  }
};

int main() {
  unsigned cases = 0;
  for (unsigned half : {5U, 20U}) for (uint32_t initial : {0U, UINT32_MAX - 100U}) {
    FakeIo io; io.good(); io.time = initial;
    Reader<FakeIo> reader(io); uint8_t bytes[3];
    auto r = reader.read(bytes, half);
    assert(r.cause == NONE && r.stage == OK);
    assert(r.tx_byte == 0x6d && r.tx_echo == 0x6d && r.tx_echo_bits == 8);
    assert(bytes[0] == 0x20 && bytes[1] == 0x01 && bytes[2] == 0xa5);
    assert(r.duration_us < 5000 && io.slave.empty());
    assert(io.clock && io.data);
    assert(io.master_on_rise.size() == 56);
    // Actual wire bits of only two addresses and register; no config writes.
    for (unsigned b = 0; b < 8; ++b) {
      assert(io.master_on_rise[b] == bool((0x6c >> (7 - b)) & 1));
      assert(io.master_on_rise[9 + b] == bool((0x0b >> (7 - b)) & 1));
      assert(io.master_on_rise[19 + b] == bool((0x6d >> (7 - b)) & 1));
    }
    assert(!io.master_on_rise[36] && !io.master_on_rise[45]);
    assert(io.master_on_rise[54]);  // mandatory final master NACK
    ++cases;
  }
  for (unsigned phase : {9U, 18U, 28U}) {
    FakeIo io; io.good(); io.slave[phase] = 1;
    Reader<FakeIo> reader(io); uint8_t bytes[3];
    auto r = reader.read(bytes, 5);
    assert(r.cause == NACK);
    assert(r.stage == (phase == 9 ? ADDRESS_WRITE : phase == 18 ? REGISTER : ADDRESS_READ));
    assert(r.tx_byte == r.tx_echo && r.tx_echo_bits == 8);
    assert(io.clock && io.data);
    ++cases;
  }
  {
    FakeIo io; io.good(); io.slave[0] = 0;
    Reader<FakeIo> reader(io); uint8_t bytes[3];
    auto r = reader.read(bytes, 5);
    assert(r.cause == SDA_STUCK && r.stage == BUS_IDLE);
    assert(io.master_on_rise.empty()); // no covert recovery clocks
    ++cases;
  }
  for (uint32_t start : {0U, UINT32_MAX - 100U}) {
    FakeIo io; io.slave = {1}; io.scl_stuck = true; io.time = start;
    Reader<FakeIo> reader(io); uint8_t bytes[3];
    auto r = reader.read(bytes, 5);
    assert(r.cause == SCL_TIMEOUT && r.stage == BUS_IDLE);
    assert(r.duration_us <= 1010 && r.max_clock_wait_us == 1000);
    ++cases;
  }
  {
    FakeIo io; io.slave = {1}; io.gpio_error = true;
    Reader<FakeIo> reader(io); uint8_t bytes[3];
    auto r = reader.read(bytes, 5);
    assert(r.cause == GPIO_ERROR); ++cases;
  }
  {
    FakeIo io; io.slave = {1}; io.long_preemption = true;
    Reader<FakeIo> reader(io); uint8_t bytes[3];
    auto r = reader.read(bytes, 5);
    assert(r.cause == DEADLINE && io.reads == 1); // final line snapshot only
    assert(io.master_on_rise.empty()); ++cases;
  }
  {
    FakeIo io; io.good(); io.slave[53] = 0;
    Reader<FakeIo> reader(io); uint8_t bytes[3];
    auto r = reader.read(bytes, 5);
    assert(r.cause == SDA_STUCK && r.stage == STOP); ++cases;
  }
  {
    FakeIo io; io.good(); io.slave[3] ^= 1; io.slave[9] = 1;
    Reader<FakeIo> reader(io); uint8_t bytes[3];
    auto r = reader.read(bytes, 5);
    assert(r.cause == NACK && r.stage == ADDRESS_WRITE);
    assert(r.tx_byte == 0x6c && r.tx_echo == (0x6c ^ 0x20) && r.tx_echo_bits == 8);
    ++cases;
  }
  std::printf("PASS: %u cases, wire bytes, ACK/NACK, bus faults, deadlines, wrap\n", cases);
}
