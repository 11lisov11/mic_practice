# UART error capture candidate (offline)

This is a separate, uninstalled diagnostic build based on the preserved working pair `2026101507 / 2026101506`.

On the first Nucleo-side UART transport fault, it freezes the received command bytes, per-byte USART marks, parser result, fault class, timestamp, and NE count. The parser now distinguishes a CRC32C mismatch from either sync-byte error, parity/framing/overrun, a partial-frame deadline, sequence rejection, watchdog timeout, and RX-buffer overflow. The existing bounded recovery and fail-stop threshold are retained.

After the controller has reported safe-off and the motor outputs are disabled, Nucleo sends the frozen record over the existing UART in five CRC-protected D3 pages. Uno accepts it only for the matching Nucleo build and a fresh outputs-off state. The HMI status parser and fault recorder retain the classification, raw frame, and per-byte flags; the existing “Код контроллера” field displays them.

The package contains Uno Q build `2026101701` and Nucleo build `2026101702`. Neither image was flashed. No hardware command, motor start, calibration write, or live stand test was performed. Calibration and the installed pair remain unchanged.

## Offline checks

- Nucleo CubeIDE build: 0 errors, 0 warnings.
- Uno Q build and loadable-extension check: passed.
- Host self-test: CRC mismatch capture, both sync errors, UART FE marking, partial-frame timeout, unchanged two-drop tolerance/fail-stop, and D3 record round-trip all passed.
- Host replay check: valid RUN heartbeat still advances its sequence and a replay still fail-stops.
- HMI self-test: status parsing, human-readable fault detail, and fault-recorder retention passed.
- Package check: paired protocol headers, build identities, binary lengths and SHA-256 values passed.
- Python and JavaScript syntax checks passed.

The separate release preflight remains closed because assembled external-soft-start HIL and IPM SD/BKIN hardware-trip evidence are absent. This is a built diagnostic candidate, not a hardware-qualified release.
