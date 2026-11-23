# Uno Q Access And Recovery Runbook, 2026-10-12

## Verified Access

CURRENT 2026-10-15: manual r3 Uno1505/Nuc1504 remains installed. Basic actual5->10->5Hz
PASS, visible smooth rotation/acceleration/deceleration confirmed by user. Active session
observed beyond old30s ARM TTL; UART fatal/bad/CRC/sequence0. Extension toward20Hz
tripped runtime TIM1 Break / MC_DP_FAULT0x0400 at last active12.6/cached12.7Hz,
not a UART timeout. 20/50Hz NOT reached or qualified. STOP/PWM0/ARM0 confirmed,
fault latched, no post-fault CLEAR/retry. User asked why OFF; log reading does not need
power OFF. Mains/J4 remain ON, stand closed, both powerbank, PCUSB and ALL Saleae
probes/GND removed, motor connected. Stopped powered10.969s/+221 fresh replies,
outputs OFF, bus318, fault retained. This is not power-removal qualification.
User has only the existing Saleae. Do not connect it between energized HOT_GND and PC USB.
Arduino's USB host path cannot run official Saleae Logic on ARM Uno Q. Proposed next route
is an on-Nucleo PA6/BKIN DMA ring buffer with passive Wi-Fi readout after Break; see
`artifacts/live_bench_20261015/manual_scalar_working_pair_r3/hardware_review/next_step_sd_capture_ru.md`.
Not yet implemented/built. One Nucleo flash requires power off and independently safe DC bus;
reading the current logs does not. Single PA6HIGH at ISR and43ms-old cached context cannot
identify physical cause. No qualified phase current/J4.
Static V/f threshold10Hz has20->35.921Vpeak discontinuity; causality unproven, no source
change based on it. Original calibration unchanged. See r3/hardware_review summary
and current CHAT_HANDOFF. Do not START/CLEAR automatically or reflash on energized stand.

INSTALLATION CHECKPOINT 2026-10-15: installed manual r3 Uno1505/Nuc1504; both writes verified, full Nuc readback
matches. Actual VF_OL reference getter corrected, actual segment-completion guard corrected.
HMI0c6f750862b1425a25b9e3a12a3cdff74128fe2688e759c1be8fa02e6e595118; original calibration SHA
unchanged. After PCUSB cold boot methodget unavailable was recovered by verified-only reset
of existing Uno image (no flash writes, no cable reconnect). Then final r3 programmed.
One archived programming timeout acknowledged under confirmed OFF/meter<20. Fresh SAFE/PWM0/
ARM0/fault0/Vbus10/transport0/bad0/reference0valid1. Eight idle samples7.703s/+154 responses.
At this installation checkpoint awaiting fresh user transfer-to-powerbank + PCUSB/Saleaeprobes/GNDremoved + powerON
reply for new5->10->5 run. Motor stays connected. No active waveform or powered r3 result yet.
See current CHAT_HANDOFF and CURRENT_BENCH_STATUS_RU.md. No recalibration or fixture swap.

HISTORICAL 2026-10-14: r2 WORKING1415/1414 completed one normal powered5 Hz scalar
run to ordinary STOP, UART fault0; user confirmed smooth rotation on this r2.
Observed active span8.391s,5 Hz reference span7.828s; actual rotor speed/current
remain unqualified. NE8/accepted6/recovered drops4 without transport trip.
One archived cold-start UV/DP CLEAR before START; no retry/reflash/recalibration.
Now SAFE/PWM0/ARM0/fault0/Vbus323 V. Mains/J4 remain ON at operator request,
both boards on powerbank, PC USB and Saleae removed; motor connected.
Post-run stopped powered idle had no new errors; power removal was NOT tested
on r2. Do not interpret the collector's legacy power_off filename as OFF proof.
Current boot e20a19c7-18e6-45c8-a2da-c9fa2b944a93, Wi-Fi8080/pinned SSH2222
working. HMI and original calibration hashes unchanged after run.
Evidence: r2/powered_vf_1792011214155394100/report.json and powered_stopped_idle_report.json.
Online acceleration still not implemented; no pending USB/firmware action.

PREVIOUS INSTALLATION CHECKPOINT 2026-10-14 20:48 UTC: r2 WORKING1415/1414 installed and both writes
verified; full Nucleo readback matched. HMI8680ac48bc10de88a79a8abb458d46a771dc40b948bf7beb5eb033fca78216d7,
original calibration unchanged/accepted. RPC resumed without USB recovery.
Boot199f9dfb-997c-463a-90a6-2c0062703bbf. Actual31.157s/42 samples/+595 replies,
no new errors after known programming timeout archived/acknowledged once.
SAFE/PWM0/ARM0/bus0/UART fault0/bad0; expected undervoltage5/masks4/4,
one retained cutover discard. No powered START on r2 yet.
User confirmed all mains/J4 OFF, independent<20 V and both PC USB ready for
this write; motor connected. Pending transfer back to powerbank/closed stand/
ON15 V and mains for one normal5 Hz bounded start, using the generic installed-pair
runner. Do not flash or recalibrate again for that run. See latest CHAT_HANDOFF.

