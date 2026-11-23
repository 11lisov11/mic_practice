# BKIN event during power-up

Live HMI telemetry after the user applied 15 V and the DC bus showed a new MCSDK `MC_DP_FAULT` and a first-since-boot TIM1 break snapshot. The bus was about 321–323 V, IPM temperature 48 °C, and UART bad-frame/error counters remained zero. PWM was off (`MOE=0`).

The snapshot has `BIF=1`, `BKE=1`, and PA6 sampled LOW in the break ISR. This proves the BKIN path asserted before START; it does not identify whether the IPM asserted SD from overcurrent or gate-supply UVLO, or whether the SD/BKIN line has a wiring/level problem. The cached Nucleo context is invalid because the event occurred before the diagnostic run context. The 1-MHz DMA capture is armed only when START is accepted, so there is no pulse-duration trace for this event.

The STGIB15CH60TS-L datasheet documents SD assertion for either comparator overcurrent or control-supply undervoltage, and recommends VCC=13.5–18 V. The HMI measures DC-bus voltage and temperature, not the IPM's 15-V rail, so the observed 15-V gate supply has not been verified at the module. Source: https://www.st.com/resource/en/datasheet/stgib15ch60ts-l.pdf.

No CLEAR or START was sent after this event. The evidence is in `report.json`. Keep the drive stopped until the 15-V gate-driver supply and SD path are checked with the high-voltage bus off and discharged.

After switching off J1/J4, remote HMI telemetry fell to 10 V and remained `SAFE`, PWM=0. With both boards connected to the PC, a read-only ST-Link/OpenOCD poll sampled GPIOA 5,000 times without reset or halt: PA6 was HIGH in all samples, with zero observed transitions; the Nucleo core remained running. This rules out a line held continuously LOW at rest, but it does not reveal the duration or source of the earlier power-up assertion. Raw ST-Link output: `stlink_pa6_readonly.log`.

With only J4's 15-V supply on and J1/high-voltage bus off, a second read-only ST-Link poll again sampled PA6 HIGH in all 5,000 reads, with zero transitions; the core remained running. HMI reported SAFE, PWM=0, Vbus=9 V, IPM=34 °C, UART errors=0. The old `MC_DP_FAULT` (`occurred=0x0400`) remains latched, with no current fault bits. Stable J4-only operation did not reproduce an active BKIN. This cannot rule out a short transient during a supply ramp. Raw ST-Link output: `stlink_pa6_j4_only.log`; structured values are in `report.json`.
