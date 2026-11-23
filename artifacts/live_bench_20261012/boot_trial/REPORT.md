# 1108/1102 Conditional Short Trial Preparation

## Completed

- Full updated-source regression: **57/57 suites passed** (`regression_r2`).
- New pair/qualification/lifecycle checks: **101 cases passed**.
- Candidate HMI command/trial/authentication/calibration guards: **5/5 passed**.
- Adapted runner stop-classification checks: **8 cases passed**, no hardware calls.
- Only Linux HMI updated via pinned-key Wi-Fi SSH. Neither MCU was programmed.
- Original calibration bytes and capture identities retained; file SHA256:
  `a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17`.
- Prepared one conditional **5-Hz / 3-second** trial, not armed or started.
- Post-install auxiliary observation: 30 seconds, 587 new correct messages,
  no new UART errors, all observed outputs off.

The first full regression failed because a new test fixture omitted
`hmi_hv_armed`; the safety precheck correctly refused incomplete data. The
fixture was corrected, and the complete source-fingerprinted run was repeated.
The failed reports are retained; no failed qualification was deployed.

## Why Calibration Can Be Reused

Nucleo image remains the flash-verified 1102 image. The previous component
audit was rerun: motor PWM functions/timer initialization remain equivalent
to retained measured baseline code, except the explicitly audited break
recorder. Uno's Vbus decoding fragment is byte-identical in source to 1104,
including the 0.1-V/LSB conversion. Only the exact reviewed 1108/1102 identity
was added to the HMI calibration-compatible list. Schema, VF capability and
MCSDK telemetry tag must still match; unknown identities remain rejected.

The calibration file is neither retagged nor recaptured. Compatibility of its
measurement contract is distinct from permission to run. Ordinary unrestricted
HV ARM for this pair remains blocked even when calibration is valid.

## Grant and Limits

The grant contains exact firmware image hashes and fingerprints of retained
PWM evidence, source audit, installation readbacks, regression, autonomous
idle data, the operator's SD sample and original calibration. It expires
after at most 600 seconds and is consumed by one start.

It explicitly does **not** claim a fresh active PWM measurement, current
register/GPIO readback or qualified phase-current telemetry. Retained baseline
PWM/component equivalence, live off-state telemetry and the operator's static
2.6-V SD sample are the conditional basis, not a general powered release.
The older Nucleo installation report's overall failure is retained; only its
confirmed flash readback is reused, alongside subsequent healthy live tests.

Preparation alone may occur with the already observed auxiliary bus bias
up to 10 V. It does not enable outputs or acknowledge faults. ARM/RUN still
require 250..360 V, fresh fault-free VF telemetry, zero transport errors,
valid temperature/softstart state and 30 seconds/100 new good frames of
powered-idle observation. Frequency is capped at 5 Hz and duration at 3 s;
coast30, unknown peers and a second start are rejected. The existing MCU
runlimit, independent HMI deadline, 300-ms UART watchdog and BKIN are unchanged.

## Next Controlled Steps

All PC USB/analyzer wiring must remain removed; controllers retain autonomous
supply. The motor must remain secured, contacts covered and the operator by
the supply switch. Keep J4 on. The next stage is **mains on with no PWM**,
not an automatic start. The operator reports readiness/power state first.

After that, an observer command can acknowledge at most one specifically
identified pre-START undervoltage if the existing checks permit it, and wait
for 30 seconds of healthy powered idle. Any unexpected protection or link
event prevents ARM/START. A separate operator-authorized run is then bounded
to 5 Hz / 3 seconds and confirmed STOP; no repeated starts on a failed result.

Prepared runner (execute only at the appropriate confirmed stage):

```powershell
python artifacts/live_bench_20261012/boot_trial/run_trial.py observe --token-file .unoq_ssh/control_token --ack-undervoltage --outdir artifacts/live_bench_20261012/boot_trial/powered_idle_r1
python artifacts/live_bench_20261012/boot_trial/run_trial.py run --token-file .unoq_ssh/control_token --ack-undervoltage --confirm-autonomous-ready --outdir artifacts/live_bench_20261012/boot_trial/motor_short_r1
```

The runner is the regression-fingerprinted existing implementation adapted
only to this exact pair, its 5-Hz ceiling and matching 3-second deadline
signature. A matching timed ESTOP is classified as a signature, not a uniquely
proven physical stop cause. Raw diagnostics/first-break records are retained.

Evidence: `candidate_r1/`, `install_r1/report.json`, `prepare_r1/`,
`aux_post_install_r1/`, `selftest_r4/`, `hmi_guards_r1/`, `runner_selftest.json`.
The earlier powered MC_DP event and 30-second motor operation remain unresolved.
