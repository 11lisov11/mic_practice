# Connected bench verification, 2026-10-06

## Scope and physical state

The operator confirmed that STEVAL J1 is physically disconnected from the
rectifier/mains. No fresh motor-disconnection or J4-voltage confirmation was
obtained. All captures in this run were passive. No ARM, MCU reflashing,
active PWM, mains application, or motor run was performed.

Vdc=0 below is controller telemetry, not an independent multimeter result.

## Results

| Check | Result | Evidence |
| --- | --- | --- |
| Linux service, MCU RPC, UART and deployed HMI identity | 14/14 passed | `board_bringup_after_update.json` |
| Wi-Fi VF selection, frequency requests 5/20/0 Hz, final STOP | Passed, SAFE/disarmed/PWM=0 throughout | `wifi_commands_after_update/report.json` |
| START at zero reported bus | HTTP 409: mc_fault=5 | Same report; this tests the fault guard, not every downstream arm gate |
| Command log download over Wi-Fi | Passed | `wifi_commands_after_update/logs.txt` |
| Post-update telemetry, 30 seconds | 38 samples, no HTTP errors, UART good 20207 to 20741 | `telemetry_after_update/summary.json` |
| UART integrity / sequence / clear pending | All remained zero | Same summary and `status.jsonl` |
| Historical superseded reply | Remained 1; counters were not cleared | Same summary |
| Saleae after Wi-Fi commands | Six outputs LOW; CH6/PA6 HIGH; no edges over 0.256 s at 24 MHz | `logic_after_update/analysis.json` and saved capture |

Commands and logs used LAN HTTP through WSL NAT, not ADB forwarding.
Windows direct LAN sockets started returning WinError 10013 during this run;
the existing WSL transport still reached the board over the network.
ADB was used for read-only service inspection, token bootstrap and deployment,
not for motor commands. Tokens were not included in reports.

## Repairs

The running Linux HMI server omitted four UART diagnostic counters that were
already present in the local/package source. Only this existing telemetry fix
was deployed. No MCU image, calibration, auth token or service settings changed.

Server SHA-256 after deployment:
`8f8730a29d70f50d8f5e1d132147bc408c9156f5571ad623808bfd9f4518a9a6`

Remote backup:
`/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/server.py.before_telemetry_20261006`

A separate verification-tool defect was fixed locally: WSL HTTP assumed every
response was JSON, but `/api/logs` returns text. Explicit text responses, status
validation, authenticated log requests and transport labels now work. The CLI
also closes the WSL helper on exit. Defaults for JSON callers remain unchanged.

New/affected offline tests: command-path verifier 6/6, WSL transport 4/4,
Wi-Fi PWM bench helper 21/21. Earlier tests and failed capture attempts remain
in the directory; they are not overwritten or counted as post-update captures.

## Not Established

- Carrier frequency, complementary PWM deadtime and active overlap: not measured.
- Physical BKIN-trip timing and restart inhibition: not retested this run.
- VF acceleration under load, motor rotation, current-sensor offsets: not tested.
- Independent Vbus measurement and completed two-point calibration: absent.
- Installed firmware capabilities are VF only, not deployed FOC or AI control.
- A static LOW capture is not evidence that active switching has correct deadtime.

Observed MCU build IDs: UNO Q 2026092901, Nucleo 2026091401. These are reported
identities, not a flash readback hash. The release package remains marked as
not hardware validated. This report does not authorize mains operation.

## Next Verification Stage

Retain the verified Wi-Fi path and production safeguards. Define the active
low-energy/HIL test separately, covering six-channel switching, deadtime,
START/STOP/ramp behavior and physical BKIN. Production firmware currently
rejects a zero-bus START; do not bypass or fake its ADC/voltage guards and do
not describe a diagnostic-firmware test as production-firmware validation.

Before that active stage, establish the motor/J4 state and the permitted
test fixture. Before powered operation, complete bus/current calibration,
soft-start validation and the production protection gates with no wired PC
connection to the non-isolated energized power stage.
