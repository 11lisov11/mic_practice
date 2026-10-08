
#include <cstdint>
#include <cassert>
#include <cstdio>
#define MC_DP_FAULT 0x400U
#define MC_UNDER_VOLT 4U
#define TIM_BDTR_MOE 0x8000U
struct { struct { uint16_t ConversionFactor; } _Super; } BusVoltageSensor_M1={{500}};
struct Timer { uint32_t BDTR; } timer;
#define TIM1 (&timer)
uint32_t now_ms, observed_v;
uint32_t HAL_GetTick() { return now_ms; }
template<class T> uint16_t VBS_GetAvBusVoltage_V(T *) { return observed_v; }
void LL_TIM_DisableAllOutputs(Timer *p) { p->BDTR &= ~TIM_BDTR_MOE; }

/* UNPOWERED MCSDK FIXTURE ONLY. Never flash this image for a powered drive.
   ADC telemetry stays real; only V/f modulation normalization uses virtual 310 V. */
static volatile uint32_t mic_bench_last_adc_ms;
static volatile uint16_t mic_bench_adc_samples;
static volatile bool mic_bench_interlock_fault;
static volatile uint16_t mic_bench_adc_raw_last;
static volatile uint16_t mic_bench_adc_raw_max;
static volatile uint8_t mic_bench_interlock_reason;
static uint32_t mic_bench_run_started_ms;
static bool mic_bench_run_tracking;

bool mic_logic_bench_bus_ready(void) {
  return !mic_bench_interlock_fault && mic_bench_adc_samples >= 20U &&
         (uint32_t)(HAL_GetTick() - mic_bench_last_adc_ms) <= 20U &&
         VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super) <= 2U;
}

static uint16_t mic_logic_bench_observe_bus(uint16_t raw, uint16_t faults) {
  const uint32_t now = HAL_GetTick();
  if (raw != UINT16_MAX) {
    mic_bench_adc_raw_last = raw;
    if (raw > mic_bench_adc_raw_max) mic_bench_adc_raw_max = raw;
    const uint32_t real_scaled_v = (uint32_t)raw *
        BusVoltageSensor_M1._Super.ConversionFactor;
    mic_bench_last_adc_ms = now;
    if (mic_bench_adc_samples != UINT16_MAX) ++mic_bench_adc_samples;
    if (real_scaled_v > (2UL << 16U)) {
      mic_bench_interlock_fault = true;
      mic_bench_interlock_reason = 1U;
    }
  }
  if (mic_bench_adc_samples >= 20U &&
      (uint32_t)(now - mic_bench_last_adc_ms) > 20U) {
    mic_bench_interlock_fault = true;
    mic_bench_interlock_reason = 2U;
  }
  if ((TIM1->BDTR & TIM_BDTR_MOE) != 0U) {
    if (!mic_bench_run_tracking) {
      mic_bench_run_tracking = true;
      mic_bench_run_started_ms = now;
    } else if ((uint32_t)(now - mic_bench_run_started_ms) >= 15000U) {
      mic_bench_interlock_fault = true;
      mic_bench_interlock_reason = 3U;
    }
  } else {
    mic_bench_run_tracking = false;
  }
  if (mic_bench_interlock_fault) {
    LL_TIM_DisableAllOutputs(TIM1);
    return faults | MC_DP_FAULT;
  }
  if (mic_logic_bench_bus_ready()) {
    /* Undervoltage is expected ONLY in this detached, zero-bus fixture. */
    return faults & (uint16_t)~MC_UNDER_VOLT;
  }
  return faults;
}

void reset() {
 now_ms=observed_v=0; timer.BDTR=0;
 mic_bench_last_adc_ms=mic_bench_adc_samples=0; mic_bench_interlock_fault=false;
 mic_bench_run_started_ms=0; mic_bench_run_tracking=false;
}
void ready() { for(unsigned i=0;i<20;++i) mic_logic_bench_observe_bus(0,4); }
int main() {
 reset(); assert(!mic_logic_bench_bus_ready());
 for(unsigned i=0;i<19;++i) assert(mic_logic_bench_observe_bus(0,4)==4);
 assert(!mic_logic_bench_bus_ready());
 assert(mic_logic_bench_observe_bus(0,4)==0 && mic_logic_bench_bus_ready());
 assert(mic_logic_bench_observe_bus(0,0x416)==0x412); // DP, OV and temperature retained
 reset(); ready(); now_ms=20;
 assert(mic_logic_bench_observe_bus(UINT16_MAX,4)==0);
 now_ms=21; timer.BDTR=TIM_BDTR_MOE;
 assert(mic_logic_bench_observe_bus(UINT16_MAX,4)&MC_DP_FAULT);
 assert(!timer.BDTR && !mic_logic_bench_bus_ready());
 assert(mic_logic_bench_observe_bus(0,4)&MC_DP_FAULT); // no automatic restart
 for(unsigned raw=0;raw<1000;++raw) {
  reset(); ready(); timer.BDTR=TIM_BDTR_MOE;
  const bool unsafe=raw*500U>(2U<<16U);
  uint16_t fault=mic_logic_bench_observe_bus((uint16_t)raw,4);
  assert(bool(fault&MC_DP_FAULT)==unsafe);
  assert(bool(timer.BDTR)==!unsafe);
 }
 reset(); ready(); observed_v=3; assert(!mic_logic_bench_bus_ready());
 reset(); ready(); timer.BDTR=TIM_BDTR_MOE;
 mic_logic_bench_observe_bus(0,0);
 now_ms=14999; assert(mic_logic_bench_observe_bus(0,0)==0);
 now_ms=15000; assert(mic_logic_bench_observe_bus(0,0)&MC_DP_FAULT);
 assert(!timer.BDTR);
 reset(); ready(); now_ms=UINT32_MAX-10;
 mic_logic_bench_observe_bus(0,0); now_ms+=20;
 assert(mic_logic_bench_observe_bus(UINT16_MAX,4)==0);
 ++now_ms; assert(mic_logic_bench_observe_bus(UINT16_MAX,4)&MC_DP_FAULT);
 reset(); ready(); now_ms=UINT32_MAX-100; timer.BDTR=TIM_BDTR_MOE;
 mic_logic_bench_observe_bus(0,0); now_ms+=15000;
 assert(mic_logic_bench_observe_bus(0,0)&MC_DP_FAULT);
 std::puts("fixture boundaries, 1000 raw ADC values, stale ADC, duration and uint32 wrap passed");
}
