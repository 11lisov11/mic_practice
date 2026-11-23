# First 30-second / 50 Hz coast trial: driver protection interrupted acceleration

## Setup and Scope

- Operator selected 50 Hz with PWM-off coast, not active braking.
- Operator reports an effective measured DC capacitance of 370 uF on a
  discharged bus, and no braking resistor. Do not continue using assumed 690 uF.
- Uno 2026101008 and Nucleo 2026101006 were unchanged. Only Linux/HMI was updated.
- HMI SHA256: 0f8a321491ff09624a9afd521ae431db381e7446a8d461dde6f3f3722aec17ce.
- Calibration bytes were preserved. Offline regression: 44/44 suites.
- The one-shot profile permits a fixed 50 Hz command, an HMI stop after 30 s,
  a 33 s MCU backup and a 45 s ARM lifetime. Active deceleration is forbidden.
- General high-voltage commissioning approval remains false.

## Observed Result

The operator confirms that the shaft began rotating quickly and then coasted.
No 30-second run was completed. Actual rotor speed and reaching 50 electrical
Hz were not measured. The frequency shown by the Uno is a local reference, not
an independently measured Nucleo electrical frequency or shaft speed.

Powered preflight showed 323 V and only retained undervoltage history. After
explicit CLEAR and fault-free powered idle observation, one START was accepted.
Ten active samples were captured before the stop; the first fault sample was
5.516 s after START HTTP acknowledgement.

At the first fault:

- First cause: MCSDK_FAULT (diagnostic reason 8).
- Current and occurred masks: 0x0400, MC_DP_FAULT.
- UART bad count, CRC/sequence counters, UART error flags, last bad reason,
  transport fault and short-write counter: all zero.
- Two NE events were observed and accepted by the existing bounded CRC policy.
- DC bus at captured active samples: 315..321 V; first fault sample: 321 V.
- Reported heatsink temperature: 51..52 C, no temperature fault flag.
- Emergency STOP was acknowledged and outputs-off was confirmed.

The first MCSDK cause remains retained after subsequent ESTOP. This event is
neither the intended 30/33-second deadline nor a rejected UART frame.

## What Is Known and Unknown

The frozen code maps TIM1 break events to PWMC_DP_Handler, which switches PWM
off and sets driverProtectionFlag. PWMC_IsFaultOccurred reports that flag as
MC_DP_FAULT (0x0400). PA6 is configured as TIM1_BKIN. This establishes the
protection path; it does not uniquely identify an IPM overcurrent, a 15 V rail
dropout, SD wiring/ground disturbance or a short noise pulse at BKIN.

Voltage and temperature telemetry snapshots do not exclude intervening
transients. Current telemetry is unqualified. No powered PC/analyzer connection
was used, so there is no waveform capture resolving the fault pulse.

Do not disable break protection, silently extend its filtering, clear the fault
and repeat 50 Hz, or mark this trial passed. The early trip needs diagnosis.

## Retained Evidence

- `coast30_hmi_install_r1/install.log`: Linux-only installation and calibration preservation.
- `coast30_post_install_idle_r1/report.json`: 414 new valid stopped UART replies.
- `coast30_autonomous_boot_r1/report.json`: fresh powerbank Wi-Fi status.
- `coast30_powered_preflight_r1/status.json`: powered stopped state.
- `coast30_powered_observation_r1/report.json`: successful no-PWM observation.
- `coast30_motor_trial_r1/report.json`: retained failed trial and first-cause snapshots.
- `coast30_motor_trial_r1/wifi_logs.txt`: onboard Wi-Fi log.
- `coast30_motor_trial_r1/post_trial_status.json`: outputs off, bus subsequently 63 V.

## Next Work

Keep mains off, switch J4 off and keep PC wires removed while the bus discharges.
Diagnose the SD/PA6 break path and auxiliary supply before another extended
powered trial. Additional instrumentation should capture the first break event
and actual speed reference; existing generic MC_DP alone cannot prove its source.
Secure Linux/HMI Wi-Fi deployment was subsequently verified on the existing
key-only SSH listener at port 2222. The earlier assumption that SSH was absent
was based on checking port 22, not the configured listener. See
`wifi_ssh_deploy_verified_r1/report.json` and `docs/unoq_wifi_hmi_deploy.md`.
This deployment verification sends no actuation commands and does not clear or
resolve the powered-trial MC_DP fault. MCU images were not modified.
