# Powered Idle Wi-Fi Observation

## Scope

Operator reported mains applied. Acquisition used direct Wi-Fi HTTP GET only;
no ARM, START, CLEAR, firmware write, or HMI deployment was performed.
The host requested 30 seconds of observation and collected 30 status samples.
Raw timestamps are retained as reported by the host, without date correction.

## Measured Result

- Build identities: Uno Q 2026101108, Nucleo 2026101102 throughout.
- Reported DC bus: 323 V throughout; not a new multimeter measurement.
- State SAFE, PWM 0, HMI armed 0 throughout.
- Correct UART messages: 38645 -> 39242, increment 597.
- CRC/sequence counters, transport faults, UART hardware flags, Uno RX drops
  and hardware errors: zero throughout.
- UART telemetry age: maximum 45 ms.
- Cumulative sender maximum gap: 53646 us, unchanged during acquisition;
  no recorded gaps over the watchdog threshold.
- HTTP errors: none. Authenticated log download: 125 lines.
- Collector pass: true for its passive idle checks only.

## Remaining Restrictions

The short-trial preparation expired before this acquisition. All samples report
remaining time 0, ready 0, and `powered trial preparation expired`.
No preparation renewal or protection bypass was attempted on the energized bus.

The previously recorded MCSDK undervoltage fault remains latched:
bp_fault 5, reason 8, current/occurred masks 0x0004/0x0004.
These fields did not change. This is not a fault-clear or start-readiness pass.
First-since-boot break history does not prove absence of later physical pulses.

This run establishes passive communications continuity with mains applied.
It does not validate active PWM, phase current, physical protection latency,
rotor motion, or sustained powered operation. A new bounded trial must be
prepared under its existing low-bus constraints before a separate start.

## Evidence

- `status.jsonl`: all raw observations.
- `summary.json`: automated passive-check results.
- `logs.txt`: downloaded device logs.
