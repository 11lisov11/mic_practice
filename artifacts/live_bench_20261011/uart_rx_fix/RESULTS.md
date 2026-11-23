# Uno Q UART RX repair

## Latest: 1108 RPC Restored, Idle Timing Improved

The operator's cold restart did not recover 1106 RPC. Candidate 1107 was also
flash-verified but failed live registration. Debug inspection showed main had
already exited at its original priority, before sketch setup. ELF analysis
identified the new TLS reference/relocation from `k_current_get()`.

Uno **2026101108** replaces it with the exported, non-TLS
`k_sched_current_thread_query()`. Actual boot and RPC registration succeeded.
The build now rejects TLS relocations before exporting images. Updated offline
regression passed **55/55** suites; predecessor/new flash images were verified.
Nucleo remains **2026101102**, and calibration is unchanged.

The native Wi-Fi 120-second off-only test received **2391** new correct replies,
with no new CRC, sequence, UART hardware or RX overflow errors. An overlapping
30-second client passed, and setpoints **5 -> 20 -> 0 Hz / STOP** were confirmed
with PWM off. Maximum enqueue interval was **53658 us**, down **81.53%** from
the separately measured 1105 maximum of 290460 us. Parser polling gap was 5 ms.
AS5600 has progressing reads/no I2C errors but `enc_ok=0`, so angle validity
must not be claimed. No ARM, START or CLEAR was sent.

See `../../live_bench_20261012/llext_fix/REPORT.md` for raw evidence and limits.
Active PWM, powered EMI/MC_DP, full 1108 cold boot and a 30-second motor run
remain unqualified; the new pair's ordinary HV ARM remains blocked.

## Earlier: RPC Priority Isolation 1106, Cold Restart Pending

The operator's full Uno restart restored 1105 RPC after a brief normal boot
interval (network timeout, then `get` unavailable, then a valid 1105 response).
The 120-second direct Wi-Fi test passed with 1203 new good replies and no new
CRC, UART hardware, overflow or Nucleo transport errors. Two additional
overlapping 20-second clients also passed. However the new measured all-state
TX maximum reached **290460 us** and parser gaps reached approximately 242 ms.
Thus 1105 narrowed the scheduling margin but did not sufficiently isolate
control from RPC load. These are measured results, not general powered approval.

Local dependency inspection identifies a mechanism consistent with that delay:
RouterBridge updater priority is 5, default main priority is 14, and long
responses use blocking Serial.write with repeated yield while a 64-byte FIFO
drains. A higher-priority ready writer can delay the lower-priority main loop.
The library also supplies a main-loop RPC fallback hook, so priority promotion
alone would not exclude serial response work from the control loop.

Uno **2026101106** is now recorded and flash-verified. In the MCSDK path:

- Control main priority is 4, above the dedicated RPC updater priority 5.
- Control releases ownership and sleeps 1 ms each iteration; it does not spin
  and starve RPC. The existing supervisory control rate is already 1 kHz.
- A strong application loop hook excludes synchronous RPC response work from
  control; legacy mode retains the vendor fallback. Renaming occurs before
  Arduino.h because UNO Q postvariant.h implicitly includes RouterBridge.
- Sensor worker priority is 4, outside control ownership, avoiding starvation
  during bulk replies. Sensor protocol and Wire bus settings are unchanged.
- There is no independent worker replaying ENABLE when control freezes.
- CRC, the actual 300-ms watchdog and Nucleo motor/PWM code are unchanged.

The first r1 compile stopped before deployment due to the implicit include
ordering; corrected r2 compiled successfully. The real transport watchdog under
a synthetic two-response schedule timed out in 100/100 old-priority cases and
passed 100/100 isolated cases with model gap <=54 ms. Actual control freeze and
sequence replay still failed as required. This is model/source evidence, not
an exclusive diagnosis or a measured 1106 bench improvement.

Updated-source regression **53/53 PASS** and candidate HMI guards **5/5 PASS**.
`../rpc_priority_fix/install_r1/report.json` records flash verification, but
remains **pass=false** because live RPC did not recover after the warm update.
The HMI and original calibration are preserved; no ARM, START, CLEAR or Nucleo
write was issued in these update/stress phases. The 1106 pair is explicitly
blocked from ordinary HV ARM pending validation. Only an Uno cold restart is
requested next; no new measured 1106 UART result is claimed yet.

## Current: 1105 Recorded, Warm RPC Recovery Pending

