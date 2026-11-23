#ifndef AIR56_LSO_START_RECORD_H
#define AIR56_LSO_START_RECORD_H

#include <stdint.h>

enum {
  AIR56_START_RECORD_MAGIC = 0x3154534CU, /* LST1 */
  AIR56_START_CHECK_SEEN = 1U,
  AIR56_START_RUN_ENTERED = 2U
};

typedef struct {
  uint32_t magic, start_ms, first_check_ms, run_enter_ms;
  uint16_t checks, in_band;
  int16_t id_min, id_max, id_last, iq_last;
  int16_t id_ref, iq_ref, id_low, id_high;
  int16_t speed_ref, speed_target, max_speed_ref, iq_ref_max;
  uint8_t last_streak, max_streak, terminal_state, ramp_command_state;
  uint16_t run_checks;
  uint8_t stages, reserved;
  uint32_t end_ms;
  int16_t last_run_id, last_run_iq;
  uint16_t terminal_faults, stop_reason;
} air56_lso_start_record;

_Static_assert(sizeof(air56_lso_start_record) == 64, "LSO start record must occupy two pages");

#endif
