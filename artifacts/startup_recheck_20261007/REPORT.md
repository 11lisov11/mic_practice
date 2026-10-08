# Startup Recheck, 2026-10-07

Both connected boards were programmed with build `2026100705` and verified by readback. No ARM, START or energized motor command was sent during this recheck.

## Corrections

1. Single ramp owner. UNO Q now sends the final scalar frequency, not its local intermediate ramp. Nucleo handles the MCSDK ramp, with minimum duration 3 s and rate ceiling 5 Hz/s. Identical heartbeat targets do not restart it.
2. Current-trip ownership. Unwired UNO Q ADC pins are not phase-current sensors. They no longer trip the MCSDK topology; the old local backend still has its original local current threshold. This is not disabling IPM/MCSDK/BKIN protection, nor adding validated phase-current protection.
3. Bus-loss stop. Dropping below 200 V or exceeding 385 V stops an active command in the main loop, even without a new UART frame. Recovery alone cannot restart the drive. MCSDK's generated undervoltage threshold is 10 V, so the application check is independently necessary.
4. Frequency resolution. Commands below one MCSDK speed unit cannot energize a zero-frequency ramp.

## Evidence

- `native_final/report.json`: 390882 assertions, 262144 command combinations, all eight deliberate mutations detected.
- `ramp_final/report.json`: 250636 production-helper checks and a quantized ramp model. For a 10 Hz target, the old cascade gives about 4.3 Hz at 3 s, the new single-owner model gives 10 Hz. This is not measured shaft speed and does not establish the cause of the earlier HV fault.
- Decoder: 66055 cases. HMI command guard: 162 cases. Calibration compatibility: 33 cases. IPM shutdown IRQ host test: four cases.
- `uno_verify.log` and `nucleo_flash_verify.log`: post-programming readback passed. Nucleo build: zero errors, zero warnings.
- `live_final/report.json`: 60 s read-only Wi-Fi, 99 samples, 899 new UART messages, no new errors. Both build IDs are 2026100705. PWM and ARM stayed off. The only reported motor fault is expected undervoltage at 0 V.
- `wifi_commands/report.json`: 5 -> 20 -> 0 Hz setpoints acknowledged over LAN Wi-Fi while SAFE; STOP confirmed, no new errors. This checks the command path, not active PWM.
- HMI installation preserved the original calibration file byte-for-byte. No new zero or high-point capture.

## Remaining Boundaries

Successful motor rotation, energized currents and loaded protection timing after this update have not been measured. The earlier logic PWM captures belong to older/fixture firmware, not to this new physical run. AS5600 magnetic validity is still false. Nucleo phase-current telemetry is not qualified. The old full `firmware/ready_to_flash` bundle is not the installed build; use the separately labeled update only.

The next acceptance test is one operator-supervised bounded V/f run with all PC/analyzer wiring removed, logging the exact fault branch if it stops. There is no automatic retry and no guarantee that all hardware risks have been eliminated.
