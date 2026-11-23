#include "as5600_teacher.h"
#include "as5600_i2c_reader.h"
#include "as5600_poll_reader.h"
#include "as5600_poll_section.h"
#include "as5600_filter_timing.h"
#include <zephyr/drivers/clock_control/stm32_clock_control.h>
#include <zephyr/drivers/clock_control.h>
#include <Arduino.h>
#include <zephyrPinctrl.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <stm32u5xx_ll_i2c.h>
#include <stm32u5xx_ll_gpio.h>

namespace {
K_THREAD_STACK_DEFINE(sensor_stack, 4096);
k_thread sensor_thread;
As5600Sample published;
bool started = false;
uint8_t requested_mode = 5, active_mode = 255;
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

struct PollSchedule {
  static void lock(){k_sched_lock();}
  static void unlock(){k_sched_unlock();}
};
struct PollIo {
  static void claim(){
    LL_I2C_Disable(I2C2);
    (void)LL_I2C_IsEnabled(I2C2); // Explicit PE readback, >=3APB cycles.
    k_busy_wait(2);
    CLEAR_BIT(I2C2->CR1,I2C_CR1_TXIE|I2C_CR1_RXIE|I2C_CR1_TCIE|I2C_CR1_STOPIE|
      I2C_CR1_NACKIE|I2C_CR1_ERRIE|I2C_CR1_TXDMAEN|I2C_CR1_RXDMAEN);
    I2C2->CR2=0;
    I2C2->ICR=I2C_ICR_NACKCF|I2C_ICR_STOPCF|I2C_ICR_BERRCF|I2C_ICR_ARLOCF|I2C_ICR_OVRCF;
    LL_I2C_Enable(I2C2);
  }
  uint32_t now_us(){return micros();}
  uint32_t status(){return I2C2->ISR;}
  uint32_t control(){return I2C2->CR2;}
  uint32_t line_bits(){return (GPIOB->IDR>>10)&3U;}
  bool lines_high(){return (GPIOB->IDR&(3U<<10))==(3U<<10);}
  void wait_step(){k_busy_wait(1);}
  void clear(){I2C2->ICR=I2C_ICR_NACKCF|I2C_ICR_STOPCF|I2C_ICR_BERRCF|I2C_ICR_ARLOCF|I2C_ICR_OVRCF;}
  void clear_berr(){I2C2->ICR=I2C_ICR_BERRCF;}
  void quiesce(){I2C2->CR2=0;}
  void begin_write(){LL_I2C_HandleTransfer(I2C2,0x6c,LL_I2C_ADDRSLAVE_7BIT,1,LL_I2C_MODE_SOFTEND,LL_I2C_GENERATE_START_WRITE);}
  void write_data(uint8_t b){LL_I2C_TransmitData8(I2C2,b);}
  void begin_read(){LL_I2C_HandleTransfer(I2C2,0x6c,LL_I2C_ADDRSLAVE_7BIT,3,LL_I2C_MODE_AUTOEND,LL_I2C_GENERATE_START_READ);}
  uint8_t read_data(){return LL_I2C_ReceiveData8(I2C2);}
  void reset(){claim();}
};
static uint32_t as5600_kernel_clock(){
  // This board's single DT clock entry is PCLK1. Do not infer an HSI/SYSCLK
  // selection from that entry: validate the actual RCC mux first.
  if(READ_BIT(RCC->CCIPR1,RCC_CCIPR1_I2C2SEL)!=0U)return 0;
  const uint32_t bus=DT_CLOCKS_CELL_BY_IDX(DT_NODELABEL(i2c2),0,bus);
  const struct stm32_pclken clock={bus&GENMASK(STM32_CLOCK_DIV_SHIFT-1,0),
      bus>>STM32_CLOCK_DIV_SHIFT,DT_CLOCKS_CELL_BY_IDX(DT_NODELABEL(i2c2),0,bits)};
  uint32_t hz=0;
  int rc=clock_control_get_rate(DEVICE_DT_GET(STM32_CLOCK_CONTROL_NODE),
      (clock_control_subsys_t)&clock,&hz);
  return rc?0:hz;
}


int configure(const device *bus, GpioIo &io, uint8_t mode,
              uint32_t scl_pull, uint32_t sda_pull) {
  if (!device_is_ready(bus) || !device_is_ready(io.gpio)) return -ENODEV;
  // Only this worker owns I2C2; handover happens after the previous transfer.
  LL_I2C_Disable(I2C2);
  if (mode == 0 || mode == 3 || mode == 4 || mode == 5) {
    int rc = zephyr::arduino::init_dev_apply_pinctrl(bus);
    if (rc) return rc;
    LL_I2C_EnableAnalogFilter(I2C2);LL_I2C_SetDigitalFilter(I2C2,0);
    rc=i2c_configure(bus, I2C_MODE_CONTROLLER | I2C_SPEED_SET(I2C_SPEED_STANDARD));
    if(!rc && mode==5){
      const auto timing=encfix::standard_filtered(as5600_kernel_clock());
      if(!timing.valid)return -ERANGE;
      LL_I2C_SetDigitalFilter(I2C2,timing.dnf);LL_I2C_SetTiming(I2C2,timing.word);
    }
    if (!rc && (mode==4||mode==5)) PollIo::claim();
    return rc;
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
  PollIo poll_io;
  encdiag::PollReader<PollIo> poll(poll_io);
  uint32_t resets=0,timeouts=0,nacks=0,last_isr=0;
  uint32_t sections=0,max_hold_us=0,berrs=0,arlos=0,busy=0,cleanups=0,reset_busy=0;
  uint32_t events[4][8]={},event_count=0;
  encdiag::PollResult last_poll;
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
    uint32_t isr=0;
    int error = setup;
    if (setup) { diag.stage = encdiag::SETUP; diag.cause = encdiag::SETUP_ERROR; }
    else if (mode == 4 || mode == 5) {
      const auto result=encdiag::scheduled_read<PollSchedule>(poll,bytes);
      if(sections!=UINT32_MAX)++sections;
      if(result.transfer.duration_us>max_hold_us)max_hold_us=result.transfer.duration_us;
      diag=result.transfer; isr=result.error_isr;
      last_poll=result;
      berrs=UINT32_MAX-berrs<result.berr_events?UINT32_MAX:berrs+result.berr_events;
      if(diag.cause==encdiag::ARBITRATION && arlos!=UINT32_MAX)++arlos;
      if(diag.cause==encdiag::BUS_BUSY && busy!=UINT32_MAX)++busy;
      if(result.graceful_cleanup && cleanups!=UINT32_MAX)++cleanups;
      if(result.controller_reset && (result.post_isr&encdiag::BUSY) && reset_busy!=UINT32_MAX)++reset_busy;
      error=diag.cause==encdiag::NONE ? 0 : -EIO;
      if(result.controller_reset && resets!=UINT32_MAX)++resets;
      if(diag.cause==encdiag::DEADLINE && timeouts!=UINT32_MAX)++timeouts;
      if(diag.cause==encdiag::NACK && nacks!=UINT32_MAX)++nacks;
      if(error)last_isr=isr;
    }
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
    if(!setup&&(mode==4||mode==5)&&(error||last_poll.berr_events)&&event_count<4){
      const bool advisory=!error;uint32_t *e=events[event_count++];e[0]=now;e[1]=mode|(advisory?256U:0U);
      e[2]=diag.stage;e[3]=advisory?8U:diag.cause;e[4]=advisory?last_poll.first_berr_isr:isr;
      e[5]=advisory?last_poll.first_berr_cr2:last_poll.error_cr2;e[6]=advisory?last_poll.first_berr_lines:last_poll.error_lines;e[7]=last_poll.post_isr;
    }
    if (error) {
      last_error_ms = now; last_mode = mode; last_stage = diag.stage;
      last_cause = diag.cause; last_us = diag.duration_us;
      last_cfg_before = cfg_before; last_cfg_after = cfg_after;
      last_tx = diag.tx_byte; last_echo = diag.tx_echo; last_echo_bits = diag.tx_echo_bits;
    }
    sample.diag_sched_sections=sections;sample.diag_sched_max_hold_us=max_hold_us;
    sample.diag_berr_count=berrs;sample.diag_arlo_count=arlos;sample.diag_busy_count=busy;
    sample.diag_graceful_cleanups=cleanups;sample.diag_post_reset_busy=reset_busy;
    sample.diag_kernel_hz=as5600_kernel_clock();sample.diag_timingr=I2C2->TIMINGR;sample.diag_cr1=I2C2->CR1;
    sample.diag_event_count=event_count;for(unsigned e=0;e<event_count;++e)for(unsigned w=0;w<8;++w)sample.diag_events[e][w]=events[e][w];
    sample.diag_isr=isr; sample.diag_last_isr=last_isr;
    sample.diag_controller_resets=resets;sample.diag_timeout_count=timeouts;sample.diag_nack_count=nacks;
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
  if (mode > 5 || !started) return false;
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
