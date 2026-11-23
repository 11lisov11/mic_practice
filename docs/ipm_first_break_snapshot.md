# IPM first-break diagnostic candidate

## Status

This is an isolated recorder candidate, not an installed firmware or permission
to run mains. The frozen baseline is Uno Q 2026101008 / Nucleo 2026101006.
Current installation is Uno Q 2026101103 / Nucleo 2026101102, with paired
Wi-Fi diagnostics installed; see `docs/ipm_break_wifi_diagnostics.md`.
Candidate identity: Nucleo 2026101101. The current powered-trial identity gate
does not approve it. Do not add it to an allowlist simply because it compiles.

Last powered evidence is in
`artifacts/live_bench_20261010/uart_v3_candidate/coast30_motor_trial_r1/report.json`:
the planned 30-second ramp/coast trial stopped after approximately 5.516 seconds
with MCSDK driver protection mask `0x0400`. UART error counters remained zero.
The operator observed rotation followed by coast. Reaching 50 Hz, completing
30 seconds, and the physical cause of driver protection are not established.

## Recorder

`research/ipm_break/first_break_snapshot.h` records TIM1 SR, DIER, BDTR, CNT,
ARR, CCR1/2/3 and GPIOA IDR before clearing break flags or masking the interrupt.
The existing BKE, DP handler, watchdogs and safety thresholds are unchanged.
There are no logging, allocation, waiting, or serial operations inside capture.
Hardware output disable precedes the software ISR when BKE is enabled.

Two immutable records survive STOP and CLEAR:

- `mic_first_break`: first hardware break since boot, including startup/idle.
- `mic_first_start_break`: first hardware break in a START-request window. An
  idle/startup break cannot consume this record. This window begins before the
  existing MC_StartMotor1 call and ends in the existing STOP path. It includes
  queued startup and the software stop transition, and is not proof of RUN.

The separate saturated `mic_break_irq_count` counts IRQ entries with BIF or
B2IF, not electrical edges. A sustained low signal still masks only the IRQ;
the hardware break remains enabled, as in the baseline.

Cached context uses double-buffered publication; an interrupt reads the last
completed bank rather than waiting for a preempted writer. It contains time,
native reference speed, state, fault masks, bus voltage, temperature and command
sequence. These values are telemetry-time samples, not synchronous fault-edge
measurements. No true rotor speed, qualified phase current, or J4 voltage is added.

## Reproducible Offline Preparation

Use a new output directory for each run:

```powershell
.venv/Scripts/python.exe tools/prepare_ipm_break_snapshot.py --outdir artifacts/my_break_candidate
powershell -NoProfile -File tools/build_acim_reference.ps1 -ProjectRoot C:/mic_practice/artifacts/my_break_candidate/nucleo -Workspace C:/mic_practice/artifacts/my_break_workspace
.venv/Scripts/python.exe tools/ipm_break_snapshot_selftest.py --outdir artifacts/my_break_tests
```

Preparation copies the frozen 2026101006 project; it never edits that reference
or the unrelated dirty main sources. Only main.c, the break ISR and the added
header differ. The packet layout, transport CRC/noise policy, timer setup and
protection configuration are unchanged. `package_ipm_break_snapshot.py` verifies
source/artifact hashes and exports RAM symbol addresses from the actual ELF.

Candidate r2:
`artifacts/live_bench_20261011/ipm_break_snapshot/candidate_r2/package.json`.
The final target compilation reports 0 errors / 0 warnings. CubeIDE's initial
clean phase on an empty copied Debug directory reports no clean rule; the
subsequent complete target compilation and link succeed. The generated release
preflight is non-gating and does not authorize HV operation.

## Readback And Limits

Each record is 92 bytes, schema 2, committed by writing magic last. Decode a
saved dump offline:

```powershell
.venv/Scripts/python.exe tools/decode_ipm_break_snapshot.py snapshot.bin --output snapshot.json
```

The package's addresses belong only to its exact ELF. They are not valid for the
currently installed 2026101006 image. No automatic readback or flashing is part
of these tools. A reset, MCU power loss or reset-on-connect erases the records.
Reading with PC-connected ST-Link requires mains physically disconnected, J4
off and the DC bus verified discharged; never connect a PC probe under mains.

A separate paired, passive Wi-Fi diagnostic extension is now implemented;
see `docs/ipm_break_wifi_diagnostics.md`. It uses separate tagged packets and
does not repurpose the normal reply. Both MCU components and HMI are installed,
and software BG capture while outputs were already off has been verified over
Wi-Fi. UART receive integrity and external SD/active shutdown qualification
remain pending. The RAM-only 2026101101 image described above is an earlier isolated
candidate, not the paired release. Low-voltage physical capture/timing also
remains pending. Neither candidate is an approval for a powered run.

PA6 HIGH at IRQ entry with BIF set is consistent with an already-ended low
event; it does not prove interference. PA6 LOW is consistent with an ongoing
active signal; it does not identify overcurrent versus undervoltage. Neither
record determines pulse duration. The J4 supply needs separate measurement if
undervoltage is suspected. Do not weaken BKIN or overcurrent protection to
obtain a longer motor run.
