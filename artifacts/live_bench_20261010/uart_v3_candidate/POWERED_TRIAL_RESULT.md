# Bounded Powered-Trial Preparation, 2026-10-10

## Implemented and Installed

- Only the Linux HMI server was updated; neither MCU was flashed in this step.
- Installed server SHA-256:
  e1e02c930b4bf15dd8457fbd7a1f5be2af600d0aa4ac7e9a2a1077599422f380.
- Active pair remains Uno Q 2026101007 / Nucleo 2026101006.
- Installer verified calibration byte preservation and validity.
- Backup on Uno Q:
  /home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/backups/vbus_reuse_20261010_182758.
- Authenticated one-shot preparation is separate from ARM and START.
- Required powered observation: 30 seconds, 20 advancing-counter samples,
  100 new good frames, fresh fault-free telemetry and calibrated 250..360 V bus.
- Trial is limited to V/f <=10 Hz and <=3 seconds; both MCU limit and independent
  HMI deadline are retained. Permission is consumed before attempting START.
- Normal deadline uses confirmed STOP; actual faults or unconfirmed STOP still
  escalate to ESTOP. Ordinary commands cannot extend limits or select FOC/PFC.
- Normal HV arming stays blocked when the trial gate is absent.

## Verified

- Offline regression: 40/40 suites PASS, including 156 dedicated mocked checks
  of trial qualification, observation reset, single-use permission, bounded
  START ordering, lost START reply, normal watchdog STOP and HTTP authentication.
- First regression failure was an outdated expected rejection string, not an
  accepted unsafe command. The failed report is retained as powered_trial_regression_r1.
- Live zero-bus preparation PASS: MODE VF / SET FREQ 5, no START.
- Seven live negative requests all returned HTTP 409: excessive requested run
  limit, start without readiness, excessive frequency, direct excessive MCU
  run-limit setter, FOC mode, service output, and ARM with a zero bus.
- The unready START was rejected by the real zero-bus controller fault; this
  live rejection alone does not independently test every other ARM condition.
- Trial preparation was canceled afterward. Final profile HV, disarmed;
  trial gate absent; PWM and service outputs OFF; both bus readings 0 V.
- Final 20-second direct Wi-Fi observation: 23 status samples, 283 new good
  UART messages, no new UART errors, no HTTP errors; logs downloaded.

## Evidence

- powered_trial_regression_r2/report.json
- powered_trial_hmi_r1/install.log
- powered_trial_prepare_r1/report.json
- powered_trial_hmi_r1/live_guard_verification.json
- powered_trial_hmi_r1/final_idle/summary.json
- powered_trial_hmi_r1/final_idle/logs.txt
- powered_trial_attestation_r1.json (short-lived, not general HV approval)

## Remaining Physical Stage

No successful START or powered motor test occurred in this step. The new
trial's powered idle qualification and motor behavior remain unmeasured.
Phase-current telemetry remains unqualified; AS5600 is not required for V/f.
The prior software TIM1 Break is not a physical IPM overcurrent/UVLO test.

Next establish autonomous power with ALL PC USB and Saleae/probe connections
removed and the power bus still discharged. Prepare the gate over Wi-Fi after
any Linux/HMI cold restart. Powered observation and the single motor trial are
separate operator-supervised steps, never an unattended power-on sequence.
