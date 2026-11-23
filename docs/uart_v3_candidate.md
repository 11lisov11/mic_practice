# UART v3: CRC-32C and bounded NE handling

Status on 2026-10-10: installed low-voltage candidate, not an HV release.
The latest installed identities are Uno Q 2026101007 / Nucleo 2026101006.
The original production source (1002/801) is retained as the frozen baseline;
`prepare_uart_v3_candidate.py` generates the versioned candidate source.
Active source snapshots and binaries are in
`artifacts/live_bench_20261010/uart_v3_candidate/firmware_r6`.

## Live Update Result

Both boards were programmed and byte verification passed: Nucleo by full image
readback, Uno by loader/sketch flash verification. The saved calibration bytes
were unchanged. Commands and status qualification used Wi-Fi, not COM/UART/ADB
command forwarding. USB was used only for programming and low-voltage debugging.

Three integration bugs were found and fixed before accepting the live result:

- HMI string decoder discarded the added NE diagnostics; it now retains the
  fields and their `mc_*` aliases.
- Uno timing diagnostics assumed a 32-byte write and falsely counted every
  correct 43-byte frame as short. Candidate timing checks use `UV3_FRAME`.
- Transport watchdog manufactured LINK_TIMEOUT 300 ms after a valid latched
  ESTOP. A fault-latched owner now disarms that watchdog until clean CLEAR.
  Motor outputs remain latched OFF; normal RUN watchdog protection is unchanged.

The install report passed 30 seconds of idle UART/Wi-Fi observation.
The separate command test passed 5->20->0 Hz setpoint delivery, idle STOP,
explicit ESTOP held beyond 300 ms, and clean CLEAR. PWM was never activated.
Counter growth, CRC errors, sequence errors and short writes were zero in these
accepted runs. Those idle tests were not active PWM or powered NE tests.
Earlier failed reports are retained rather than rewritten.

Evidence: `install_estop_fix_r1/report.json`, `wifi_idle_commands_r3/report.json`,
`regression_r7/report.json` under the same artifact directory. The HMI keeps
HV arming blocked for the installed candidate by default. The subsequent
zero-bus PWM qualification passed all eight named scenarios, including complete
Wi-Fi active updates/STOP and a software TIM1 Break; see `PWM_RESULT.md` in
the same artifact directory. Six image-matched passed cases were reused.

## Physical Evidence

The 3-second powered V/f trial completed with operator-confirmed shaft rotation.
The later 15-second trial stopped at about 2.75 seconds with UART_RX_ERROR and
NE=0x04; MCSDK current/occurred masks in that snapshot were zero. The actual
rejected byte and its correctness were not captured. This does not prove bad
wiring, nor does it prove that accepting the byte would have been safe.

