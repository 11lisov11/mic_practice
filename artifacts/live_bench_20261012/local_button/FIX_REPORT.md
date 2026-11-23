# Local STOP and Preparation Wait Fix, 2026-10-12

**Superseded preparation record.** Installed final pair: Uno 2026101205 /
Nucleo 2026101204; see `DEPLOY_REPORT.md`. This draft predates the diagnostic
peer and active-HIGH button corrections. Do not deploy its older images.

## Prepared Changes

Nucleo candidate: `candidate_r3`, build ID 2026101201. Uno Q 2026101108 is
unchanged. Neither the firmware nor HMI candidate was installed in this turn.
No hardware command, reset, debugger attachment, or firmware write was issued.

The strong PC13 callback latches a local inhibit, clears TIM1 MOE immediately,
and requests MCSDK STOP only after MCSDK boot is complete. The latch remains
set after button release. Foreground control rejects ENABLE while latched.
The V/f timer output-enable operation checks the latch, button level and
pending EXTI flag inside a short saved-PRIMASK critical section. The linked
R3_2 output-enable sites use the same guard. Hardware BKIN remains enabled;
automatic output re-enable remains disabled. IRQ latency is not measured here.

Only a clean, explicit CLEAR can release the latch. Release requires the button
up, no pending PC13 edge, MOE off, MCSDK IDLE and no current/past MCSDK faults.
It does not start the motor. Received ENABLE or STOP cannot release the latch.
The 300-ms link watchdog and existing power/thermal/transport guards remain.
Nucleo status bit 0x80 reports the local latch; the HMI displays LOCAL_STOP_PC13.
PWM status now reports actual timer MOE rather than just the RUN state.

HMI candidate: `wait_candidate_r4`. After authenticated, fresh, low-bus
preparation is accepted, the non-actuating waiting stage has no countdown.
Each ARM still requires 30 seconds of fresh fault-free powered idle observations
and 100 new valid UART frames. Peer identity change or observed counter rollback
invalidates the prepared request. Process restart drops it. Active ARM expiry,
one-shot consumption, the 3-second run limit and 5-Hz ceiling remain.

New-pair qualification uses a new schema and exact image hash. It requires
fresh physical PWM and local-STOP evidence; no such attestation was fabricated.
Old 1108/1102 evidence cannot authorize this new Nucleo image. Measurement
configuration is unchanged and original calibration identity compatibility is
retained explicitly, so re-capturing zero is not part of this update.

## Verification

- Original restart path reproduced: `restart_audit_r1/report.json`.
- Final host STOP checks: 1038; all passed (`selftest_r3/report.json`).
- Four deliberately broken variants were detected: output guard removed,
  sticky latch removed, CLEAR allowed while held, pre-boot MCSDK call unguarded.
- Final waiting/qualification lifecycle checks: 49; all passed.
- Five existing HMI guard suites passed against the final candidate:
  `hmi_guards_r3/report.json`.
- Existing repository regression: 57/57 passed in `regression_r1/report.json`.
  This preceding run covers the repository baseline suites, not physical tests
  of the new candidate. Final candidate checks above are separate.
- Final STM32CubeIDE target build: exit 0, 0 errors, 0 warnings. Empty-directory
  preliminary clean failures are preserved in the build log; final build
  succeeds. Non-gating HV preflight is not a powered-release approval.
- ELF resolves UI_HandleStartStopButton_cb to the strong application symbol,
  with a 4-byte BSS latch and linked guarded MOE publication.

## Final Artifacts

- Firmware: `candidate_r3/nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin`.
  Size 44676 bytes; SHA256
  `49d38e84c2cc5ba581c9cf8d272f5578a962c187dd495c288c647d8d75f66f0a`.
- ELF and HEX plus build manifest are adjacent to the BIN.
- HMI: `wait_candidate_r4/web_hmi/server.py`; SHA256
  `d7fe5cdb83afb2921d9e769e4de83e9a8fb5399ec7cd1e9878098ba346026076`.
- Reproducible preparation: `tools/prepare_nucleo_local_stop.py` and
  `tools/prepare_trial_wait_fix.py`.
- Core assets: `research/local_stop/local_stop.h` and `local_stop.inc`.

## Pending Hardware Stage

Firmware installation requires the operator's requested transition to mains
physically disconnected, J4 off, DC bus verified <=2 V and Nucleo USB attached.
Then verify readback/build identity, cold boot, local button STOP, held-button
CLEAR rejection, no restart under repeated ENABLE, and explicit reset behavior
on the non-powered motor output path. New image has no physical PWM validation
or unrestricted powered release yet. No autonomous continuation on link loss
was introduced. Installed old firmware/HMI and its expired preparation remain
unchanged until the deployment stage.
