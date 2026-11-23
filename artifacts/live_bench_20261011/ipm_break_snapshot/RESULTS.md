# First-break diagnostics: preparation and verification

## Result

- Isolated Nucleo diagnostic candidate 2026101101 prepared and built.
- Final candidate: `candidate_r2`; r1 is superseded and must not be installed.
- Target compile/link: 0 errors, 0 warnings. Initial clean-on-empty-directory
  messages are retained in the build log; they are not hidden.
- Final BIN: 43548 bytes, SHA256
  `c2916541f70a4a2948e5cd7bace3774be52bbe22ef93920434da110043d3f547`.
- Relative to frozen 2026101006: +536 bytes flash, +264 bytes RAM.
- Full offline regression: **46/46 suites PASS**, source hashes unchanged
  during testing. Recorder suite: **32 checks PASS** (included, not additive).
- ELF-based package verification passes; both 92-byte record addresses and
  artifact hashes are verified against the actual build.
- No MCU flashing, ARM, START, CLEAR, or powered trial performed in this work.

## What Changed

The break ISR captures timer flags/settings and PA6 input before the existing
handler clears flags or masks the IRQ. A first-event record and a separate
first-START-window record distinguish startup events from a later run attempt.
STOP and CLEAR do not erase these records. Double-buffered cached context
includes native reference speed, MCSDK state/masks, bus voltage, temperature
and command sequence. Context age and uncertainty are explicit in the decoder.

The frozen baseline sources, protection thresholds, hardware BKE, DP handling,
UART packet layout/CRC/noise policy and watchdogs remain unchanged. Candidate
identity is deliberately not approved by the current powered-trial gate.

## Passive Connected-Bench Check

GET-only Wi-Fi collection at `http://192.168.1.138:8080` requested 10 seconds:

- Eight status samples; no HTTP errors; logs downloaded.
- Installed images still Uno Q 2026101008 and Nucleo 2026101006.
- UART good count 18783 -> 18936: **153 new correct messages**.
- Bad/integrity/sequence counts zero, no new errors; superseded stayed at 1.
- SAFE, outputs off, no HV arm; reported bus remained within the 2-V check.

This checks communication and idle telemetry, not an active PWM waveform or
the physical cause of MC_DP.

## Not Solved Yet

The previous powered trial stopped at about 5.516 seconds with MC_DP mask
0x0400, not a 30-/33-second timeout. The operator observed rotation/coast;
50 Hz and a completed 30-second run remain unconfirmed. The new recorder
cannot recover that past event: the installed image did not contain it.

Detailed snapshot delivery over Wi-Fi is not implemented. It requires a
versioned paired UART/Uno/HMI diagnostic extension; normal reply fields must
not be silently repurposed. Low-voltage physical capture and ISR timing also
remain unqualified. Record readback through PC-connected ST-Link is only for
a deenergized, discharged setup, and reset/power loss erases RAM records.

No conclusion that the IPM itself, J4 supply, or SD wiring is defective is
justified yet. Do not weaken protection or repeat a powered run solely on
the basis of passing host tests.

## Evidence

- `full_regression_r2/report.json`
- `full_regression_r2/ipm_break_snapshot_selftest/report.json`
- `candidate_r2/package.json`
- `candidate_r2/manifest.json`
- `candidate_r2/nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json`
- `passive_wifi_r1/summary.json`, `status.jsonl`, `logs.txt`
- Design and readback limitations: `docs/ipm_first_break_snapshot.md` in the
  repository root.