The powered idle attempt on 1104/1102 did not issue ARM or START. It archived
a pre-START break record (PA6 LOW, BIF set, MOE off, cached bus 0 V). One gated
CLEAR succeeded, with SAFE/fault=0 observed, followed by LINK_TIMEOUT on Nucleo
at sequence 218. CRC, UART hardware-error and RX-drop counters stayed zero.
This is a newly identified pre-RUN transport event, not proof of the cause of
the earlier powered motor MC_DP trip. See `../rx_trial_preparation/powered_idle_r1`.

A reproducible scheduling defect was then found: fault handling services STOP
at the 50-ms limiter, but healthy SAFE formerly used a separate 100-ms loop
schedule after optional work. In the same serialized owner, unqualified Uno
ADC readings were performed although MCSDK owns current control/protection.
With the previously observed 233-ms service-delay envelope, the real v3
watchdog reports timeout in 28/100 simulated phases; the corrected before/after
50-ms service schedule passes 100/100. CRC corruption and true >300-ms loss
still fail. This is a deterministic scheduling model, not an exclusive live
root-cause proof or a measured hardware failure probability.

Prepared and now flash-verified Uno Q **2026101105**:

- MCSDK SAFE UART servicing runs before optional work and after it, at 50 ms.
- Blocking Uno-local current ADC acquisition and voltage ADC fallback are
  excluded from the MCSDK supervision path. Current values remain explicitly
  unqualified/not acquired, not asserted as measured motor currents.
- All-state TX maximum/last enqueue gaps and >300-ms gap counts are exposed,
  addressing the older active-only counters' inability to observe SAFE stalls.
- Firmware watchdog/CRC/protection configuration remains unchanged.
- Nucleo 2026101102 was not programmed. No ARM, START or updater CLEAR was sent.

Candidate r2 is byte-identical in MCU source to the compiled r1; verified build
artifacts were copied only after full source equality. Image is 134164 bytes,
SHA256 `90e5ed006eb5ca2e4a0a1db9db688f9031095d0a60de463a9323d128a31e0e2d`.
Updated-source regression 52/52 PASS and candidate HMI guards 5/5 PASS.
HMI SHA256 `63df189d3747a684a4cb009a6054b7bc747eb8958ff5ba8d060630e598c6b464`.
The new pair is deliberately blocked from ordinary HV ARM pending validation,
even with a calibration override; no powered attestation was transferred to it.

The operator confirmed mains/J4 off, meter <=2 V and Uno USB connected. Current
pre-write telemetry was 0 V, SAFE and output-off. The updater accepts only this
zero-bus state with a known archived timeout or undervoltage context. The prior
temporary <=5-V maintenance variant was tightened to <=2 V before use.

Flash verification passed, but the live RPC identity did not recover within
the bounded wait. An additional **verification/restart only**, without another
flash write, also passed. Linux HMI/router remained available but MCU RPC did
not yet answer. Accordingly `../idle_deadline_fix/install_r1/report.json` is
explicitly **pass=false** despite `uno_flash_verified=true`.
GPIO readiness was inspected read-only; no guessed GPIO/reset/service changes
were performed. Loader/RPC recovery is unresolved, not presumed to be caused
by the scheduling patch. A full Uno-only cold power cycle is requested before
further live classification. No subsequent communication or motor qualification
is claimed. The calibration file's stored captures and identity were untouched.

## Follow-up: Short Trial Preparation

After operator authorization, the known programming-pause watchdog was
acknowledged once with CLEAR over Wi-Fi. Diagnostics/logs were archived first;
the dedicated first-break RAM record survived unchanged. `bp_bad_cnt` and
`bp_transport_fault` are now zero. Zero-bus MCSDK undervoltage remains visible,
including its occurred-fault history; it was not waived as a powered RUN state.
The subsequent 40-second idle test received 421 new good replies and no new
transport errors. See `../rx_trial_preparation/clear_r1` and `idle_after_clear_r1`.

The live HMI was updated over pinned Wi-Fi SSH without rewriting either MCU:
SHA256 `746e115881494312f2f2b414d1d3108199a69debb7ff90dfad78e7aec2fcb1cc`.
An explicit calibration compatibility entry for 2026101104/2026101102 was
added only after source/measurement-contract review. The original calibration
file, capture identities and measured values were preserved byte-for-byte.
Unknown IDs/contracts still fail compatibility, and the new pair requires
an explicitly prepared short-trial gate even with valid calibration.

The following checks passed (`../rx_trial_preparation/install_prepare_r1`):

