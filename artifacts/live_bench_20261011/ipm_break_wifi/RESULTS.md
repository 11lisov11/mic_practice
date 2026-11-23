# Passive diagnostic pair: installation and Wi-Fi capture

Follow-up: Uno RX repair 2026101104 is now installed with unchanged Nucleo
2026101102. A 226-second combined Wi-Fi observation recorded 1980 ordinary
replies and 863 diagnostic pages without new CRC errors or dropped bytes.
See `../uart_rx_fix/RESULTS.md` for current state; the text below is the
preserved pre-repair history. No powered release was granted by either test.

## Current Result

Both images are now installed: Uno Q 2026101103 and Nucleo 2026101102.
Nucleo write/read verification passed; the Uno image was verified and restarted
without rewriting flash. Linux HMI was repaired to remove competing text-UART
fallback in router mode. Calibration bytes remain unchanged.

Final source regression: **49/49 suites PASS** (`full_regression_r8`). MCU
sources/images are unchanged from candidate r4; candidate r6 updates HMI only.
The existing images were reused only after byte-identical source and artifact
hash checks. The refresh helper's redundant per-file whole-tree hash scan was
also fixed; incomplete candidate r5 is not the installation source.

The cold restart initially exposed an unavailable RPC bridge. Evidence:
router startup registered no `cmd/get` methods, while HMI's text fallback
opened the router-owned `/dev/ttyHS1` and generated invalid MsgPack packets.
The fallback was removed, tested in 12 ownership cases and installed through
owned-process, HMI-only recovery with preserved calibration. An unchanged-image
MCU restart then restored RPC. A further full cold boot with this fix has not
yet been independently qualified. The inspected loader header has flags 0,
so the wait-for-App flag was not the explanation; see the official
[Arduino 0.90.0 loader](https://github.com/arduino/ArduinoCore-zephyr/blob/0.90.0/loader/main.c).

## Real Snapshot Test

With mains and J4 off, bus reported 0 V, Wi-Fi SAFE, and TIM1 MOE already off:

- Readback before injection: DIER `0x80`, BDTR `0x02333872`, GPIOA IDR `0xC044`.
- One software `TIM1.EGR.BG` event was generated, with no START command.
- Authenticated Wi-Fi GET returned a committed 92-byte first-break record.
- BIF=1, B2IF=0, PA6 HIGH at IRQ, BKE=1, MOE=0, START window=0.
- Record tick 185624 ms, cached context tick 185494 ms: context age **130 ms**.
- Cached reference 0, Vbus 0 V, temperature 30 C, MCSDK current/occurred masks
  4/4 from the preceding telemetry sample, not instantaneous trip masks.
- After injection BDTR was still `0x02333872`; DIER became 0, confirming the
  existing break IRQ masking path while hardware BKE remained enabled.
- `IPM_BREAK_SNAPSHOT` with the complete raw record exists in downloaded logs.
- The first-START-window record remains explicit no-event; no START occurred.

This proves the real software-event path **TIM1 break IRQ -> RAM -> UART ->
Uno RPC -> Wi-Fi -> persisted HMI log**, while outputs were already disabled.
It is not an external SD/PA6 hardware-edge test or active PWM shutdown test.
The induced diagnostic event is intentionally labelled software BG; it cannot
be used to infer the physical cause of the earlier powered MC_DP event.
The test record/fault was not cleared or reset afterwards.

## Remaining Blocker

UART receive integrity is still not qualified. The paired 20-second test had
272 correct replies but an integrity count increase **6 -> 7**. Later the
count reached 12; a final 5-second read-only window had 63 correct replies and
no additional increase (12 -> 12). Nucleo's own bad count stayed at zero after
its image update; the rejects are observed on Uno's receive side.
Diagnostic pages are also occasionally rejected (4 at the recorded API read).
No statement that all communication is error-free is justified.

Installation safety and operational readiness are now separate: physically
deenergized maintenance permits bounded historical rejects only with stable
pre-write counters, fresh <=2-V telemetry and outputs off. Counters are retained,
and strict operational qualification is still **false**. MCU CRC checks, noise
budget, watchdogs, BKE and protection thresholds have not been weakened.

Next debugging step is capture of the actual rejected reply bytes and receive
timing/overflow information, followed by a clean paired soak. Another powered
run is not approved. The original MC_DP cause remains unidentified.

Current evidence: `install_r7/report.json`, `paired_idle_r1/summary.json`,
`bg_snapshot_wifi_r1/status.jsonl`, `bg_snapshot_wifi_r1/logs.txt` (snapshot entry),
`full_regression_r8/report.json`, candidate r6 manifest. The earlier partial
installation history below is retained as historical evidence, not current state.

## Earlier Preparation And Handover

## Completed

- Matched snapshot protocol, Nucleo sender, Uno assembler/RPC publication,
  authenticated read-only Wi-Fi endpoint and automatic HMI fault-snapshot logs.
- Partial/mixed/CRC-damaged records are rejected; no control ACK or watchdog
  timestamp is refreshed by diagnostic traffic.
- Fixed cache invalidation after a saturated Nucleo packet counter decreases.
- Final full regression: **48/48 suites PASS**, unchanged sources during tests.
- Pair suite: 388 control + 381 transport + 10 emitter + 21 HMI/HTTP cases;
  CRC-removal negative control detected. These are host checks, not motor trials.
- Prepared HMI additionally passes five existing safety/auth/calibration suites.
- Both target images built successfully. Nucleo final compile/link has
  0 errors/0 warnings; initial empty-directory clean messages are retained.

## Installation State

- Linux HMI installed over pinned SSH/SFTP on port 2222; verified.
- Uno Q **2026101103** flashed and verified in one OpenOCD session.
- Nucleo is still **2026101006**, not the prepared 2026101102.
- Internal RPC has recovered and reports the new Uno identity.
- Nucleo latched the expected link watchdog during the Uno flashing pause.
  Uno has one historical integrity rejection. No attempt was made to CLEAR
  or hide either counter to obtain a passing readiness result.
- Joint cold reboot requested. Installer will resume with Nucleo only after
  clean output-off telemetry; no repeated Uno upload is needed.
- **No START, CLEAR or powered trial was performed.**

The first installer failure was strict rejection of the archived undervoltage/
DP context on a discharged stand. Maintenance-only handling was then added,
with tests. The next failure was initially labelled RPC recovery failure, but
the retained telemetry proves RPC recovered: it was the legacy UART watchdog
gate. Classification and transition handling were corrected. The remaining
integrity count is not waived; it requires the requested clean startup.

## Passive Hardware Observation

After the Uno update, a 5-second Wi-Fi GET-only collection produced 5 samples
and **72 new correct messages** (5196 -> 5268). Integrity rejection stayed
at 1, sequence rejection at 0; no new errors. Outputs remained off, bus within
the 2-V gate. This is the intermediate pair, so detailed snapshots are not yet
available from Nucleo. It is not end-to-end qualification of the matched pair.

Calibration SHA256 after the Uno write:
`a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17`.
Bytes are unchanged. The new identities are not yet qualified for HV; no
calibration values were recaptured or silently retagged.

## Prepared Images

- Uno flash image SHA256:
  `cdc76b8d98a11789023f39fb6dfa6dd2f5c803ee28ea8017327b6639d19e9a69`.
- Nucleo BIN: 44140 bytes, SHA256:
  `d17b1ed8313b7e355e66681f90beaf84e7535e22504212f79ef44ce2bad5d37c`.
- Nucleo image has **not** been written yet.

## Remaining

Complete Nucleo write after joint reboot, collect matched-pair Wi-Fi records,
then qualify the real first-event snapshot on an isolated low-voltage setup.
The cause of the previous powered MC_DP trip at approximately 5.516 seconds
remains unknown. The 50-Hz / 30-second motor trial did not complete and must
not be described as successful. This update is not approval to repeat it.

## Evidence

- `full_regression_r4/report.json`
- `full_regression_r4/ipm_break_wifi_selftest/report.json`
- `hmi_guards_r3/report.json`
- `candidate_r4/manifest.json` and both target build manifests
- `install_r2/hmi_deploy/report.json`, `flash_verify_uno.log`, `before_wifi_logs.txt`
- `install_r3/report.json`: current UART fault gate (no flashing performed)
- `intermediate_idle_r1/summary.json`, `status.jsonl`, `logs.txt`
- Resume procedure: repository `docs/ipm_break_wifi_diagnostics.md`