PREVIOUS: r1 pair1413/1412 remained installed. Real motor rotation confirmed by user
on requested repeat; RUN/5Hz reference seen, then UART NE stopped early. Full
stable ten-second run NOT achieved. User confirmed mains/J4 OFF, boards on
powerbank; actual30.719s/+596 replies/no new errors across power removal passed.
Bus245->187 V then, later fresh11 V. First UART fault kept; no post-run CLEAR.

r2 candidate1415/1414 BUILT and qualified offline, NOT installed: single-NE
full-CRC/fresh-sequence packets are advisory, separated from real damaged-packet
budget.2106 checks and40-packet NE burst regression passed. All PWM/measurement/
protection sources unchanged; calibration preserved. Pending physical USB-ready
and independent<20 V acknowledgment for writing r2. Leave motor connected.
Current source/hardware/evidence details are in the latest CHAT_HANDOFF section.

PREVIOUS INSTALLATION CHECKPOINT 2026-10-14 18:23 UTC: WORKING1413/1412 installed from
`artifacts/live_bench_20261014/uart_recovery_working_pair_r1`. Both writes verified,
full Nucleo readback matched. HMI952de2e96d7ab6bef8e5a321f209769a00caf390268f3f71dbb1c6ab1c587639;
original calibration byte-identical, matching pair accepted. Current Linux boot
2b7e1087-a6a7-4603-9075-b7634f17553d. RPC recovered after upload without USB
cold boot; Wi-Fi192.168.1.138:8080 and pinned SSH2222 available.

User confirmed mains/J4 OFF, meter residual<20 V, explicitly authorized repair.
Motor remains at J3. BOTH PC USB used for programming. Latest SAFE/PWM0/ARM0/
Vbus2 V; UART fault0 and fatal/integrity/sequence/hardware/passive counters0;
recovered-discard1 retained from cutover. Expected undervoltage fault5/masks4/4
is independent of UART. Known programming LINK_TIMEOUT7 was archived and
acknowledged once; physical undervoltage retained. Real idle30.828s/41 samples/
+589 responses passed. New powered motor run NOT performed yet.

Pending physical question: return both boards to powerbank, keep Saleae probes
removed, close stand, ON15 V/mains through existing soft-start, report ready for
one normal5 Hz bounded start. Keep original calibration and working bundle;
no fixture swaps or motor disconnection. See latest CHAT_HANDOFF for evidence.