- SWD HOTPLUG reads, without reset/halt/programming: TIM1 MOE=0, BKE=1, BIE=1,
  PA6 HIGH, and all six configured PWM pin input levels LOW.
- Full 44140-byte Nucleo flash readback matches the exact audited 1102 image.
- Existing Uno flash verification is retained; no new MCU image was written.
- Five unlinked PWM/DP function sections and the timer initializer are unchanged
  from the previously measured 1006 motor component. The break IRQ is explicitly
  **not** byte-identical: its source-audited change adds the first-event recorder.
- New gate tests: 85 cases, including wrong image/identity, missing evidence,
  dirty/absent RX counters, invalid calibration contract, 6 Hz, extended run
  duration and the 30-second coast profile. Existing candidate HMI guards 5/5
  and updated full offline regression 51/51 PASS, unchanged-source fingerprints.

One **5 Hz / at most 3 seconds** conditional trial is prepared, disarmed,
with a 600-second preparation lifetime. This uses explicitly labelled PWM
component-evidence transfer, not a claim of a new active-PWM measurement on
the complete 1104/1102 pair. Preparation sends MODE VF and SET FREQ 5, not
ARM or START. It grants no unrestricted HV operation or 30-second trial.
Live arming still requires fresh fault-free powered telemetry at 250..360 V,
30 seconds/100 new good replies, zero transport/RX errors and valid calibration.
Motor rotation and the original powered MC_DP cause remain unverified here.

Next operator step: remove both PC USB links and every analyzer lead from the
stand and supply the boards autonomously, leaving mains/J4 off. Powered idle
observation and a single operator-authorized START are separate subsequent steps.

That transition was subsequently confirmed by the operator. Wi-Fi initially
timed out during boot, then recovered without USB, deployment or a reset command.
The autonomous 30-second observation (`../rx_trial_preparation/autonomous_idle_r1`)
received 317 new correct replies across 42 samples, with zero new CRC, sequence,
diagnostic, RX-drop or hardware-UART errors. Outputs stayed disabled, bus 0 V.
The stored calibration was accepted on the current pair after this cold boot.

As expected, restarting Linux clears its temporary trial preparation; MCU
RAM records also naturally restart with power cycling. Previously captured
records remain archived, not asserted to survive loss of MCU power. The unused
preparation was restored via authenticated Wi-Fi HTTP only, using the audited
images/source and fresh autonomous idle evidence. The new helper's 15 offline
precondition checks passed; all previously fingerprinted regression sources
remain unchanged. See `../rx_trial_preparation/autonomous_prepare_r1/report.json`.
No ARM, START, flash, SWD read or fault acknowledgement was sent in this phase.
Next physical step is J4 15 V only; mains remains off until the next readback.

After operator-confirmed J4 power, `../rx_trial_preparation/j4_idle_r1` passed:
10 seconds, 15 HTTP samples, 102 new correct replies, no new UART errors.
Later readback showed bus 9 V, outputs disabled and HMI disarmed. The expected
MCSDK undervoltage remains visible; no CLEAR/ARM/START was sent. This is low-bus
telemetry, not a measurement of the actual J4 supply or powered-run readiness.
The next stage is powered idle observation with PC wired interfaces absent,
before any separate, explicitly authorized bounded START.

## Scope

This is a deenergized, output-off communication test. No START, CLEAR, active
PWM, motor trial, Nucleo programming or high-voltage approval is included.
The previous first-break record and rejected-message totals are archived,
not cleared to obtain a passing test.

## Observed Before Repair

Installed pair: Uno 2026101103 / Nucleo 2026101102.
The 30-second direct Wi-Fi GET-only baseline (`baseline_r1`) had 43 samples,
fresh UART throughout and two additional integrity rejects: 641 -> 643.
Sequence rejects and Nucleo-side rejects remained zero. The good-reply counter
was already saturated at 65535; it is not a valid count of new baseline replies.

## Source Defects And Repair

- Arduino Zephyr 0.90.0 Serial RX capacity is 64 bytes. The existing sender
  can emit an ordinary 43-byte response and a 43-byte diagnostic page together.
  The vendor handler ignores short `ring_buf_put` returns, losing bytes without
  reporting overflow. A deterministic delayed-drain 86-byte burst loses 22
  bytes with the original capacity and zero with the replacement capacity.
- Uno's snapshot RPC disabled interrupts while appending variable-length
  strings and allocating storage. Snapshot data is already serialized by the
  existing ControlMutex. Interrupt masking now only protects short timing and
  driver-counter snapshots, not string formatting.
