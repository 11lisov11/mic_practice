# Uno sender invariant fix: installed, powered trial pending

## Result

- Uno Q 2026101008 was programmed and the loader/sketch flash verified in one session.
- Nucleo 2026101006 was not flashed or modified.
- Full offline regression: 42/42 suites passed with unchanged source fingerprints.
- Fresh Wi-Fi-only command check: MODE VF, targets 5 -> 20 -> 0 Hz, STOP.
- Thirty-second stopped observation: 417 new valid UART replies, no new UART errors.
- Actual PWM, ARM and START were not requested during this stopped observation.
- Original Vbus calibration bytes were preserved, SHA256:
  a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.
- New bounded trial was prepared on a 1 V bus. It is NOT an ARM or START.
- After removing PC connections and switching to powerbank, fresh Wi-Fi status
  confirmed the same pair, SAFE/off outputs, a 1 V bus and no UART errors.
- The trial was re-prepared after the autonomous HMI restart; still no START.
- A powered trial of image 1008 was subsequently attempted; see the section below.
  Overall trial qualification remains incomplete, not passed.

## Correction

The MCSDK command keeps a constant requested frequency during ramp-up, but the
old Uno sender varied the unused legacy magnitude at bytes 10/11 with its local
ramp. The receiver ignores this magnitude for actuation, yet compares it when
deciding whether recent RUN commands are unchanged. This repeatedly prevents
the clean-frame prerequisite for its existing bounded intact-CRC noise policy.

Image 1008 uses zero for this ignored field only with the MCSDK scalar backend.
The legacy backend retains its original magnitude. CRC, sequence checks, noise
budgets, watchdogs, Nucleo code, PWM timers and physical protection are unchanged.

The deterministic host reproduction rejects 1000 injected intact-CRC NE frames
with the old varying field and accepts 1000 after the fix under the existing
guarded prerequisites. Subsequent CRC damage remains rejected. These trials
cycle through 256 sequence values; they are not 1000 independent hardware
experiments and do not prove physical noise immunity.

## Installed Identities

Uno image SHA256:
1ebb68a6bf9180643ec471e240b4ab125c51866f8da1d69c974421bbd403708a

Retained Nucleo image SHA256:
20530ef90893b8cdb074739e3b8fd02d0bb0c478016ab291e036192c4a784479

Installed HMI server SHA256:
1ba99c686ff8b4441f20542d3e161ef311362bee446f8c52824608a9887b0bf2

## Evidence

- `sender_install_r1/flash_verify_uno.log`: successful flash readback.
- `sender_install_r1/report.json`: retained installer failure after a warm-reset
  RPC timeout. This failure was not rewritten as a pass.
- `sender_wifi_idle_r1/report.json`: successful fresh verification after an
  operator-confirmed full board power cycle; 1008/1006 identities and clean link.
- `sender_trial_regression_r1/report.json`: 42 offline suites.
- `sender_trial_hmi_r1/install.log`: updated HMI and unchanged calibration.
- `sender_trial_attestation_r1.json`: explicitly scoped component-evidence transfer.
- `sender_trial_prepare_r1/report.json`: prepared, disarmed one-shot trial.
- `sender_autonomous_boot_r1/report.json`: fresh stopped Wi-Fi status on powerbank.
- `sender_autonomous_prepare_r1/report.json`: new permission after power transition.

The eight retained zero-bus PWM scenarios were measured with Uno 1007 and the
unchanged Nucleo 1006. The new attestation explicitly states this provenance;
it does not claim that all eight were physically remeasured on Uno 1008.
The permission is bound to exact image identities, expires within one hour,
requires 30 seconds of healthy powered idle, and allows one run up to 3 seconds
with a target at most 10 Hz. General HV release remains blocked.

## Next Step

The operator confirmed mains and J4 off after the attempted trial. Keep PC
connections removed while the DC link discharges. A new one-shot preparation
requires a discharged bus and a fresh controller session; do not reuse the spent
permission. No firmware programming is needed for the host observer correction.

## First Powered Attempt With Sender 1008

`sender_motor_trial_r1/report.json` remains `pass: false`.

- Passive powered preflight: 324 V, only the specifically recorded undervoltage
  history, no UART errors. Explicit CLEAR followed by fault-free idle observation.
- START accepted with 5 Hz target, 3 s runlimit and VF_RUN/PWM-active telemetry.
- Seven active snapshots show no UART rejection or MCSDK fault. One NE event
  was observed and accepted under the unchanged guarded intact-CRC policy.
- Final Nucleo bad count, UART error flags and transport fault were all zero.
- Physical shaft rotation was not observed by the operator and is unconfirmed.
- The host observer stopped waiting before it could record the automatic stop.
  START HTTP setup took 1.054 s out of the old 3.5 s request-based readback window.
- Emergency cleanup and the concurrent HMI deadline produced an ESTOP record.
  Final stop was acknowledged, with SAFE state and PWM off. This is not evidence
  that the earlier UART rejection recurred.
- Encoder I2C errors rose during the run. Its bus/magnet state was intermittent;
  no encoder-based speed result is qualified. This V/f trial did not use it.

## Host Observer Correction

Readback now receives a bounded 4 s window after START HTTP acknowledgement,
instead of spending that window on pre-START HTTP work. Both MCU runlimit and
the HMI independent deadline remain 3 s. The extra time is observation time,
not a command extending the drive's permitted operation.

A successful normal STOP no longer unconditionally adds ESTOP in cleanup.
Failures or unconfirmed outputs still escalate to emergency stop. Network
failure in cleanup is retained in the report instead of losing the report.

The timing reproduction and normal/emergency cleanup checks pass in 211 offline
cases. Full unchanged-source regression after this correction is 42/42:
`sender_stop_observer_regression_r1/report.json`.
These host corrections have not yet been exercised in a second powered trial.
The earlier failed trial was not relabeled as successful.

## Stopped Zero-Target Follow-Up

After the operator-confirmed board restart, fresh telemetry showed Uno 1008 /
Nucleo 1006, SAFE outputs, no ESTOP and zero transport error counters. A residual
bus was observed decreasing from 10 to 5 V; no ARM/START was sent.

The actual Uno `request_normal_stop()` calls `hard_stop(true)`, which sets the
frequency command to zero. Both the host run observer and the installed HMI
trial runtime check previously demanded a strictly positive frequency even in
SAFE with PWM off. This mismatch can misclassify a normal runlimit stop.

The reviewed correction allows a zero target only for an already stopped trial.
HMI arming/idle qualification still requires a positive target. Active outputs
with zero target remain rejected. Transport, measurement, fault and service
output checks and the independent 3 s deadline are unchanged.

Checks: 219 offline scenarios, and 42/42 unchanged-source suites in
`stopped_zero_regression_r1/report.json`. Tests now simulate the actual stop
behavior by setting `freq_cmd=0` rather than leaving it at the RUN target.

At this checkpoint the correction is local, not installed on Uno Linux.
The operator has been asked to connect only Uno USB with mains/J4 off for an
HMI-only update. MCU images remain unchanged, and no second powered start has
been performed. This checkpoint must not be treated as completed commissioning.
