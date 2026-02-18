#pragma once

#include <stdint.h>

typedef struct {
  uint8_t enable_ai;
  uint8_t gated;
  int16_t id_ref_q10;
} unoq_gate_result_t;

static inline int16_t unoq_rate_limit(int16_t prev, int16_t target, int16_t step) {
  if (step < 1) step = 1;
  if (target > prev) {
    int32_t next = (int32_t)prev + step;
    if (next > target) next = target;
    return (int16_t)next;
  }
  if (target < prev) {
    int32_t next = (int32_t)prev - step;
    if (next < target) next = target;
    return (int16_t)next;
  }
  return target;
}

static inline unoq_gate_result_t unoq_apply_gates(
    int16_t speed_err_q10,
    int16_t speed_tol_q10,
    uint16_t status_flags,
    uint16_t link_flags,
    int16_t id_ref_base_q10,
    int16_t id_ref_cmd_q10,
    uint8_t enable_ai_req,
    uint8_t allow_flux_reduction) {
  unoq_gate_result_t out;
  out.enable_ai = 0u;
  out.gated = 1u;
  out.id_ref_q10 = id_ref_base_q10;

  if (enable_ai_req == 0u) {
    return out;
  }

  int16_t tol = speed_tol_q10;
  if (tol < 0) tol = (int16_t)(-tol);
  int16_t err = speed_err_q10;
  if (err < 0) err = (int16_t)(-err);

  if (status_flags != 0u || link_flags != 0u) {
    return out;
  }
  if (err > tol) {
    return out;
  }

  out.enable_ai = 1u;
  out.gated = 0u;
  if (allow_flux_reduction != 0u) {
    out.id_ref_q10 = id_ref_cmd_q10;
  } else {
    out.id_ref_q10 = (id_ref_cmd_q10 > id_ref_base_q10) ? id_ref_cmd_q10 : id_ref_base_q10;
  }
  return out;
}