- Application-local RX storage is 1024 bytes on the same physical UART;
  vendor package files, UART baud, framing, TX path and control CRC are unchanged.
- RX drops, UART hardware-error count/flags, queue high-water mark, maximum
  parser service gap and the last CRC-rejected raw frame are published through
  Wi-Fi. Counters saturate rather than wrap. CRC-invalid packets still reject.
- RPC initially reserves 4096 bytes instead of repeatedly growing from 160.

These are reproducible source defects. Their contribution to the observed
live failures must be assessed by the post-installation measurement, not
asserted from the synthetic queue test alone.

## Prepared Image

Uno Q 2026101104, 135484 bytes; verified target build succeeded.
Flash image SHA256:
`987a869e146e115ba9f526bf991e50cd461095f0c9448263f5502071b964e15f`.
Nucleo remains 2026101102. Candidate: `candidate_r1`.
The fixed buffer passed 10000 FIFO/wraparound burst cycles and overflow tests.
Existing safety/authentication/calibration HMI guard suites: 5/5 PASS.

The first installer attempt stopped before any hardware operation because its
manifest reader did not handle PowerShell's UTF-8 BOM. That reader was fixed;
regression was rerun against the updated source before retrying installation.

## Live Result

Installed Uno Q 2026101104; loader/sketch flash verification passed. Linux HMI
SHA256 is `1215d8aa6ec4683be0d2d321f1aefd277663095dbdd802b694ddc01bb1a0ee5f`.
RPC recovered without an additional user power cycle. Nucleo 2026101102 was
not programmed or reset. Calibration bytes were verified unchanged before
and after installation (`install_r1/report.json`). Full updated-source
regression: **50/50 suites PASS**, sources unchanged (`regression_r2`).

Measurements over direct Wi-Fi HTTP, with outputs disabled and bus 0 V:

| Measurement | Result |
| --- | --- |
| Main 180-second soak | PASS, 243 status samples, 1750 new correct replies |
| Stress client A, 60 seconds | PASS, 86 samples, no HTTP or new UART errors |
| Stress client B, 60 seconds | PASS, 91 samples, no HTTP or new UART errors |
| Combined elapsed observation | 226.123 seconds, 420 HTTP samples |
| Unique new ordinary replies | 1980 (116 -> 2096), overlapping clients not double-counted |
| New valid diagnostic pages | 863 (34 -> 897) |
| CRC / sequence rejects | 0 / 0 throughout all post-installation samples |
| Diagnostic rejects | 0 throughout |
| Software RX dropped bytes | 0 throughout |
| Hardware UART errors | 0 throughout |
| RX high-water mark | 86 bytes: greater than the previous 64-byte capacity |
| Maximum reported reply age | 53 ms |
| Maximum parser service gap | 233 ms (includes boot/installation period) |
| Maximum measured RPC formatting time | 3257 us |

The two stress clients overlap the end of the main soak and each other.
Their time and reply deltas must not be summed as independent exposure.
Normal and diagnostic framing remained intact under this increased read load.

The pre-flash ordinary rejection count was 645 and is archived in the installer
report. Uno's counters restarted naturally with the new image; the evidence
for improvement is the absence of new failures in measured post-installation
windows, not the counter resetting to zero. The first-break record remained
captured on Nucleo and was again received over Wi-Fi. The first-START-window
record remains explicit no-event.

Nucleo's link watchdog latched once during the intentional Uno programming
pause: `bp_bad_cnt=1`, `bp_transport_fault=7`. That record was not cleared and
the count stayed 1 throughout all subsequent samples. A passing communication
soak is not a passing RUN-readiness gate with that latched fault. No START,
CLEAR, active PWM or powered trial was sent.

This establishes a clean measured RX interval and eliminates two source
defects, not a guarantee of zero errors under every electrical/load condition.
The individual contributions of the buffer increase and IRQ-mask correction
were not separated by live ablation. It does not identify the cause of the
earlier powered MC_DP trip or qualify a new motor run.

## Reproduction

`tools/prepare_unoq_rx_fix.py` generates the isolated candidate from the
installed snapshot baseline. `tools/unoq_rx_fix_selftest.py` checks actual
storage and generated IRQ scope. `tools/install_unoq_rx_fix.py` checks source
and image hashes, archives before-state/logs, installs HMI and Uno only, and
verifies calibration plus live identities. Raw status/logs and summaries are
in `baseline_r1`, `fixed_soak_r1`, `stress_client_a`, `stress_client_b`.
The dirty older root sketch was not silently promoted or overwritten.
