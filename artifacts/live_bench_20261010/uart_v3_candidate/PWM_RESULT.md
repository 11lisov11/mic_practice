# Zero-Bus PWM Check, 2026-10-10

## Confirmed

- Physical Saleae analyzer A7D1BB81883C0092, seven connected channels.
- Six outputs LOW before tests; PA6/CH6 HIGH.
- Wi-Fi -> Uno Q -> UART v3 -> Nucleo -> all six PWM outputs observed physically.
- Carrier 16,000 Hz on all six channels at requested setpoints 5 and 20 Hz.
- Minimum measured complementary gap approximately 1.333 us at 12 MHz sampling.
- No HIGH/HIGH overlap observed in the raw accepted traces.
- Captured STOP, ESTOP, frequency-zero stop, and MCU run-limit stop passed.
- Complete Wi-Fi START / target changes 5 -> 10 -> 20 / STOP capture passed.
  The targets were accepted (freq_cmd=10 and 20); the short test did not reach
  either steady-state electrical frequency. Actual ramp telemetry was 1.16
  and 1.51 Hz. Do not describe this as sustained operation at 10 or 20 Hz.
- Software TIM1 BG event stopped all six PWM outputs, produced MC_DP_FAULT
  (0x0400), and rejected START without acknowledgement (HTTP 409, ok=false).
- The two final continuous captures used no acquisition-prefix quarantine.
  LOW tails after shutdown were 3.7500675 s and 2.0472875 s, respectively.
- 39/39 offline regression suites passed after the runner changes. The flash
  recipe test exercises unchanged/changed images, write failure, and failed
  post-write verification with a Tcl interpreter and mocked hardware commands.
- After normal-image restoration, a 20 s direct Wi-Fi observation received
  277 new valid UART messages with no new errors; a separate analyzer capture
  confirmed six outputs LOW. Logs were downloaded through Wi-Fi.

## Scope and Limits

Eight of eight named zero-bus scenarios have passed. Six passed subchecks were
reused from active_pwm_r3 after exact image-hash matching; ACTIVE_RPC and
TIM1_BREAK were newly captured in active_pwm_r5. The six PWM/break machine-code
sections match the normal candidate, and the timer initializer source matches.
This is NOT an assertion that the entire diagnostic binary is identical.

TIM1 Break was stimulated through the debugger, not through PA6 or the IPM.
Its capture does not measure the response time from a physical fault input.
No physical IPM overcurrent/UVLO trip, powered UART-v3 immunity, motor current,
loaded motor behavior, or steady-state fundamental-frequency accuracy is
qualified by these zero-bus tests. The current channel remains unqualified.

The analyzer returned stale data in the first 2048 samples. A simultaneous
three-pair transition at sample 2048 caused one raw deadtime check to fail.
Original failed evidence remains intact. Established steady-state quarantine
and fresh idle acquisitions were used in the later accepted timing check;
raw overlap checking was retained. Do not treat the quarantined acquisition
prefix as qualified startup/stop data.

The earlier r4 attempt stopped before START with a status/RPC boundary timeout;
it remains failed evidence. A timeout alone does not locate the fault in WSL,
the network, HMI, router, or MCU. After the user's cold restart, direct Wi-Fi
status worked. The successful r5 run used direct LAN HTTP and a single Uno
programming session with explicit post-write verification, avoiding the prior
second reset solely for verification. This does not prove the earlier timeout's
root cause. Restoration runs independently of RPC availability.

## Current Images

- Uno Q 2026101007: b521f692621f9374338b59805d0f0a233e086dfe802c6f9ec28e768b8e4a1e9b
- Nucleo 2026101006: 20530ef90893b8cdb074739e3b8fd02d0bb0c478016ab291e036192c4a784479

Both restored images were byte-verified. Final live identities match 1007/1006,
PWM=0, estop=0, both bus readings=0 V, transport-error counters=0. HMI profile
is HV and disarmed. The diagnostic image is not left installed. The separate
post-restoration analyzer capture confirms all six outputs LOW.

## Evidence

- `active_pwm_r1/report.json`: initial trace and retained raw deadtime failure.
- `active_pwm_r1/carrier20_steady_reanalysis.json`: separate prefix-aware analysis.
- `active_pwm_r3/report.json`: six passed subchecks and unqualified RPC stop tail.
- `active_pwm_r4/report.json`: image-matched partial reuse, failed RPC boundary.
- `active_pwm_r5/report.json`: complete eight-scenario result and normal restore.
- `active_pwm_r5/ACTIVE_RPC/capture.sal`: full Wi-Fi active updates and STOP.
- `active_pwm_r5/TIM1_BREAK/capture.sal`: software Break and LOW tail.
- `pwm_emergency_restore_r1/report.json`: actual restoration and flash verification.
- `pwm_fixture_interlock_test_r1/report.json`: zero-bus fixture interlock boundaries.
- `pwm_regression_final_r2/report.json`: 39/39 offline suites, source fingerprints.
- `post_pwm_idle_r1/summary.json`: direct Wi-Fi monitoring and log download.
- `post_pwm_idle_r1/physical_idle.json`: independent final LOW capture.

No HV release approval is given by this result; candidate HV arming remains
blocked in HMI. The zero-bus PWM task is complete. Powered qualification is a
separate stage, not an automatic consequence of an eight-scenario PASS.
