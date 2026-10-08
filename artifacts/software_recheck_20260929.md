# Software and logic-only recheck, 2026-09-29

Scope: UNO Q + NUCLEO-G431RB + IHM09M2/STEVAL-IPM15B control path. No mains,
DC-bus energization, physical SD trip, or motor run was performed in this pass.

## Passed

- Clean rebuild of the active MCSDK Nucleo firmware and UNO Q sketch from the
  current source. `verify_firmware_bundle.py` and
  `air56b2_firmware_profile_check.py` pass.
- Rebuilt UNO Q and Nucleo flash binaries match the prepared package byte for
  byte. `verify_board_flash_package.py` passes for 30 listed artifacts;
  `ready_to_flash.zip` matches all 31 files in the package directory.
- Active protocol/guard, Wi-Fi HMI, firmware-update, Saleae-analysis, and Nucleo
  diagnostic self-tests pass. `nucleo_firmware_safety_check.py` passes after
  updating its stale CLEAR-rate-limit source pattern. The UNO Q superseded
  UART-reply C++ self-test passes.
- Read-only Wi-Fi `/api/status` returned HTTP 200: SAFE, PWM=0, Vdc=0 V,
  `fw_build=2026092901`, `mc_fw_build=2026091401`, fresh UART response,
  `bp_bad=bp_bad_cnt=0`, HMI disarmed and HV calibration incomplete.
- Earlier same-day Saleae logic-only evidence in
  `artifacts/bkin_software_break_release_2026092901/report.json` passed:
  six diagnostic PWM channels at 10.025 kHz, 2 us interlock gaps, no pair
  overlap, and all six LOW after a *software* TIM1 break. Production firmware
  was restored; `artifacts/production_2026092901_final_idle/report.json`
  confirms SAFE/PWM=0, six outputs LOW, and unarmed START rejected.

## Not released for power

The active MCSDK release preflight still fails four checks:
`external_softstart_hil_validated`, `motor_profile_is_real_acim`,
`generated_motor_configuration_matches_profile`, and
`ipm_sd_bkin_hardware_trip_validated`. The latter three must not be inferred
from a diagnostic PWM capture: physical SD/BKIN response and actual motor
identification have not been measured. The package correctly retains
`hardware_validated=false` and `logic_pwm_chain_validated=false`.

`research_readiness_check_selftest.py` also fails because its archived theory
snapshot hashes no longer match `README_RU.md` and
`snh_pwm/source/tests/test_air56b2_energy_value_audit.py`. That is a separate
research reproducibility issue, not evidence of a bench-control failure.

The only source edit in this pass is the updated static CLEAR-rate-limit check
in `tools/nucleo_firmware_safety_check.py`; no board was reflashed.