HISTORICAL, before normal-HMI/UART repair: working1411/1410 installed from pwm_filter_pair_r7.
HMI93d21c9381dc0e93613f3a638497ccb6b6525c4051f7c117068382a82ebcf0c4;
no fixture HMI, primary unpaused/running. Final SAFE/PWM=0/ARM=0/bus=0;
transport/error counters0; only expected zero-bus fault5/masks4/4.
Current Linux boot80efa2f2-1f53-4194-9661-5648b3f203b4 after the user's transfer
to powerbank (both boards), PC USB and Saleae USB disconnected. Autonomous
30-second Wi-Fi idle passed,40 samples,+596 good frames, all errors0,
SAFE/PWM0/ARM0/bus0, original calibration and HMI hashes unchanged.
Evidence: snapshot_stop_sync_hil_r1/autonomous_idle_1791995712628013400/report.json.
J4 ONLY15 V check completed with J1/motor still detached. Operator meter9.5 V
on DC-link (NOT discharged); controller9..10 V during30 seconds, mean9.666667 V,
42 samples,+603 good frames, all errors0, SAFE/PWM0/ARM0; sensor47 C,fault0.
Evidence: snapshot_stop_sync_hil_r1/j4_driver_idle_1791996153341614900/report.json.
First-since-boot BKIN record now captured with MOE0/PA6-low; preserve it, no CLEAR
issued. Old calibration still unchanged; working-voltage gain unqualified.
OFF15 V confirmed. Controller5 V, operator meter2.5 V after turn-off; not yet
confirmed<2 V for re-wiring. Evidence j4_off_1791997173694116000/report.json.
Working-voltage preparation confirmed by user ready: independent meter<2 V,
ALL Saleae probes/GND removed, J1 connected to switched-off original source,
motor remains disconnected; both boards on powerbank, PC USB removed.
Fresh reported Vbus1 V, SAFE/PWM0/ARM0/trial0 and errors0; HMI/cal hashes unchanged.
Evidence working_bus_prepared_1791997766415076200/report.json. No exact new zero
meter value recorded. Charge GET-only collection active (exec5077,300 seconds),
folder working_bus_charge_1791997766415589900. J4/mains still OFF pending next
instruction: secured meter/closed stand, ON J4 15 V then mains via soft-start;
report power on and NEW meter voltage. Motor stays detached; no ARM/START.
Read-only tools/verify_vbus_preserved_points.py prepared,20 offline checks passed,
GET-only20 samples, preserve calibration; passive_working_bus_preparation_r1/plan.json.
It cannot unlock HMI/START. Old322.7 V must not be reused as a fresh meter reading.
Previous boot2f1d2cc2-bf16-4f14-80f1-e1ecff58ef37 recovered r6 RPC;
r7 swap paused verified user HMI while MCU reset, then resumed successfully.
Programming-only timeout was recorded and acknowledged once.30.078s idle,
+598 good frames. snapshot_stop_sync_hil_r1/RESULT_RU.md contains full proof.
Old calibration unchanged/archived: meter0 and322.7 V, MC0 and325 V. Operator
supplied meter0.32 V, then rejected repeated replacement of these points.
20 read-only samples verify discharged-bus agreement (MC0 V);0.32 V was NOT
recorded as a new calibration point. No calibration POST/reset or firmware write.
Do not execute the superseded new-zero capture plan: it would discard old HIGH.
HMI identity incompatibility and explicit HV gate remain. The filter changed
its fractional remainder in r3/r4; subsequent diagnostic changes do not warrant
repeated recalibration. Preserve points and review measurement compatibility
separately; see current handoff and vbus_preservation_review_1791995033559009700.
Read latest handoff; all older installed-pair descriptions below are historical.

CURRENT VERIFIED 2026-10-14: working Uno2026101407 / Nucleo2026101406 installed
and flash verified. Final package pwm_filter_pair_r4; session pwm_filter_hil_r2
restored, passive check +586 frames with zero error deltas. HMI SHA256:
0e896bfc4df50e53c1783c2eb017a0d4e77d60f67207200dd51cef2917b53902.
SAFE/PWM=0/ARM=0/bus=0 V, programming-cutover Nucleo STOP fault still latched.
Calibration bytes unchanged but invalid for changed filter; HV gate closed.
Both fixture HMI processes on8081 stopped. Do not restore obsolete1405/1404.
Read pwm_filter_hil_r2/RESULT_RU.md for measured PWM and diagnostic rejection.

Operator correction 2026-10-14: six Saleae probes and logic GND stay connected;
ONLY USB is removed/reconnected. Do not ask to reconnect these same probes.
Newest revision is r4 (working 1407/1406; detached 1496/1497), completing a
follow-up for false software fault during inactive boot HFT. The r3 state below
is superseded; consult the newest handoff and pwm_filter_hil_r2/session.json.

Active update, 2026-10-14: detached fixture 2026101498/2026101499 is currently
installed, SAFE/PWM=0/ARM=0/bus=0; awaiting Saleae probes before bounded PWM.
New working 2026101405/2026101404 is built; restore to THIS pair after capture.
Primary HMI SHA256 is 701f01b7a57da13c1d25ee4d2bd008b442ef76bf497e5ea2727c0632c2fc72a6.
Original calibration bytes preserved but invalid for the new filter identity.
Port 8081 is the owned LV-only fixture HMI. Read the latest handoff first;
older installed-pair/hash descriptions below are historical.

Workspace: C:\mic_practice. Installed production IDs: Uno 2026101205,
Nucleo 2026101204. Read CHAT_HANDOFF_20261012.md first; preserve its latest
stage notes and frozen artifacts. Do not restore superseded images.

Wi-Fi HTTP: http://192.168.1.138:8080. /api/status is read-only and requires
no control token. Authenticated commands and logs use the existing private
.unoq_ssh/control_token, never a hard-coded or printed token. Direct Wi-Fi
proof uses WifiHmi(..., via_wsl=False), not an ADB port forward.

SSH: arduino@192.168.1.138, port 2222. Use .unoq_ssh/id_ed25519 with pinned
.unoq_ssh/known_hosts and StrictHostKeyChecking=yes. SSH key authentication
works without a Linux password. The key is NOT a sudo credential.

