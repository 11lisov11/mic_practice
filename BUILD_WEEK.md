# MIC AI Motor Control

**Codex-assisted embedded motor-control platform for comparing conventional FOC with a safety-gated MIC/LUT policy on real hardware.**

> Build Week note: Codex was used as a development and debugging copilot. The deployed controller does not call an OpenAI model at runtime; deterministic real-time control remains on the microcontrollers.

## The problem

Motor-control experiments often fail for reasons that have little to do with the control idea itself: unstable wiring, unsafe PWM transitions, missing dead time, stale telemetry, broken links between processors, or tests that cannot be reproduced.

MIC AI turns that fragile bench workflow into a measurable system. It combines:

- an Arduino UNO Q as the supervisory controller and web interface;
- an STM32 Blue Pill for deterministic complementary PWM and fast I/O;
- an ST IPM15 / UM2014 inverter stage;
- scalar V/f, FOC, and MIC operating modes;
- an AS5600 encoder for measured shaft speed;
- Saleae-based automated waveform capture;
- safety gates, ESTOP handling, thermal protection, link-failure fallback, and bounded high-voltage test sequences.

## What MIC means here

MIC is implemented as a deterministic lookup-table policy that selects the magnetizing-current reference `Id_ref` from operating conditions. The normal current-control loop remains active. The policy is enabled only when the system is in a valid steady state and is disabled on faults, ESTOP, communication degradation, invalid feedback, or excessive speed mismatch.

This architecture deliberately keeps machine-learning experimentation outside the hard real-time loop while preserving a predictable MCU fallback.

## Why it matters

The project is not merely a motor spinning from a web button. Its main contribution is a reproducible path from an experimental control idea to evidence:

1. build and flash both controllers;
2. verify communication and encoder health;
3. run scalar, FOC, and MIC preflight tests;
4. capture complementary PWM with a logic analyzer;
5. check overlap and dead time;
6. compare FOC and MIC telemetry;
7. finish every bounded test with `STOP` and `ESTOP` cleanup.

The resulting CSV and JSON artifacts make failures inspectable rather than anecdotal.

## System architecture

```text
Browser / phone
      |
      v
UNO Q web HMI + supervisory state machine
      |
      | UART command and telemetry link
      v
STM32 Blue Pill
  | complementary PWM + dead time
  | ADC telemetry + encoder
  v
ST IPM15 / UM2014 inverter -> induction motor

Saleae Logic 2 <--- automated PWM capture and safety checks
Python tooling <--- preflight, comparison, export, diagnostics
```

## Key engineering features

- Complementary three-phase PWM from STM32 TIM1.
- Explicit ESTOP and fault-latched safe states.
- Scalar V/f, FOC, and MIC modes behind one supervisory interface.
- MIC enable gates and rate limits on `Id_ref`.
- Encoder-aware speed and slip validation.
- DC-bus, current, phase-voltage, and thermal telemetry.
- Automated overlap and dead-time analysis.
- Low-voltage HIL preflight before optional high-voltage tests.
- Persistent bounded command runner with mandatory cleanup.
- Web HMI reachable through ADB or a local bridge.

## Reproducible demo

The primary end-to-end command is:

```powershell
py -3 -u .\tools\full_system_preflight.py --url http://127.0.0.1:18080
```

It builds the firmware, checks the device link and encoder, runs scalar and FOC/MIC tests, captures PWM, and exports a top-level summary.

For the FOC-versus-MIC comparison:

```powershell
.\.venv\Scripts\python.exe -u .\tools\mic_ai_compare.py `
  --url http://127.0.0.1:18080 `
  --freq 10.0 --duration 8 --poll 0.05 --warmup 0.8
```

Expected artifacts:

- `timeseries_foc.csv`
- `timeseries_mic.csv`
- `summary.json`

## Safety model

This repository controls power electronics. High voltage must remain disconnected until low-voltage PWM, dead-time, ESTOP, communication, sensor, and fault-handling tests pass. The automated high-voltage stage is opt-in and does not replace proper isolation, current limiting, guarding, and a physical external emergency stop.

## What was built with Codex

Codex supported repository-scale work including:

- tracing control and telemetry paths across Arduino, STM32, Python, and the web HMI;
- generating and refining automated preflight tooling;
- diagnosing UART, ADB, Logic 2, encoder, and PWM integration failures;
- tightening fail-safe behavior and bounded cleanup paths;
- documenting wiring, test procedures, and expected evidence.

The human author defined the hardware architecture, performed the wiring and bench work, reviewed changes, and validated behavior against real measurements.

## Current status

The software stack, safety tooling, wiring documentation, and low-voltage HIL workflow are implemented. Final competition evidence should include a short real-hardware video and fresh exported results from the fully assembled motor bench.

## Repository map

- `UNOQ_MOTOR/` — UNO Q firmware, state machine, FOC/MIC logic, UI bridge.
- `bluepill_uart_pwm_pio/` — STM32 firmware for PWM, sensing, encoder, and UART.
- `web_hmi/` — browser control and telemetry interface.
- `tools/full_system_preflight.py` — end-to-end regression runner.
- `tools/mic_ai_compare.py` — FOC versus MIC measurement workflow.
- `tools/ui_pwm_suite.py` — automated PWM capture and validation.
- `docs/MIC_AI_Runbook_RU.md` — MIC experiment procedure in Russian.
- `docs/IPM15_Runbook_RU.md` — inverter bring-up procedure in Russian.

## Submission assets still needed

- 2–3 minute demo video.
- One architecture image or clean bench photograph.
- One logic-analyzer screenshot showing complementary PWM and dead time.
- One concise FOC-versus-MIC result chart.
- A verified open-source license decision for all repository components.
- Final eligibility check against the official challenge rules.
