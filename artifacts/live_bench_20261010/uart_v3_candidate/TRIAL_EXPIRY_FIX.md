# Trial Preparation Expiry Fix, 2026-10-10

The first requested run did NOT send ARM or START. The unused preparation
expired after an arbitrary 600 seconds. Final STOP was acknowledged; the
reported PWM state remained OFF and UART counters were zero. Retained evidence:
`autonomous_motor_trial_r1/report.json` (failed, not rewritten).

Two preparation-lifecycle defects were corrected in the HMI source:

1. Permission lifetime now follows the authenticated host attestation's remaining
   validity, capped at 3600 seconds and tracked monotonically. Its remaining time
   is exposed in status. Observations never extend it. Expiry still blocks START.
2. Existing one-second idle-watchdog RPC reads feed the same observation gate.
   A chat/browser pause no longer discards continuously verified telemetry.
   Missing/bad telemetry, restart and real observation gaps still reset the window.

The client detects an expired preparation promptly without trying ARM or START.
The exact peer/image qualification, one-shot consumption before START, fresh
powered observation, 10-second ARM window, <=10 Hz V/f target, MCU-backed
<=3-second run limit, independent HMI deadline and physical fault handling are
unchanged. No unsafe gate was bypassed to recover this failed attempt.

Final local regression: `powered_trial_regression_r5/report.json`, 40/40 suites
PASS; 175 dedicated trial checks include lifetime bounds, validity beyond the
old 600-second boundary, exact expiry, background idle observation without
commands and fault-induced observation reset. Earlier r3 evidence is retained.

New server SHA-256:
f427d0dc4f818e04abb2dd7f1d40b39c048eec4365936d056bd4a507e4e86522.

The final server was installed and byte-matched by the HMI installer; see
`powered_trial_hmi_r3/install.log`. Neither MCU image nor the saved calibration
was modified. Actual zero-bus preparation passed; remaining permission time
was about 3550 seconds. Four negative requests were rejected and the unused
verification permission was canceled (`powered_trial_hmi_r3/live_verification.json`).

On power-down, a first undervoltage snapshot carried occurred-mask 0x0404,
including a recorded driver-protection occurrence. Preparation now accepts
that narrowly identified history on a discharged bus without ACK/ARM/START.
The history remains visible and fault-free powered readiness is unchanged.
Automatic undervoltage-only acknowledgement still rejects the combined history;
it requires separate inspection before acknowledgement. This does not identify
the physical source or classify every DP fault as harmless.

Installation requires the power bus discharged and the HMI disarmed. This
record describes a tested source fix, not a completed motor start or a general
HV qualification. Neither MCU image needs to be flashed for this correction.
