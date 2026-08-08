#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "motor_bench_policy.h"
#include "motor_pwm_math.h"
#include "proto.h"

int main(void) {
  const uint32_t arr = motor_pwm_center_aligned_arr(170000000U, 10000U);
  assert(arr == 8499U);
  assert(motor_pwm_q15_to_compare(16384U, arr) == 4250U);

  const uint32_t requested_ticks = 340U;
  const uint8_t encoded = motor_pwm_encode_deadtime_ticks(requested_ticks);
  const uint32_t effective_ticks = motor_pwm_decode_deadtime_ticks(encoded);
  assert(effective_ticks >= requested_ticks);
  assert(effective_ticks == 344U);
  assert(motor_pwm_decode_deadtime_ticks(motor_pwm_encode_deadtime_ticks(0U)) == 0U);
  assert(motor_pwm_decode_deadtime_ticks(motor_pwm_encode_deadtime_ticks(127U)) == 127U);
  assert(motor_pwm_decode_deadtime_ticks(motor_pwm_encode_deadtime_ticks(128U)) >= 128U);
  assert(motor_pwm_decode_deadtime_ticks(motor_pwm_encode_deadtime_ticks(1008U)) == 1008U);

  uint8_t command[FRAME_LEN] = {};
  command[CMD_OFF_FLAGS] = FLAG_ENABLE | FLAG_DIAG_PWM;
  command[CMD_OFF_MODE] = MODE_DIAG;
  assert(motor_bench_command_allowed(command, true));
  assert(!motor_bench_command_allowed(command, false));
  assert(!motor_bench_command_allowed(nullptr, true));

  command[CMD_OFF_MODE] = MODE_SCALAR;
  assert(!motor_bench_command_allowed(command, true));
  command[CMD_OFF_MODE] = MODE_FOC;
  assert(!motor_bench_command_allowed(command, true));
  command[CMD_OFF_MODE] = MODE_DIAG;
  command[CMD_OFF_FLAGS] |= FLAG_VECTOR_ROTATE;
  assert(!motor_bench_command_allowed(command, true));
  command[CMD_OFF_FLAGS] = FLAG_ENABLE | FLAG_DIAG_PWM;
  command[CMD_OFF_EXT_FLAGS] = EXT_PRECHARGE_RELAY;
  assert(!motor_bench_command_allowed(command, true));

  puts("NUCLEO_PWM_MATH_SELFTEST PASS");
  return 0;
}
