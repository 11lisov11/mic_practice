# BKIN DMA diagnostics installed and verified

Date: 2026-10-17, 20:47 MSK.

The candidate pair is live: Uno Q `2026101703`, Nucleo `2026101702`. The Nucleo
image was programmed and verified through ST-Link; the Uno Q image was
readback-verified through OpenOCD. Final live verification returned the same
pair, `SAFE`, PWM=0, fresh telemetry (14–15 ms), and increasing good-frame
counters. Calibration SHA-256 was unchanged. Candidate scope is limited to
capturing/validating BKIN DMA samples and displaying diagnostic state; the
V/f algorithm, PWM generation and control protocol were not changed.

One boot-time `LINK_TIMEOUT` was latched while Uno Q restarted. The host
continued receiving fresh frames, with no integrity, sequence or hardware UART
errors. After checking SAFE, PWM=0, disarmed state, fresh telemetry, zero
MCSDK masks and the exact one-shot timeout signature, one `CLEAR` command was
sent. It cleared the link latch; transport errors and bad-frame counts are now
zero. No START, frequency, or motor command was sent.

With J1/J4 off, telemetry settles at SAFE/PWM=0, Vbus=10 V, IPM=48 °C,
transport errors=0, bad frames=0. The remaining `fault=5`, reason 8,
occurred mask `0x0004` is the expected DC-bus undervoltage while the power
stage is off. The two-point Vbus calibration remains valid. No new BKIN record
exists yet; the diagnostic capture has not been qualified by a new powered
trip.

Validation: candidate BKIN selftest 17/17; installer selftest 6/6; preflight
and final live verification passed. Flash/readback results are in
`../bkin_dma_install_after_reboot_r1/report.json`; current live state is in
`report.json` in this directory.
