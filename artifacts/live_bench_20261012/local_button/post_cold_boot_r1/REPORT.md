# Production RPC Recovery, 2026-10-12

The user confirmed fully power-cycling Uno Q only. Linux boot ID changed from
9f1d8e82-6cb8-48d4-8698-2d35239f0c09 to cf8c52bb-a93d-4013-a646-65a846c1c033.
The previously unresponsive primary RPC returned without any firmware write.

30-second HTTP GET-only verification passed: 29 samples, good UART messages
3279 -> 3870 (+591), no HTTP errors, bad/CRC/sequence counters remain zero,
fresh link, identities 2026101205/2026101204 stable. SAFE, PWM=0, ARM=0 and
reported bus 0 V throughout. Logs download succeeded. No ARM/START/CLEAR was
issued. This is an idle communications check, not a powered qualification.

Installed HMI SHA256 remains
21bda96fae14b0fa13db27d1fb21edd6f059e6d2037199944bdae50999569276;
calibration remains
a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.
arduino-router.service and unoq-hmi.service are active. Diagnostic validity
returned; MC_UNDER_VOLT masks 4/4 on zero bus remain recorded, not erased.

Sudo password is not known to the user or recorded in project files. The
noninteractive sudo validation/router restart and logind reboot checks required
authentication. An attempted adb reboot returned error: closed; unchanged boot
ID showed no reboot. These failed attempts must not be called successful.

The successful earlier B1/PWM fixture test and verified production restoration
are described in PWM_LOCAL_STOP_REPORT.md. Its pending-RPC section is now
superseded by this recovery report. Active production PWM/HV and exact button
edge-to-off timing are not proved by this check.
