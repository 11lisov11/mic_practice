# Low-voltage checks, 2026-09-27

Scope: user-confirmed power stage deenergized. No START, ARM, reset or flash commands sent. Active PWM and power-stage protection were not exercised.

## Results

- UNO Q ADB 3880458060, COM10; ST-Link/COM13 and physical Saleae A7D1BB81883C0092 detected.
- 20 read-only bring-up samples passed; UNO Q and Nucleo report build 2026091401, RPC v3.
- HMI systemd service active/enabled; deployed HMI hashes match the flash package.
- 20 additional HTTP status requests to 192.168.1.138:8080 succeeded. UART good counter 2553 -> 2831; bad counter 1 -> 1; maximum reported response age 52 ms.
- SAFE, PWM=0 and reported Vbus=0 throughout sampling; fault 5 is undervoltage. This telemetry is not an independent voltage measurement.
- Two Saleae captures at 24 MS/s, requested duration 0.2 s, recorded channels 0..5 continuously LOW. Interpretation assumes probes remain on the documented six PWM pins.
- Initial 2 s Saleae capture failed with ReadTimeout. Both shorter retries passed; sustained capture reliability remains unverified.
- Python research tests: 1051 passed. HMI guard selftest: 155 passed. MCSDK preflight selftest, Nucleo safety check, UART contract and flash-package verifier passed.

## Observations and limits

- One accumulated UART error was present before sampling; its cause is unconfirmed. It did not increase during these observations.
- ia/ib/ic are populated from UNO Q local analogRead inputs (UNOQ_MOTOR.ino). Nonzero idle readings are not verified motor phase currents; input wiring/calibration and telemetry source require follow-up.
- enc_ok=0: encoder feedback not confirmed.
- Persistent Vbus verification is incomplete, HV unarmed. Hardware release remains unvalidated.
- Active PWM frequency, dead time, SD/BKIN trip, external soft-start and loaded operation were not tested today.

## Evidence

- board_bringup_logic_only_20260927_192606.json
- logic_idle_retry_20260927/report.json and nucleo_pwm.sal
- logic_idle_repeat_20260927/report.json and nucleo_pwm.sal

Additional Wi-Fi statistics and software test outcomes above were recorded from command output during this session.
