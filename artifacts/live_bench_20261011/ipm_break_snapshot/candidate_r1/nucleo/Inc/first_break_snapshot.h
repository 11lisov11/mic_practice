#ifndef MIC_FIRST_BREAK_SNAPSHOT_H
#define MIC_FIRST_BREAK_SNAPSHOT_H

#include <stdint.h>

#define MIC_BREAK_MAGIC 0x314B5242UL
#define MIC_BREAK_SCHEMA 1UL

/* The inactive bank is written by the main loop; the IRQ never waits on it. */
typedef struct {
  uint32_t tick_ms;
  int32_t reference_speed_unit;
  uint32_t motor_state;
  uint32_t current_faults;
  uint32_t occurred_faults;
  uint32_t vbus_v;
  int32_t temperature_deci_c;
  uint32_t command_sequence;
} mic_break_context_t;

typedef struct {
  uint32_t magic;
  uint32_t schema;
  uint32_t bytes;
  uint32_t tick_ms;
  uint32_t tim_sr;
  uint32_t tim_dier;
  uint32_t tim_bdtr;
  uint32_t tim_cnt;
  uint32_t tim_arr;
  uint32_t tim_ccr1;
  uint32_t tim_ccr2;
  uint32_t tim_ccr3;
  uint32_t gpioa_idr;
  uint32_t context_valid;
  mic_break_context_t context;
} mic_break_snapshot_t;

extern volatile mic_break_snapshot_t mic_first_break;
extern volatile uint32_t mic_break_irq_count;
extern volatile mic_break_context_t mic_break_context[2];
extern volatile uint32_t mic_break_context_index;
extern volatile uint32_t mic_break_context_valid;

static inline void mic_break_copy_context(volatile mic_break_context_t *to,
                                         const volatile mic_break_context_t *from) {
  to->tick_ms = from->tick_ms;
  to->reference_speed_unit = from->reference_speed_unit;
  to->motor_state = from->motor_state;
  to->current_faults = from->current_faults;
  to->occurred_faults = from->occurred_faults;
  to->vbus_v = from->vbus_v;
  to->temperature_deci_c = from->temperature_deci_c;
  to->command_sequence = from->command_sequence;
}

static inline void mic_break_publish_context(const mic_break_context_t *value) {
  const uint32_t bank = mic_break_context_index ^ 1U;
  mic_break_copy_context(&mic_break_context[bank], value);
  __DMB();
  mic_break_context_index = bank;
  mic_break_context_valid = 1U;
}

/* BKE has already disabled outputs in hardware. No HAL/MCSDK calls or UART
   writes here. This must run before clearing BIF/B2IF or changing DIER. */
static inline void mic_break_capture_first(uint32_t tick_ms) {
  const uint32_t sr = TIM1->SR;
  if ((sr & (TIM_SR_BIF | TIM_SR_B2IF)) == 0U) return;
  if (mic_break_irq_count != UINT32_MAX) ++mic_break_irq_count;
  if (mic_first_break.magic == MIC_BREAK_MAGIC) return;
  mic_first_break.schema = MIC_BREAK_SCHEMA;
  mic_first_break.bytes = sizeof(mic_break_snapshot_t);
  mic_first_break.tick_ms = tick_ms;
  mic_first_break.tim_sr = sr;
  mic_first_break.tim_dier = TIM1->DIER;
  mic_first_break.tim_bdtr = TIM1->BDTR;
  mic_first_break.tim_cnt = TIM1->CNT;
  mic_first_break.tim_arr = TIM1->ARR;
  mic_first_break.tim_ccr1 = TIM1->CCR1;
  mic_first_break.tim_ccr2 = TIM1->CCR2;
  mic_first_break.tim_ccr3 = TIM1->CCR3;
  mic_first_break.gpioa_idr = GPIOA->IDR;
  const uint32_t valid = mic_break_context_valid;
  const uint32_t bank = mic_break_context_index;
  __DMB();
  mic_first_break.context_valid = valid;
  if (valid != 0U) mic_break_copy_context(&mic_first_break.context, &mic_break_context[bank]);
  __DMB();
  mic_first_break.magic = MIC_BREAK_MAGIC;
}

/* First event deliberately survives CLEAR/STOP. Only a reboot erases it. */
#endif
