# Local Button and Manual Control Audit

## Result

The extracted PC13 callback and RUN publication branch from the source of
Nucleo image 2026101102 reproduce a restart after local STOP completes.
The button calls MC_StopMotor1 without latching a local inhibit. A subsequent
otherwise valid ENABLE heartbeat calls MC_StartMotor1 when MCSDK reaches IDLE.
Reproduction output: `restart=1 failed=0`.

This is a source-level result with mocked MCSDK APIs, not a powered test or
proof that this path caused earlier observed failures. Installed firmware
was not modified. No hardware commands were sent by the audit.

## Manual Control Requirements

- Existing manual HMI is at http://192.168.1.138:8080. Frequency, START, STOP
  and log access must remain explicit operator actions.
- A preparation-wait deadline and a motor-running time limit are separate
  concepts. Waiting for operator preparation should not consume a run budget.
- Local PC13 STOP must inhibit queued and subsequent ENABLE commands, not
  merely stop the current MCSDK state. It must remain effective without UART.
- Only an explicit acknowledged reset, with the button released and outputs
  off, may release that inhibit. Release must not itself start the motor.
- Link loss in the existing remote-control mode must still disable outputs.
  Unsupervised continuation requires a separately designed local ownership
  mode; the presence of a button alone does not implement that mode.
- Do not remove physical BKIN, bus, thermal or transport guards to make a
  manual control panel appear operational.

## Outstanding Work

Implementation, offline interrupt/publication tests and the target build are
now prepared in the separate candidates described in `FIX_REPORT.md`.
Installation and physical low-voltage validation are still outstanding. No
unrestricted manual powered release is established by this audit. The installed
HMI still has an expired preparation; it was not renewed under high voltage.

## Evidence

- `restart_audit_r1/report.json`: assumptions, hashes, reproduction result.
- `restart_audit_r1/button_restart.cpp`: extracted host test.
- `tools/nucleo_button_restart_audit.py`: reproducible, hardware-free audit.
