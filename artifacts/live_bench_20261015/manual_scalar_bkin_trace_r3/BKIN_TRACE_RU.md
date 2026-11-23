# BKIN trace candidate 2026101507 / 2026101506

This is a separate, uninstalled diagnostic pair derived from the working pair
2026101505 / 2026101504. The installed firmware,
live HMI, calibration, and archived run results were not changed.

## What it records

On each START, Nucleo uses the previously unused DMA2 channel 1 and repurposes
TIM2 after MCSDK has completed its one-time boot synchronization. The recorder
holds TIM2 TRGO at reset and triggers one GPIOA IDR read each microsecond into a
1024-word circular buffer. PA6 is the BKIN/SD digital input. When TIM1 reports BKIN/BK2, the new
recorder stops only its own timer and DMA before the existing first-break
snapshot and MCSDK handler continue. It preserves the most recent 1.024 ms,
packs PA6 into a 128-byte bit trace, and sends seven CRC-protected D2 pages
through the existing UART only after outputs are confirmed off. Uno exposes the
decoded trace through the HMI button **«Считать снимок BKIN»** and at
`GET /api/bkin-trace`; no Saleae lead or PC ground is involved.

The existing D1 first-break snapshots keep their 92-byte format. UART control
frames, PWM generation, ADC setup, TIM1 break configuration, and V/f profile are
not modified. The HMI enables only the matched pair above.

## Limits and status

The trace measures one digital PA6 signal at 1 MHz. It does not measure J4,
phase voltage, or qualified motor current, and by itself cannot identify the
physical cause of the IPM trip. Its time zero is the final DMA sample before
BKIN interrupt handling, not a hardware timestamp of the electrical edge;
sub-microsecond pulses are not resolved. If fewer than 1024 valid samples were
collected after START, the returned prefix is marked unknown.

`installed=false`, `hardware_commands=0`, and `hv_release_approved=false` are
intentional. The candidate has not been programmed or electrically qualified.
Do not use the predecessor pair's results as qualification for this new image.
The next bench step is a controlled low-voltage compile/readback and then a
single supervised trip capture; no powered trial is authorized by this package.
