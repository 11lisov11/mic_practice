
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
   ADC telemetry stays real; only V/f modulation normalization uses virtual 310 V.
   Operator-measured bus must be <2 V. Use the same filtered voltage as MCSDK;
   an unpowered board's raw ADC pickup is not an independent voltage sensor. */
static volatile uint32_t mic_bench_last_adc_ms;
static volatile uint16_t mic_bench_adc_samples;
static volatile bool mic_bench_interlock_fault;
static volatile uint16_t mic_bench_adc_raw_last;
static volatile uint16_t mic_bench_adc_raw_max;
static volatile uint8_t mic_bench_interlock_reason;
static volatile bool mic_bench_zero_observed;
static uint16_t mic_bench_raw_window[32];
static uint8_t mic_bench_raw_index;
static volatile uint32_t mic_bench_raw_sum;
static uint32_t mic_bench_run_started_ms;
static bool mic_bench_run_tracking;

bool mic_logic_bench_bus_ready(void) {
  /* Read the ISR timestamp before the clock to avoid a preemption-age wrap. */
  const uint32_t last_adc = mic_bench_last_adc_ms;
  const uint32_t now = HAL_GetTick();
  return !mic_bench_interlock_fault && mic_bench_zero_observed &&
         mic_bench_adc_samples >= 32U &&
         (uint32_t)(now - last_adc) <= 20U &&
         VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super) <= 2U;
}

static uint16_t mic_logic_bench_observe_bus(uint16_t raw, uint16_t faults) {
  const uint32_t now = HAL_GetTick();
  if (raw != UINT16_MAX) {
    mic_bench_adc_raw_last = raw;
    if (raw > mic_bench_adc_raw_max) mic_bench_adc_raw_max = raw;
    mic_bench_last_adc_ms = now;
    if (mic_bench_adc_samples != UINT16_MAX) ++mic_bench_adc_samples;
    mic_bench_raw_sum -= mic_bench_raw_window[mic_bench_raw_index];
    mic_bench_raw_window[mic_bench_raw_index] = raw;
    mic_bench_raw_sum += raw;
    mic_bench_raw_index = (mic_bench_raw_index + 1U) & 31U;
    const uint16_t filtered_v = VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super);
    if (mic_bench_adc_samples >= 32U && filtered_v <= 2U) {
      mic_bench_zero_observed = true;
    }
    /* RVBS_Init seeds its filter near nominal. Wait for a measured zero
       before using a later nonzero filtered voltage as a latched interlock. */
    if (mic_bench_zero_observed && filtered_v > 2U) {
      mic_bench_interlock_fault = true;
      mic_bench_interlock_reason = 1U;
    }
  }
  if (mic_bench_adc_samples >= 32U &&
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
 mic_bench_raw_index=0; mic_bench_raw_sum=0; mic_bench_zero_observed=false;
 for(auto &sample : mic_bench_raw_window) sample=0;
 mic_bench_run_started_ms=0; mic_bench_run_tracking=false;
}
void ready() { for(unsigned i=0;i<32;++i) mic_logic_bench_observe_bus(0,4); }
int main() {
 reset(); assert(!mic_logic_bench_bus_ready());
 for(unsigned i=0;i<31;++i) assert(mic_logic_bench_observe_bus(0,4)==4);
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
  uint16_t fault=mic_logic_bench_observe_bus((uint16_t)raw,4);
  assert(fault==0 && timer.BDTR); // raw pickup is recorded, never relabelled as a voltage
 }
 for(unsigned voltage=0;voltage<=450;++voltage) {
  reset(); ready(); timer.BDTR=TIM_BDTR_MOE; observed_v=voltage;
  uint16_t fault=mic_logic_bench_observe_bus(0,4);
  assert(bool(fault&MC_DP_FAULT)==(voltage>2));
  assert(bool(timer.BDTR)==(voltage<=2));
 }
 reset(); ready(); observed_v=3; assert(!mic_logic_bench_bus_ready());
 // MCSDK RVBS_Init seeds the filtered voltage near nominal before any ADC sample.
 reset(); observed_v=295;
 for(unsigned n=0;n<1000;++n) assert(!(mic_logic_bench_observe_bus(0,4)&MC_DP_FAULT));
 assert(!mic_logic_bench_bus_ready() && !mic_bench_interlock_fault);
 observed_v=0; assert(mic_logic_bench_observe_bus(0,4)==0 && mic_logic_bench_bus_ready());
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
 std::puts("fixture boundaries, 1000 diagnostic raw values, 451 filtered voltages, stale ADC and uint32 wrap passed");
}
