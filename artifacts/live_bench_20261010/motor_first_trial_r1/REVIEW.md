# First powered V/f response and UART failure review

Date: 2026-10-10 (Europe/Moscow).

## Observed outcome

- Operator explicitly authorized one START and subsequently reported shaft movement.
- Command path was Wi-Fi HTTP -> Uno Q -> UART -> Nucleo. No host USB or analyzer
  acquisition was used in this powered trial.
- Installed builds: Uno Q 2026100804, Nucleo 2026100801.
- Setpoint was 10 Hz. This was not a completed 10 Hz run or a measured speed test.
- Stored RUN snapshot at `ts=1791641274527` reports PWM=1, frequency=0.45 Hz,
  Vdc=319 V and no fault. The HMI fault-history snapshot at `ts=1791641274712`
  reports RUN, PWM=1, frequency=0.51 Hz and no fault.
- At `ts=1791641275035`, state=SAFE, PWM=0, Vdc=323 V and the controller's
  received-command bad counter had increased from 0 to 1.
- First cause was CRC, motor state at first fault was RUN (6), last valid command
  sequence was 5. Hardware UART flags and first-fault MCSDK current/occurred
  masks were all zero.
- STOP was acknowledged HTTP 200 / ok=true. Final snapshot is SAFE, PWM=0,
  estop=1 and HMI HV arm=0.

The timestamps are observed telemetry times, not interrupt timestamps. They do
not establish exact PWM duration or stop latency. `speed` is not an independently
measured shaft speed. Uno local ADC currents are unqualified; they cannot prove
the phase-current magnitude or absence of overload. Encoder validity was false.

## What the CRC event does and does not prove

The production Nucleo parser assembled a candidate command with a checksum
mismatch and stopped the drive. The bad frame's raw bytes were not included in
the saved telemetry. Therefore software stream synchronization, dropped bytes
and physical signal corruption cannot be distinguished from these logs alone.
Zero UART hardware flags do not prove an electrically clean link.

Uno reply-integrity counters and Nucleo command-integrity counters refer to
opposite directions. Uno reply-integrity=0 does not contradict a Nucleo CRC trip.
The first-fault sequence is the last accepted sequence, not a captured sequence
from the rejected frame.

After the operator reported shutdown/discharge, a read-only Wi-Fi snapshot
showed SAFE, PWM=0, HMI arm=0, reported Vdc=9 V, preserved first CRC, and Uno
reply sequence errors=23 (versus 0 at the powered trial). The time and cause of
those additional sequence errors are not established by a single later sample.
Reported ADC voltage is not a replacement for the operator's multimeter check.
No CLEAR, ARM, START, flashing or debug connection was issued during this review.

## Offline checks of unchanged production source

1. `../uart_production_regression_r1/report.json`: PASS, 412901 assertions;
   all 10 deliberate broken-code mutations detected.
2. `../uart_fifo_regression_r1/report.json`: PASS, 8994 cases / 86371 assertions;
   all four deliberate broken-code mutations detected.
3. `../uart_corruption_offline_r1/report.json`: audit PASS, 69680 cases /
   263280 assertions; removing the checksum guard is detected.
   **Checksum qualification FAIL**: 256 paired-bit corruption witnesses accepted.

These are host executions of the production functions with HAL/MCSDK mocks,
not a physical UART timing or EMI qualification. No production source was changed.

## Additional reproduced protocol weakness

Despite the CRC naming, protocol v2 computes an XOR of bytes. In a valid command
for 10000 millihertz, XORing both frequency bytes 6 and 7 with 0x40 changes the
frequency to 26448 millihertz. The original checksum byte remains valid. The
unchanged production parser accepts that changed target for all 256 sequence
values in the host test.

This is not asserted to be the cause of the observed CRC mismatch. It is a
separate integrity weakness requiring a versioned, coordinated protocol update
and regression tests, not removal or weakening of the existing guard. A genuine
CRC alone would not eliminate an electrical or framing source of corruption.

## Next qualification steps

- Keep powered restarts disabled while the transport fault is unresolved.
- With mains physically disconnected and discharge verified, use wired access
  for diagnostics/firmware work, not during an energized run.
- Preserve bounded copies of transmitted and rejected frames plus their timing
  in a reviewed diagnostic build, so bytes can be compared instead of guessing.
- Stage a coordinated stronger-integrity wire protocol with explicit version
  mismatch rejection; do not silently change checksum interpretation in v2.
- Repeat idle and low-voltage transport/PWM tests first. A future powered trial
  needs explicit operator authorization and its own bounded STOP handling.

Status: first shaft response observed; sustained operation and HV readiness
not qualified. Physical root cause of this CRC failure remains unresolved.
