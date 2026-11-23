#ifndef MIC_MANUAL_SCALAR_CONTROL_H
#define MIC_MANUAL_SCALAR_CONTROL_H
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

/* Scalar-only extension in the previously unused scalar voltage field.
 * Service/brake bytes 14..38 remain zero. CLEAR retains its all-zero payload.
 * Rates are electrical Hz/s * 100, not mechanical rpm/s. */
#define MSC_TAG_COAST 0xC1U
#define MSC_TAG_RAMP 0xC2U
#define MSC_TAG_END 0x5AU
#define MSC_OPERATOR_TIMEOUT_MS 3000U
static inline bool msc_finite(float value) {
  uint32_t bits;memcpy(&bits,&value,sizeof(bits));return (bits&0x7F800000U)!=0x7F800000U;
}
static inline bool msc_rate_valid(uint16_t rate) { return rate >= 10U && rate <= 5000U; }
static inline bool msc_operator_alive(uint32_t now, bool seen, uint32_t last) {
  return seen && (uint32_t)(now-last) < MSC_OPERATOR_TIMEOUT_MS;
}
static inline bool msc_start_allowed(bool manual, uint32_t limit, bool alive) {
  return manual ? alive : limit != 0U;
}
static inline bool msc_wire_present(const uint8_t *f) {
  return f[12] == MSC_TAG_COAST || f[12] == MSC_TAG_RAMP;
}
static inline bool msc_wire_valid(const uint8_t *f) {
  if (!(f[10] | f[11] | f[12] | f[13])) return true;
  return msc_wire_present(f) && f[13] == MSC_TAG_END &&
      msc_rate_valid((uint16_t)(f[10] | ((uint16_t)f[11]<<8)));
}
/* MCSDK accepts a uint16_t duration. Split slow ramps into <=60s segments,
 * rather than silently accelerating a requested slow ramp. Re-evaluate only
 * from the controller's actual reference and only on a fresh validated frame. */
static inline uint16_t msc_segment(int16_t current, int16_t target, uint16_t rate,
                                  uint16_t speed_unit, uint16_t pole_pairs,
                                  int16_t *next) {
  if (!msc_rate_valid(rate) || !speed_unit || !pole_pairs) { *next=current; return 0; }
  int32_t difference=(int32_t)target-current;
  uint32_t delta=(uint32_t)(difference<0 ? -difference : difference);
  const uint32_t segment_ms=difference<0 ? 200U : 60000U;
  uint32_t maximum=(uint32_t)(((uint64_t)segment_ms*rate*speed_unit)/(100000U*pole_pairs));
  if (!maximum) maximum=1U;
  if (delta>maximum) delta=maximum;
  *next=(int16_t)((int32_t)current+(difference<0 ? -(int32_t)delta : (int32_t)delta));
  uint32_t ms=(uint32_t)(((uint64_t)delta*pole_pairs*100000U+rate*speed_unit-1U)/(rate*speed_unit));
  return (uint16_t)(ms>60000U ? 60000U : ms);
}
#endif