ADB: adb -s 3880458060 shell, user arduino UID 1000. Uno USB COM10 is the
last observed address; identify by serial, not by assuming a COM number.
Nucleo ST-Link serial: 003A002C3335510933383531, last USB COM13. Saleae
device: A7D1BB81883C0092; automation port 10430. Do not interrupt an operator
capture or require extra probes that were not agreed.

## Linux Services And Files

- unoq-hmi.service owns primary HMI, arduino UID 1000.
- arduino-router.service owns internal ttyHS1, root UID 0.
- arduino-router-serial.service is the serial monitor proxy.
- Installed HMI: /home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/server.py.
- Use the adjacent .venv/bin/python for imports (system Python lacks modules).
- Calibration: /home/arduino/.config/mic-ai/vbus_calibration.json.
- Current HMI SHA256: 992b3c20c8573681f195de3a208a461359c22673b83e3f2d578f87e16ce212d1
  (2026-10-14 passive 1204 snapshot decoder fix; control/actuator AST unchanged).
- Previous short-trial HMI SHA256: 88f0764f881b5bbc7cb8e1e0b40954fe7d2e63450edd568cd8b92f83550d2d6b
  (short_trial_candidate_r2; exact-evidence one-shot fixture-transfer trial schema).
- Previous HMI SHA256: 21bda96fae14b0fa13db27d1fb21edd6f059e6d2037199944bdae50999569276.
- Original calibration SHA256:
  a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.

.unoq_ssh/ is ignored by Git. Do not put passwords/tokens in source, artifacts,
reports or handoff messages. No sudo password was ever found in the supplied
context or project credential files. The user explicitly does not know it.
Never guess a password, mistake the control token for it, disable authentication,
change sudoers, or claim a documented universal factory password.

Both `sudo -n -v` and `sudo -n systemctl restart arduino-router.service`
were rejected with authentication required. logind CanReboot returned challenge.
`adb reboot` returned error: closed and did NOT reboot Linux (boot ID unchanged).
Repeated attempts at those commands are not a recovery strategy on this image.
Arduino removed incorrect references to a default password:
https://github.com/arduino/docs-content/pull/2729

## Completed Recovery

On 2026-10-12 the user fully removed Uno power for five seconds and reconnected
it, retaining Nucleo/Saleae and the isolated, unpowered motor setup.
Linux boot ID changed from 9f1d8e82-6cb8-48d4-8698-2d35239f0c09 to
cf8c52bb-a93d-4013-a646-65a846c1c033. RPC returned without a firmware write,
password, new calibration, CLEAR, ARM or START.

The direct Wi-Fi 30-second check passed: +591 good frames, no new UART/HTTP
errors, SAFE/PWM=0/ARM=0, reported bus 0 V, current identities 1205/1204,
diagnostics valid, local-stop field 0 consistent with raw status 9. MCU fault
5 is the existing zero-bus MC_UNDER_VOLT (masks 4/4), not an UART failure.
Both services are active, HMI/calibration hashes unchanged. Evidence:
artifacts/live_bench_20261012/local_button/post_cold_boot_r1/summary.json,
status.jsonl and logs.txt.

The earlier physical B1/PWM test already passed on detached fixture 1298/1299;
production images were restored and verified. Read PWM_LOCAL_STOP_REPORT.md
for its exact scope. Do not repeat a successful test or reflash verified images
because a stale handoff still says recovery is pending. No powered release
or exact PC13-to-off latency is established by the cold-boot check.

## Operational Rules

Latest single powered run is `local_button/motor_short_r1`: user confirmed
rotation, but HMI rejected a new Uno UART_ERROR_NOISE count and stopped.
Overall pass=false; one-shot consumed, outputs off, power off confirmed.
Do not repeat START or clear evidence to make this pass. Read RESULT_RU.md.
Passive snapshot decoder 1204 whitelist correction was installed and tested on
2026-10-14; both records are now readable. See the latest CHAT_HANDOFF section
and artifacts/live_bench_20261014/passive_decoder/install_r1/report.json.
No MCU firmware writes or new powered preparation were made. First fault,
error counters, calibration and UI preserved; post-install idle +604 frames
without errors. The physical UART noise source remains unidentified.

For a recurring RPC failure, save diagnostics and check live identity/state.
Try owned HMI recovery only when appropriate; avoid a competing reader of
ttyHS1. If that fails with verified images and root router unavailable,
request one full Uno cold boot on a confirmed unpowered/isolated stand, then
verify boot ID, telemetry freshness, output state and calibration bytes.

Power-stage activation is a separate operator-coordinated stage. PC USB and
all Saleae wires must be removed for powered operation. Do not infer new
physical conditions or send START from this document. Do not recapture the
zero calibration just because the user reconnects a board.
