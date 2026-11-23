# Powered Run Failure and Sender Invariant Fix, 2026-10-10

## Actual Stand Result

- The authorized Wi-Fi START reached VF_RUN and reported PWM active.
- The operator confirmed shaft rotation and subsequently switched off mains.
- The test aborted before its intended duration with one UART_RX_ERROR,
  NE=0x04, in the Nucleo snapshot. MCSDK current/occurred masks were both zero.
- One marked byte was observed; accepted-noise count was zero; the transport
  result was NOISE_REJECTED. STOP was acknowledged and final PWM was OFF.
- The observed active reply age reached 208 ms; the recorded active transmit
  gap maximum was about 200 ms. This did not produce the reported stop reason,
  but it is a scheduling-margin issue requiring separate investigation.
- Evidence: autonomous_motor_trial_r2/report.json and wifi_logs.txt. The failed
  result remains failed; physical motion alone does not qualify reliability.

## Reproduced Software Defect

In the installed Uno sender, scalar bytes 10/11 contain the legacy magnitude
computed from the local frequency ramp. In the installed Nucleo MCSDK semantic
handler, those bytes are not read or applied; Nucleo owns V/f voltage and ramps.
The unchanged-RUN transport check nevertheless compares every payload byte
except sequence. Changing an unused magnitude field resets the clean recovery
count, making the bounded NE path unavailable in the reproduced ramp sequence.

An isolated Uno 2026101008 candidate sets that field to zero only for the
MCSDK backend. The legacy backend retains its magnitude calculation. The
receiver binary 2026101006 is unchanged. CRC, hard error handling, frame deadline,
replay checks, watchdog, voltage checks and physical PWM protections are not relaxed.

## Offline Results

- sender_invariant_regression_r1/report.json: 41/41 suites PASS.
- The new reproduction performs 12000 assertions, including 1000 synthetic
  intact single-NE trials cycling 256 distinct sequence values. These are
  repeated deterministic checks, not 1000 independent physical observations.
- Installed-sender pattern: all 1000 such NE trials rejected.
- Canonical unused-field pattern: all 1000 accepted after existing clean-RUN
  prerequisites. A subsequent CRC-corrupted frame is still rejected.
- sender_invariant_fix_r1/uno_build: ARM build successful; 131468 bytes flash,
  64738 bytes static RAM. No upload was performed.

## Remaining Limits

The actual rejected frame, its CRC outcome and rejection byte position were
not retained by the installed telemetry. Therefore this deterministic defect
is NOT yet proven to be the precise rejection path of this live event. The
physical noise source is also unproven; it may require electrical remediation.
Startup clean-frame timing, malformed/noisy headers and true corruptions still
must fail closed. No further powered trial is justified by the offline result alone.

The candidate is not installed or HV-qualified. The local HMI source now blocks
its exact identity even with a saved calibration, but that HMI guard change has
not yet been deployed. Deploy/verify that block before any candidate upload.
Then verify the new sender's command invariance on a non-powered bench and add
first-rejection detail if physical diagnostics are still insufficient.
