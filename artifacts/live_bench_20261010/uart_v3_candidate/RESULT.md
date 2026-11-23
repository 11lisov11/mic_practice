# UART v3 Stand Update, 2026-10-10

Installed: Uno Q **2026101007**, Nucleo **2026101006**.

## Passed

- Both board images programmed and flash contents verified.
- Saved Vbus calibration preserved byte-for-byte.
- 38/38 offline regression suites.
- Integrated transport: 204,552 scenarios and 619,694 assertions.
- Six critical PWM/break object-code sections match production; TIM1 initializer unchanged.
- 30-second live idle Wi-Fi/UART observation without new transport errors.
- Wi-Fi setpoints 5 -> 20 -> 0 Hz, STOP, sustained ESTOP, CLEAR.
- Sustained ESTOP no longer causes a duplicate LINK_TIMEOUT.
- NE counters survive HMI decoding; genuine short writes remain distinguishable.

## Limits

PWM was not activated in the accepted live tests. No motor start was requested.
Active low-voltage PWM capture and powered noise qualification remain pending.
The original powered NE event's physical cause has not been identified.
HV arming for this candidate remains blocked. Offline corruption tests are not
a safety certification or proof against every possible physical error pattern.

## Evidence

- `install_estop_fix_r1/report.json`: final pair installation and idle observation.
- `wifi_idle_commands_r3/report.json`: final Wi-Fi command and ESTOP test.
- `regression_r7/report.json`: current offline regression.
- `critical_code_r6/report.json`: selected PWM/break code comparison.
- `mutex_r6/report.json`: real Uno ELF mutex layout.
- `firmware_r6`: exact candidate sources and compiled images.

Earlier failed runs remain available, including the 32/43-byte diagnostic error
and the duplicate ESTOP watchdog error. They are superseded only where the
later test explicitly verifies the correction.
