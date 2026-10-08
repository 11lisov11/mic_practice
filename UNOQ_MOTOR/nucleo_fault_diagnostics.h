#pragma once
#include <stdint.h>

struct NucleoFaultDiagnostics {
  bool valid = false;
  uint8_t reason = 0;
  uint8_t uart_errors = 0;
  uint8_t motor_state = 0;
  uint16_t current_faults = 0;
  uint16_t occurred_faults = 0;
  uint8_t sequence = 0;
  uint8_t tx_status = 0;
  bool last_bad_valid = false;
  uint8_t last_bad_reason = 0;
  uint8_t last_uart_errors = 0;
  uint8_t last_tx_status = 0;
};

inline NucleoFaultDiagnostics decode_nucleo_fault_diagnostics(
    const uint8_t *reply, bool mcsdk, uint32_t build) {
  NucleoFaultDiagnostics d;
  // Caller has already checked the complete 32-byte frame CRC and sequence.
  const bool extended = build == 2026100703U || build == 2026100704U || build == 2026100705U ||
      build == 2026100707U || build == 2026100708U || build == 2026100710U ||
      build == 2026100801U || build == 2026100899U;
  if (!reply || !mcsdk || (reply[11] & 0x0fU) > (extended ? 14U : 13U)) return d;
  const bool v1 = build == 2026100701U && (reply[11] & 0xf0U) == 0x80U;
  const bool v2 = (build == 2026100702U || extended) && (reply[11] & 0xf0U) == 0x90U;
  if (!v1 && !v2) return d;
  d.valid = true;
  d.reason = reply[11] & 0x0fU;
  d.uart_errors = v2 ? (reply[12] & 0x0fU) : reply[12];
  d.motor_state = v2 ? (reply[13] & 0x1fU) : reply[13];
  d.current_faults = (uint16_t)reply[15] | ((uint16_t)reply[16] << 8U);
  d.occurred_faults = (uint16_t)reply[27] | ((uint16_t)reply[28] << 8U);
  d.sequence = reply[30];
  d.tx_status = v2 ? (reply[22] & 0x0fU) : reply[22];
  d.last_bad_valid = v2;
  if (v2) {
    d.last_bad_reason = reply[22] >> 4U;
    d.last_uart_errors = reply[12] >> 4U;
    d.last_tx_status = (reply[13] >> 5U) & 0x03U;
  }
  return d;
}
