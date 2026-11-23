# Uno Q ownership update and idle Wi-Fi qualification

Date: 2026-10-10. Scope: programming and discharged, disarmed bench only.
The operator confirmed that J4 was off and the power input physically disconnected.
No ARM or START commands were issued during this qualification.

## Installed state

- Uno Q: build 2026101001, image verified against the device.
- Image SHA-256: `92f3c7484ceb31ff67e04a1d0b08292499f1875cf49fef12fe6d14c4a4fece38`.
- Nucleo: build 2026100801, not programmed in this update.
- Read-only Nucleo image matched the installed reference before programming Uno.
- Existing bus calibration was preserved byte-for-byte; the HMI accepts only the
  explicitly qualified new Uno/unchanged Nucleo pair, not arbitrary future builds.

## Change

RouterBridge RPC callbacks and the main loop previously accessed shared control
and UART transaction state without a common owner. They now use one recursive
Zephyr mutex, released before the main loop yields. The host tests exercise the
same RAII lock and detect a deliberately removed callback guard.

This corrects a concurrency risk. It does not establish the cause of the earlier
powered UART checksum fault. Wire protocol, pin mapping, Nucleo PWM/protection,
bus scaling and run limits were not changed.

## Verification

| Check | Result |
| --- | --- |
| Complete software regression | 30/30 suites passed |
| Ownership host test | 2,000 frames; 2,008 assertions; negative control detected |
| Device installation / verify-only | Passed |
| Concurrent Wi-Fi idle commands | 80 accepted commands: 20 x (5 Hz, 20 Hz, 0 Hz, STOP) |
| Concurrent idle observation | 126 samples over 61.172 s |
| New Uno UART received messages | 393 |
| New command checksum / reply integrity / sequence errors | 0 / 0 / 0 |
| Largest observed UART telemetry age | 49 ms |
| HTTP command latency, median / maximum | 0.3435 s / 1.517 s |
| All observed PWM/arming/service outputs off | Yes |
| Final STOP sequence | HTTP 200, acknowledged |
| Wi-Fi log download | Succeeded |

Final state: SAFE, PWM=0, armed=0, setpoint=0 Hz, reported bus=1 V.
Fault 5 (undervoltage) is expected on this unpowered bus; it was not bypassed.
HTTP latency and telemetry age are sampled observations, not real-time bounds.
The idle setpoint commands do not demonstrate physical PWM or motor speed.

## Remaining limits

1. The earlier first powered trial produced observed shaft movement, then a
   detected command checksum fault. Its rejected raw frame was not captured;
   electrical interference versus software corruption remains unproven.
2. Protocol v2 uses XOR. The offline corruption audit found 256 paired-bit
   mutations which preserve the checksum and change a frequency command. The
   audit passed by detecting this weakness; checksum qualification did NOT pass.
   This is not evidence that such a collision caused the earlier detected fault.
3. Current measurements and encoder speed are not qualified by this run.
4. Active PWM under load, restart after the update, and powered fault behavior
   have not been requalified. This report is NOT a release for mains operation.
5. A coordinated, versioned stronger-checksum update for both controllers and
   active low-voltage timing verification remain next engineering work. Do not
   disable integrity checks, watchdogs or undervoltage to conceal a failure.

## Evidence

- `install_verified_r2/report.json`: installed pair, verify-only and idle samples.
- `regression_final_r2/report.json`: all suite results and source hashes.
- `regression_final_r2/uno_control_ownership_selftest/report.json`: lock test.
- `regression_final_r2/uart_command_corruption_selftest/report.json`: corruption audit.
- `wifi_concurrent_idle_r1/report.json`: commands, observer samples and final STOP.
- `wifi_concurrent_idle_r1/wifi_logs.txt`: downloaded stand logs.
- `../motor_first_trial_r1/REVIEW.md`: earlier powered trial and evidence limits.

Installation history is retained: `install_r1` flashed the correct image but
stopped on the peer's expected idle link pause. `install_verified_r2` resumed with
the same verified image and acknowledged only the narrowly checked idle pause.
The initial failed regression runs remain on disk alongside the passing rerun.
