# J4 Auxiliary Supply: Passive Wi-Fi Check

Operator reported 15 V applied to J4; mains remained off and the controllers
remained on autonomous supply. No ARM, START, CLEAR or firmware write was sent.
The J4 rail itself is not remotely measured.

- Live pair: Uno 2026101108 / Nucleo 2026101102.
- 60-second collection: 57 snapshots, 1201 new good replies, no HTTP errors.
- UART/CRC/sequence errors, RX drops and hardware UART error counts stayed zero.
- All snapshots: SAFE, PWM=0 and HMI HV armed=0.
- Maximum enqueue interval: 53177 us; maximum parser polling gap: 5 ms.
- Bus telemetry: 5 V in initial snapshot, then 7..9 V during collection.
- Reported temperature: 49 C; this is controller telemetry, not an independent
  thermometer validation.
- First-fault masks remain 0x0004 MC_UNDER_VOLT; no active high-voltage bus.

## Pre-START Break Record

Before the J4 step, the retained installation report had no captured break.
The current first-since-boot record is captured at MCU tick 261709 ms:
BIF=1, PA6 LOW at IRQ, BKE=1, MOE=0, all CCRs=0, reference=0 Hz, cached bus=0 V
and START window=0. The cached context was 2 ms old. No first-START-window
record is captured. The raw first record remained unchanged throughout the
60-second collection.

This establishes a pre-START SD/BKIN observation, not an explanation of the
earlier powered motor trip. No claim is made that J4 switching uniquely caused
it. GPIO was sampled at ISR entry, not continuously. The existing firmware
does not expose the current PA6/SD level, and an unchanged first record cannot
prove either that SD is released or that no later pulses occurred.

Requested next observation: DC voltage at TP23/SD relative to J4 minus, without
shorting anything and with mains still off. This is not a new bus calibration.

## Subsequent SD Measurement

Operator reported **2.6 V** at TP23 relative to J4 minus. DS12589 Rev 6,
Table 53 specifies guaranteed VIH=0.7*VDD for the relevant digital input.
At assumed VDD=3.3 V this is 2.31 V, giving a static margin of 0.29 V.
This measurement is consistent with HIGH and does not support a continuously
LOW SD node at the measurement instant. It does not exclude brief pulses,
independently measure Nucleo VDD or digitally sample PA6 itself.

After measurement, native Wi-Fi still reported SAFE/PWM=0, bus=9 V, and zero
UART errors. HMI remains disarmed. Ordinary start is still blocked for the
new firmware pair and by its unmatched calibration identity; the existing
calibration points have not been changed. No fault reset or powered START
was issued. Next software work is a reviewed, evidence-bound short-trial
qualification, not bypassing those checks or recapturing zero indiscriminately.

Source: https://www.st.com/resource/en/datasheet/stm32g431rb.pdf
Evidence: `sd_measurement.json`, `after_sd_measurement.json`.

Evidence: `before.json`, `telemetry/status.jsonl`, `telemetry/logs.txt`,
`telemetry/summary.json`, `result.json`. The 15-V collector ceiling was solely
an auxiliary-powered observation bound, not a start or programming allowance.
No mains-start approval or automatic fault reset was made.
