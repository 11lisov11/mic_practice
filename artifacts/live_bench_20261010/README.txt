Bench status, 2026-10-10
======================
Current installed pair remains Uno Q 2026100804 / Nucleo 2026100801.
HMI profile HV restored, ARM/PWM off, device calibration preserved.
No high-voltage acceptance or motor rotation is claimed.

Completed observations
----------------------
wifi_idle_r1/report_with_capture.json: PASS. 714 UART messages in 51 s,
no new errors, maximum reported age 52 ms. Wi-Fi setpoints 5/20/0 and
STOP acknowledged while off; four log downloads. Six outputs LOW, SD HIGH.
The initial report.json retains a failed relative-path Saleae export.

j4_15v_readonly_r1/report.json: PASS, passive only. 353 messages in 26 s,
max age 50 ms, no new errors. Six outputs LOW, SD HIGH. HOTPLUG register
reads confirm BKIN enabled and MOE off. Reported bus 7..8 V, not a meter
measurement. Current production fault MC_UNDER_VOLT is expected in this setup.

physical_sd_r1/report.json: overall FAIL, not a failed physical protection.
Valid 16 kHz PWM on all six pins; no observed overlap. Minimum sampled gap
1.25 us at 4 MHz resolution (250 ns), not an exact analog deadtime measurement.
SD never changed; operator subsequently confirmed missing the 3 s window.
No physical SD trip is established. Production image restored and byte-verified.

physical_sd_r2/report.json: FAIL, Saleae Device disconnected. Operator also
confirmed missing the contact. No accepted waveform; no protection claim.
Production image restored and byte-verified. Subsequent 250 ms passive capture
in analyzer_recovery_r1 passed; the disconnect's root cause is not established.

Automatic external-stimulus fixture (prepared, NOT flashed)
--------------------------------------------------------
sd_auto_preparation/fixture: auxiliary_only_10v_auto_sd_pc8.
Temporary wire: Nucleo PC8 / CN10-2 -> 1 kohm -> STEVAL TP23 / SD.
Do not also connect this wire to GND, +15 V or DC+.
PC10 and PC11 are deliberately avoided: IHM09M2 routes them to service functions.
Nucleo header reference: ST UM2505, table 16:
https://www.st.com/resource/en/user_manual/um2505-stm32g4-nucleo64-boards-mb1367-stmicroelectronics.pdf

PC8 is open-drain: released at boot, LOW after 800 ms of active PWM, released
after 250 ms even when BKIN has stopped PWM. One pulse per MCU boot, no software
TIM1 BG injection. The fixture never starts PWM itself. The HMI 3 s run limit,
real filtered ADC <=10 V interlock, ADC freshness and MCU 15 s cap are retained.
Fixture 899 identifies the reviewed UART format, NOT unique binary contents;
use fixture variant and SHA-256 manifests to distinguish different test images.

Host pulse-state tests, 10 V interlock tests, waveform counterexamples, safe
state and missed-contact/no-second-START checks passed. Final target compilation
had zero errors/warnings. Initial clean of the new CubeIDE directory logged
missing makefile; subsequent generation/compilation succeeded. These messages
remain in the original build log. Critical PWM/BKIN code sections and TIM1
initializer match production (sd_auto_preparation/critical_code/report.json).
This fixture has NOT been installed or physically qualified.

Required next action
--------------------
With J1 and motor still disconnected, switch J4 off, install the temporary
PC8/1k/TP23 wire, then restore J4 15 V and confirm wiring before flashing.
The runner requires --confirm-pc8-test-wire and restores production afterwards.
Remove this temporary wire before ordinary operation or any later HV test.
Keep HV disconnected throughout this diagnostic sequence.
