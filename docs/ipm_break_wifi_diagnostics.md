# Passive IPM break diagnostics over Wi-Fi

## Matched Candidate

Candidate: `artifacts/live_bench_20261011/ipm_break_wifi/candidate_r6` (r4 MCU
images reused after byte-identical-source verification; r6 updates HMI only).
Uno Q build 2026101103, Nucleo build 2026101102. The MCU and HMI components
must be treated as one diagnostic package, not as an HV release.

Both MCU images and HMI are installed and verified. A software BG event with
MOE already off produced a real IRQ snapshot delivered over Wi-Fi and logged.
No START or CLEAR was issued. Operational qualification is still blocked by
intermittent Uno receive integrity rejections; no powered run is approved.

## Packet Format

Normal v3 commands/replies remain 43 bytes, with unchanged CRC, sequence rules,
noise budget, watchdogs, service fields and safety thresholds. The diagnostic
packet is also 43 bytes but has a distinct version tag and cannot act as a
normal control ACK:

| Bytes | Value |
| --- | --- |
| 0..1 | 55 AA |
| 2 | D1, passive diagnostics v1 |
| 3 | Record kind: first since boot / first START request window |
| 4..5 | Page index 0..3 / total pages 4 |
| 6..9 | Exact Nucleo firmware ID, little-endian |
| 10..13 | CRC32C of the complete 92-byte record |
| 14..37 | Up to 24 record bytes, zero-padded on the last page |
| 38 | Reserved, zero |
| 39..42 | CRC32C of bytes 0..38 |

Nucleo sends at most one page per 200 ms after a successful ordinary reply,
only with command enable false, START window closed, MOE disabled and MCSDK
not in RUN. A nominal full rotation through two records takes 1.6 seconds.
This is not an ISR-time streaming channel.

Uno checks the complete packet CRC, exact peer ID, fresh ordinary off-state
telemetry, page metadata, padding, whole-record CRC and record ABI. Partial,
expired, conflicting or mixed records do not replace a published record.
Counters decreasing on the ordinary channel reset the diagnostic cache:
Nucleo's good counter saturates, so a decrease is not a natural wrap.
Diagnostics never acknowledge control commands or refresh their timestamps.
A malformed diagnostic envelope with failed CRC still increments the ordinary
integrity rejection count; the diagnostic route does not hide control damage.

## HTTP And Logs

`GET /api/break-snapshot` requires the existing control key. It returns decoded
records, raw registers, cached context, age and interpretation limits.
It does not send a command or update the operator heartbeat. Complete captured
records also produce `IPM_BREAK_SNAPSHOT` entries in downloadable HMI logs.
Explicit zero records mean no recorded event; absence/stale data means unknown,
not absence of a fault.

The reference-frequency decoder is specific to this frozen one-pole-pair,
SPEED_UNIT=10 project. It is not measured rotor speed. PA6 is sampled at IRQ
entry, not the electrical edge. There is no qualified phase-current or J4
supply measurement, and no unique inference of overcurrent versus driver
undervoltage or interference.

## Verification And Installation

Offline final regression: 49/49 suites pass. Wire/HTTP suite includes 388
control-parser scenarios, 381 transport scenarios, 10 real-emitter host cases,
and 21 HMI/HTTP checks, plus a CRC-removal negative control. Five existing HMI
guard/authentication/calibration suites also pass against the prepared server.
Physical UART timing under active PWM and a new recorded external SD event
remain unqualified; these results do not authorize a powered motor run.

For future maintenance only, with mains/J4 off and the bus discharged, the exact
USB serials, image hashes and fresh output-off state are checked before writing.
Do not rerun solely to erase error history or obtain a readiness pass:

```powershell
.venv/Scripts/python.exe tools/install_ipm_break_wifi_pair.py --candidate artifacts/live_bench_20261011/ipm_break_wifi/candidate_r6 --regression artifacts/live_bench_20261011/ipm_break_wifi/full_regression_r8/report.json --outdir artifacts/live_bench_20261011/ipm_break_wifi/install_next --confirm-mains-j4-off
```

The installer resumes from 2026101103/2026101006 without flashing Uno again.
It permits a narrowly identified legacy undervoltage snapshot or expected
flash-pause timeout for deenergized maintenance. Historical integrity rejects
may be retained only in maintenance mode with stable pre-write counters; they
still fail strict operational qualification. Increasing counters, active
outputs, stale measurements or a bus over 2 V abort programming.
This is not the motor RUN gate. Saved fault evidence is exported before MCU
replacement, and calibration file bytes are preserved. No automatic CLEAR or
START occurs. New identities remain outside the powered-trial allowlist.

In router mode, HMI never creates a competing text serial client for ttyHS1.
Explicit serial mode is still supported only when deliberately selected.
HMI-only recovery checks the current and candidate hashes, owned UID/PID/CWD,
keeps a backup, atomically replaces the server and preserves calibration.
It requires physical mains/J4-off confirmation and does not assert RPC recovery
or operational readiness merely because the process restarted.
