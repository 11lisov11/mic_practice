# Uno Q 1002: active logic PWM and recovery qualification

Date: 2026-10-10, Europe/Moscow. No mains or J4 power was enabled in this work.
The operator confirmed the unpowered setup and later power-cycled both USB boards.

## Final Installed State

- Uno Q: 2026101002, live identity confirmed after the operator's cold restart.
- Nucleo: production 2026100801 restored; byte readback matches the reference.
- HMI: `26aad6a1156378d11faee5f995a6ba5a5493e78cc76ae0c357afd3c168983dfc` installed.
- Bus calibration preserved byte-for-byte and valid for the exact 1002/801 pair.
- Final: SAFE, PWM=0, ESTOP=0, ARM=0, disarmed HV profile, reported bus=0 V.
- Final counters: rejected commands=0, rejected replies=1, reply sequence errors=0.
  The one rejected reply appeared at restoration/programming, not in the active run.
  Counters were not reset merely to report a clean active run.

Uno flash artifact SHA-256:
`fda80b586f070873640d467d81f4794821657a4c501283cb41ae0618b3b68823`.
The upload completed and live build 1002 was observed. A separate post-upload
byte readback of Uno 1002 was NOT completed; do not confuse ELF/layout tests with
device-byte verification. Nucleo restore byte verification DID complete.

## Changes

1. Retained one recursive control/UART owner for main loop and RPC callbacks.
   Replaced `K_MUTEX_DEFINE` with an ordinary RAM mutex and explicit
   `k_mutex_init` before RouterBridge starts, following the installed library's
   pattern. The actual ELF has a 20-byte mutex in `.bss`, no kernel mutex section.
   The old 1001 ELF is a negative control. This removes an undesirable extension
   storage-layout dependency; it does NOT prove the original powered CRC cause.
2. HMI can return to the disarmed HV profile with expected undervoltage only for
   the known production pair, fresh bus <=2 V/raw <=20, inactive outputs and
   diagnostics showing ONLY undervoltage. ARM and START checks remain unchanged.
3. The bench runner preserves programming-boundary history separately from new
   runtime errors, checks a stable baseline, and refuses generic fault CLEAR.
   A narrowly recognized single stopped-peer FE can be acknowledged only in the
   discharged programming phase. CRC, ORE, noise, RUN state and other fault masks
   are rejected by this exception. The successful final run did not need that FE ACK.
4. Added controlled cleanup for the bench's own ESTOP and restored-profile checks.
   History is recorded before an idle ACK; no automatic motor restart is performed.
5. Short 12 MHz carrier captures avoid the observed repeated USB timeouts at
   24 MHz. Longer transition captures retain 4 MHz acquisition.

## Results

`active_pwm_r2_12mhz/report.json`: overall PASS, restore PASS, calibration PASS.

| Scenario | Result |
| --- | --- |
| Carrier during a ramp toward 5 Hz | PASS |
| Carrier during a ramp toward 20 Hz | PASS |
| STOP | PASS |
| ESTOP | PASS |
| Zero frequency command | PASS |
| Run time limit | PASS |
| Concurrent RPC reads and setpoints during active PWM | PASS |
| Software TIM1 break event | PASS |
| Restart without fault acknowledgement rejected | PASS |
| Operator heartbeat timeout | PASS |

All six observed GPIO carriers: 16 kHz. No complementary overlap was detected.
Minimum measured gap: approximately 1.333 us on U/V/W, sample period 83.333 ns.
This agrees with the 1.35 us configured deadtime within acquisition resolution.
There were zero NEW command, reply-integrity or reply-sequence errors in the
active phase. The concurrent RPC observer collected 14 samples, 5 while PWM was on.
The full current software regression passed 33/33 suites; profile/ARM guard
negative cases, kernel-storage ELF negative control, host mutex exclusion and the
actual-parser restart experiment are included as separate evidence.

The tested Nucleo 899 fixture was derived from production 801: real zero-bus ADC
interlock, virtual 310 V modulation normalization and bounded run time. Timer
initialization and selected PWM/break machine-code functions match production.
Production was restored after the test. The production binary itself was NOT
commanded to generate PWM on a zero bus. Target electrical 20 Hz, motor speed,
torque, current accuracy and powered gate-driver behavior were NOT qualified.
The software break event is NOT a new physical PA6/IPM trip measurement.

## Retained Failures And Limits

- Earlier 1001 runs are retained, including an active pass and a cleanup failure.
- A truncated old reply followed by a restarted peer's reply produces one rejected
  mixed frame in the actual Uno parser with host serial/clock/reply-state stubs.
  This establishes a possible restart mechanism, not the physical cause of any
  powered fault and not a command-channel CRC explanation.
- Repeated long/short 24 MHz acquisitions sometimes failed with Saleae ReadTimeout.
  The failed 1002 capture was followed by a protective ESTOP, not UART corruption.
- A software verify/reset attempt left RPC unavailable while Linux/Wi-Fi remained
  reachable. Re-upload alone did not recover it; the operator's complete board
  power cycle did. Cold startup of 1002 was verified. Automatic warm RPC recovery
  is still unqualified. The experimental `reset_unoq_nucleo_idle.py` is NOT an
  approved recovery path for the current stand.
- The original powered trial's command CRC fault remains unexplained: its rejected
  raw bytes were not captured. Active zero-bus success does not prove immunity to
  switching interference or resolve powered commissioning.
- Protocol v2 uses XOR. The corruption audit still finds checksum-preserving
  paired-bit mutations. Its audit passes by detecting the weakness; checksum
  qualification remains FALSE. A coordinated stronger protocol and rejected-frame
  tracing remain engineering work. Do not disable integrity/timeout/bus guards.

This report is logic-bench evidence, NOT an authorization or certification for
mains operation or a claim that all physical protections have been qualified.

## Evidence

- `active_pwm_r2_12mhz/report.json`: final 10-scenario run, images and restore.
- `active_pwm_r2_12mhz/*/`: saved Saleae captures and raw transition CSV.
- `regression_r3/report.json`: 33 suites, full source fingerprints, checksum caveat.
- `elf_mutex_layout/report.json`: current real ELF and old-layout negative control.
- `hmi_profile_fix/install.log`: installed server and unchanged calibration.
- `install/flash.log`: Uno 1002 upload and Nucleo-reset log alongside it.
- `active_pwm_r1/report.json`: failed 24 MHz capture and saved fault snapshots.
- `../uno_control_owner_1001/reply_restart_parser_r1/report.json`: restart experiment.
- `../uno_control_owner_1001/paired_idle_reset_r1/report.json`: failed warm recovery.
- `../motor_first_trial_r1/REVIEW.md`: original powered trial and evidence limits.
