# Autonomous 1108 Boot and Linux Fault History

## Completed Checks

The operator transferred Uno Q and Nucleo to powerbank supply, with mains/J4
left off and no PC/analyzer wiring as requested. Uno USB disappeared from ADB.
Linux boot ID changed from the previously observed
`242c06fe-ea2c-4c3f-a094-c8dfd1add5c9` to
`ad503d6b-dd6c-4f4c-8256-2d64a4b87edf`. Live firmware is Uno **2026101108** and
Nucleo **2026101102**. RPC returned after the reboot without another flash.

| Check | Result |
| --- | --- |
| Offline regression | 56/56 suites passed |
| New fault-history tests | 18 checks passed |
| Candidate HMI guard suites | 5/5 passed |
| Autonomous Wi-Fi collection | 120 s, 115 snapshots, 2399 new good messages |
| Maximum enqueue interval | 53177 us |
| Maximum parser polling gap | 5 ms |
| UART/CRC/sequence errors | Zero throughout observed run |
| Setpoint commands | 5 -> 20 -> 0 Hz confirmed, always PWM off |
| STOP | Acknowledged and output-off state confirmed |
| DC bus telemetry | 0 V throughout observed run |
| New fault fields in downloaded logs | Confirmed |

No ARM, START or CLEAR was sent. This validates autonomous boot and an idle
command path, not active PWM or a powered motor run.

## Logging Update

Only Linux `server.py` was changed over pinned-key Wi-Fi SSH. Both MCU images,
calibration and all actuator/gating code remained unchanged. The byte-identical
actuator section and exact two logging replacements were checked offline.
The history remains bounded to 64 samples and the existing 5-second post-fault
window.

19 existing telemetry fields are now retained in the fault context, including
UART enqueue intervals, >300-ms gap counts, parser delay, FIFO drops, hardware
UART flags, rejected-frame bytes, transport state and break-packet counters.
Brief changes in the relevant error counters now retain a history sample even
inside the normal 190-ms observation interval. This is passive logging; it
does not relax CRC, BKIN or watchdogs and does not replay control commands.

The first installation attempt timed out before any write during the operator's
power transition. Its failed report is retained in `install_r1/report.json`.
The actual installation in `install_r2/report.json` passed live checks, file
SHA verification and calibration preservation. Installed HMI SHA256:
`09fdbf9129c604c1f8fd995f94c92b98d4d90455b4a9ec95f27089210b8650a5`.

## Next Step and Limits

With autonomous supply retained, the next check is **15 V on J4 only**, mains
still off, and passive Wi-Fi observation. This is not permission for a mains
start. The earlier MC_DP event remains unresolved; the new logging is intended
to help separate UART stalls, software stop conditions and IPM protection.
AS5600 usable angle remains unqualified. The logger does not measure the J4
rail or qualified phase current and cannot uniquely distinguish driver
undervoltage, overcurrent and an SD disturbance.

Evidence: `autonomous_result.json`, `autonomous_wifi_r1/`,
`autonomous_commands_r1/`, `install_r2/`, `regression_r1/`, `hmi_guards_r1/`.