ST describes majority sampling and noise indication in
[RM0440](https://www.st.com/resource/en/reference_manual/rm0440-stm32g4-series-advanced-armbased-32bit-mcus-stmicroelectronics.pdf).
The candidate does not disable noise detection or enable ONEBIT sampling.

## Candidate Contract

Both directions use 43-byte frames. Version is 3; command/reply headers and the
first 31 payload bytes retain their previous positions. Bytes 31-38 extend the
payload; bytes 39-42 carry CRC-32C in little-endian order. CRC covers bytes 0-38,
including header, version and sequence. Command extension bytes must be zero.
There is no on-wire fallback to XOR or protocol v2.

CRC-32C uses reflected polynomial 0x82f63b78, initial value 0xffffffff and final
inversion. Four independent published test vectors from
[RFC 3720, Appendix B.4](https://www.rfc-editor.org/rfc/rfc3720#appendix-B.4)
are checked, as is the standard `123456789` check string.

NE tolerance requires all of the following:

- Complete frame received within 15 ms, with correct CRC and version.
- Exactly one byte marked NE, with no PE, FE, ORE or unknown error flags.
- Actual preceding MCSDK state RUN, not merely a requested start.
- Three consecutive clean sequential frames of the same running command.
- Identical command bytes except the sequence; no new frequency, mode or service output.
- Next sequence modulo 256, including correct wrap from 255 to 0.
- Fewer than two previously accepted NE frames in the sliding 1000-ms window.

After accepting NE, three new clean frames are required. The third NE frame
within a second stops the drive. NE cannot authorize first start or CLEAR.
STOP and ESTOP are not delayed to wait for a clean recovery sequence; a noisy
STOP/ESTOP frame also causes a latched stop rather than continued operation.

CRC failure, wrong version, out-of-order RUN sequence, hard UART errors, orphan
NE without an available byte, frame deadline and software queue overflow remain
fail-closed. The 300-ms link watchdog is unchanged and cannot be refreshed by
partial or rejected frames. Latched faults cannot be cleared by ENABLE.
Only an explicit clean safe-off CLEAR can release the latch; it does not start
the motor or bypass a sustained physical break input.

Hardware UART FIFO is disabled in the candidate. ISR snapshots accompany each
RDR byte into the existing 128-entry software ring. Both byte and marks are
published before advancing the producer index. Fatal errors invalidate pending
commands before control API calls. Hardware ISR timing still needs physical
qualification after installation.

Reply extension:

| Bytes | Field |
| --- | --- |
| 31-32 | Accepted NE frames, saturating uint16 |
| 33-34 | NE-marked bytes consumed by the parser, saturating uint16 |
| 35 | Clean RUN recovery frame count |
| 36 | Noise budget entries |
| 37 | Most recent parser sample/frame UART flags |
| 38 | Latched transport fault reason |

Uno exposes `bp_ne_accepted`, `bp_ne_observed`, `bp_ne_flags` and
`bp_transport_fault` in its existing status stream. The original first/last
fault fields and MCSDK masks remain available. Accepted noise is not counted
as a corrupted command, but is not hidden from telemetry either.

## Offline Verification

The integrated host test uses generated candidate ISR/parser/queue and the
production MCSDK semantic handler with HAL/MCSDK mocks. It tests all single and
double bit flips of a representative frame, selected short burst shapes, the
existing XOR-collision witness, all 256x256 RUN sequence transitions, flag
combinations, queue wrap, insertions/deletions, deadlines, latch behavior and
voltage/break/API failure guards. These are finite tests, not an exhaustive
enumeration of all physical error patterns.

Latest integrated run: 204,552 cases, 619,694 assertions, eight deliberately
broken implementations detected. On identical synthetic intact-NE inputs,
11,008 eligible cases continued RUN; the strict CRC32C baseline rejected those
same 11,008 cases. This is a conditional software result, not a measured
improvement on the powered stand.

Uno peer tests exercise the generated parser and fault decoder, rejecting
single-bit reply corruption, stale sequence, wrong version and mixed replies
across restart. Serial/RPC state is mocked. Correct header resynchronization
after a lone header byte is intentionally accepted.

ARM builds for both targets are generated separately. Six critical PWM/break
object-code sections and TIM1 initializer are compared against production;
matching sections do not prove complete timing equivalence of the firmware.

## Reproduce

From the repository root, with fresh output directories:

```powershell
.venv/Scripts/python.exe tools/uart_v3_candidate_selftest.py --integrated --outdir artifacts/uart_v3_test
.venv/Scripts/python.exe tools/uart_v3_uno_peer_selftest.py --outdir artifacts/uart_v3_peer_test
.venv/Scripts/python.exe tools/prepare_uart_v3_candidate.py --outdir artifacts/uart_v3_firmware
powershell -File tools/build_unoq_mcsdk_scalar.ps1 -Sketch artifacts/uart_v3_firmware/UNOQ_MOTOR -OutputDirectory artifacts/uart_v3_firmware/uno_build
powershell -File tools/build_acim_reference.ps1 -ProjectRoot artifacts/uart_v3_firmware/nucleo -Workspace artifacts/uart_v3_cube_workspace
.venv/Scripts/python.exe tools/uart_update_regression.py --baseline-source artifacts/current_pwm_20261008/uart_guard_801/baseline/main_708.c --outdir artifacts/uart_v3_regression
```

These tools do not upload, actuate, connect to a board or modify the production
source. Destination preparation refuses an existing output directory.

## Remaining Gates

Every subsequent installation still requires disconnected mains, J4 off and
a discharged bus. Compatible peer versions must be kept together. The HMI now
recognizes the exact installed measurement contract without rewriting saved
points, but explicitly refuses HV arming for this candidate.

Idle Wi-Fi/RPC/UART, restart boundaries, low-voltage PWM and captured
STOP/ESTOP/run-limit behavior have passed. The software TIM1 Break capture is
not a physical PA6/IPM fault measurement. Noise tolerance is not a substitute
for tracing supply/reference/timing/EMI problems. No further powered trial is
approved by the offline results alone.

The 8-bit sequence cannot identify a long-delayed valid replay after a full
wrap; CRC is not authentication. The candidate is not a certified safety
protocol. Current and encoder telemetry limitations from previous powered tests
are not fixed by this transport change.

## One-Shot Powered Trial

The normal HV block stays in place. An authenticated `/api/powered-trial`
preparation request can install an in-memory, one-use trial gate for exactly
1007/1006. Preparation requires a discharged, disarmed stand and a fresh host
attestation derived from retained eight-case PWM evidence, verified image
hashes, the trial-aware offline regression and post-restoration idle evidence.
The attestation records evidence SHA-256 values; it is not a signature,
certification, fresh MCU flash readback, or general permission to use HV.

The gate then requires 30 seconds of fault-free powered idle observations,
at least 20 distinct advancing-counter samples and 100 new valid UART frames.
An observation gap over two seconds, restart, invalid calibration or unhealthy
telemetry resets the observation window. The encoded bus word and scaled
readings must agree, bus readings must be 250..360 V, and telemetry ages <300 ms.
No START is sent by preparation or by the observation phase. A specifically
identified idle undervoltage may be acknowledged once only when explicitly
requested; other faults are never automatically cleared.

Only V/f targets in (0,10] Hz are allowed. The START endpoint applies a limit
of at most 3 seconds to the Uno MCU before sending START, even when the caller
omits a requested limit. An independent HMI deadline also stops the trial.
Permission is consumed before START, including a lost/rejected START reply.
Re-arming, replacing the permission and changing profiles cannot authorize a
second trial in the same HMI session. Ordinary commands cannot raise the run
limit or select FOC/service outputs while the trial gate exists. STOP remains
available without a control token. A normal deadline uses confirmed STOP;
unconfirmed STOP and actual protection failures retain the ESTOP escalation.

The trial preparation is lost on HMI/Linux restart. Prepare after establishing
autonomous power, with the bus still discharged, before any powered test.
Preparation lifetime is bounded by the host attestation's remaining validity
(at most one hour), tracked with a monotonic clock and exposed in telemetry.
This replaces the initial arbitrary 10-minute preparation timer, which expired
before the first attempted run. That attempt sent no ARM or START. The 10-second
ARM window, 30-second fresh powered observation and 3-second run limit are
separate constraints and remain unchanged. An expired preparation fails promptly
instead of waiting through the entire observation timeout.
The existing one-second idle watchdog reads also feed the observation gate,
without extra polling or actuation. A pause in the browser/chat no longer
discards a window that is continuously validated on the board; missing or bad
RPC telemetry still resets it. An observation never extends the attestation's
monotonic preparation deadline.
Preparation may retain a previously recorded DP occurrence alongside a first
undervoltage snapshot on a discharged bus. This sends no CLEAR/ACK/ARM, does
not establish that DP is harmless, and does not relax the powered fault-free
window. The client's automatic undervoltage-only acknowledgement still refuses
such combined history; it must be inspected separately before any acknowledgement.
No USB or Saleae connection to the PC may remain during a powered test.
The `run` phase requires explicit operator-ready confirmation; these tools
cannot independently verify physical wiring, guarded contacts or motor mounting.

Tools (all output directories must be new):

```powershell
.venv/Scripts/python.exe tools/prepare_powered_trial.py --pwm artifacts/live_bench_20261010/uart_v3_candidate/active_pwm_r5/report.json --offline artifacts/live_bench_20261010/uart_v3_candidate/powered_trial_regression_r2/report.json --idle artifacts/live_bench_20261010/uart_v3_candidate/post_pwm_idle_r1/summary.json --physical artifacts/live_bench_20261010/uart_v3_candidate/post_pwm_idle_r1/physical_idle.json --out artifacts/trial_attestation.json
.venv/Scripts/python.exe tools/wifi_uart_v3_trial.py prepare --qualification artifacts/trial_attestation.json --token-file .unoq_ssh/control_token --outdir artifacts/trial_prepare
.venv/Scripts/python.exe tools/wifi_uart_v3_trial.py observe --ack-undervoltage --token-file .unoq_ssh/control_token --outdir artifacts/trial_powered_idle
.venv/Scripts/python.exe tools/wifi_uart_v3_trial.py run --confirm-autonomous-ready --token-file .unoq_ssh/control_token --outdir artifacts/trial_run
.venv/Scripts/python.exe tools/wifi_uart_v3_trial.py cancel --token-file .unoq_ssh/control_token --outdir artifacts/trial_cancel
```

Do not execute the powered phases as an unattended sequence. An accepted START
and controller PWM telemetry do not establish physical shaft rotation or
accurate phase-current measurement. Inspect the fault snapshots/logs and the
operator's observations before planning any longer trial.
