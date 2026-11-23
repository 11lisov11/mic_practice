# UNO Q 1108: Boot Recovery and Idle Wi-Fi Qualification

## Subsequent Autonomous Verification

1108 subsequently recovered RPC after a full Linux reboot on operator-reported
powerbank supply. The autonomous 120-second test, 5 -> 20 -> 0 Hz commands and
STOP passed with PWM off. A Linux-only fault-history addition was installed
over Wi-Fi without MCU writes or calibration changes. Details and remaining
powered-test limits are in `../fault_context_fix/REPORT.md`; the sections below
retain the earlier USB-powered run and its then-current limitations.

## Result

Uno **2026101108** is installed, flash-verified and responding over native
Wi-Fi HTTP. Nucleo **2026101102** was not programmed. Calibration SHA256 is
unchanged. All observed outputs remained off. No ARM, START or CLEAR was sent.

| Check | Observed result |
| --- | --- |
| Offline regression | 55/55 suites passed |
| Target ELF TLS check | Passed; 2381 relocations inspected |
| Flash predecessor/new image readback | Both verified |
| Idle native Wi-Fi collection | 120 s, 114 snapshots, 2391 new good replies |
| Overlapping Wi-Fi reader | 30 s, 43 snapshots, passed |
| Setpoints / STOP over Wi-Fi | 5 -> 20 -> 0 Hz / STOP confirmed, PWM remained off |
| CRC, sequence, RX overflow, UART hardware errors | Zero throughout observed window |
| Maximum UART enqueue interval | 53658 us |
| Maximum parser polling gap | 5 ms |
| Enqueue intervals above 300-ms watchdog | Zero |
| AS5600 reads during main collection | 45954 new reads; no I2C errors |
| AS5600 usable angle | Not qualified: enc_ok=0 |

The observed maximum enqueue interval fell from **290460 us** on the earlier
1105 idle run to **53658 us** here, a reduction of **81.53%**. These are separate
bench runs, not a statistical reliability bound or a powered-operation result.
The overlapping reader's 603 replies are part of the same UART stream and
must not be added to the main run's 2391 replies.

## Diagnosis and Repair

The operator's cold restart did not restore 1106 RPC. An initial boot-order
candidate 1107 compiled and verified but also did not expose live RPC.
Its failure is retained in `../bridge_boot_fix/install_r1/report.json`.

A halted/resumed debug snapshot showed main thread state 0x08 (dead), priority
14, and the CPU idle in the verified loader. The new priority assignment had
not executed. ELF comparison then exposed a new `z_tls_current` reference and
`R_ARM_TLS_LE32` relocation introduced by `k_current_get()` in 1106/1107.

1108 uses exported `k_sched_current_thread_query()` instead of that TLS-backed
inline helper. It retains the early priority assignment, isolated RPC updater,
1-ms supervisory sleep and off-only Bridge recovery. No motor-control,
300-ms transport watchdog, CRC, BKIN or current-protection setting was relaxed.
The replacement removes the TLS relocations, and actual RPC boot recovery
succeeded without another operator cold restart.

`tools/unoq_llext_check.py` parses ELF relocation sections using pyelftools.
The build script now rejects this TLS defect before exporting release images.
The check rejects both historical failing images and accepts the previously
loading 1105 image. It is a targeted compatibility check, not a universal
proof of loader compatibility. Future powered/start qualification is separate.

## Evidence and Limits

- `install_r1/report.json`: predecessor verification, new flash verification,
  live 1108/1102 response and unchanged calibration.
- `regression_r1/report.json`: exact source fingerprints and 55-suite result.
- `candidate_r1/uno_build/llext-check.json`: actual compiled ELF check.
- `idle_wifi_r1/`: raw status, logs and 120-second summary.
- `concurrent_wifi_r1/`: overlapping read-only client evidence.
- `idle_commands_r1/`: setpoint replies, output-off snapshots and STOP.
- `timing_summary.json`: timing/counter aggregation.

DC bus was 0 V in telemetry; mains and J4 were physically confirmed off before
writing. The undervoltage fault on Nucleo is expected in this off-only test;
it was not cleared or suppressed. AS5600 communication is alive but its angle
validity remains false. Full Linux/MCU cold boot of 1108 has not yet been tested.
Active PWM, powered EMI, the earlier MC_DP trip and 30-second motor operation
are **not qualified** by this report. Ordinary HV ARM remains blocked for this
new pair; no powered release or calibration identity migration was made.
