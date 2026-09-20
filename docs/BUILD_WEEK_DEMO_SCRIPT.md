# OpenAI Build Week demo script

Target length: **2 minutes 30 seconds**. Keep the motor bench de-energized during the introduction. Show high-voltage operation only after the safety checks and only if the bench is physically ready.

## 0:00–0:15 — The problem

**Voice-over**

> Motor-control research is often difficult to reproduce. A control algorithm may look correct in simulation, while the real bench fails because of PWM overlap, missing dead time, broken telemetry, unsafe transitions, or an encoder problem. MIC AI is my attempt to turn that fragile workflow into a measurable and safety-gated system.

**On screen**

- Wide shot of the bench.
- Labels: UNO Q, STM32 Blue Pill, IPM15 inverter, motor, encoder, logic analyzer.

## 0:15–0:35 — Architecture

**Voice-over**

> The Arduino UNO Q runs the supervisory state machine and web interface. The STM32 generates deterministic complementary three-phase PWM, reads sensors and the encoder, and controls the inverter. Python tools automate build, communication checks, waveform capture, and regression tests.

**On screen**

- Architecture diagram from `BUILD_WEEK.md`.
- Brief close-up of the hardware connections.

## 0:35–0:55 — Why Codex mattered

**Voice-over**

> I used Codex as a repository-scale engineering copilot. It helped trace behavior across embedded firmware, Python tooling, the web HMI, UART telemetry, ADB deployment, and Saleae automation. The real-time controller itself remains deterministic and does not call a cloud model while driving the motor.

**On screen**

- Quick cuts of the repository tree.
- `full_system_preflight.py`, `mic_ai_compare.py`, firmware, and web HMI.

## 0:55–1:25 — Safety and automated evidence

**Voice-over**

> Before applying the DC bus, the preflight checks communication, encoder health, ESTOP behavior, complementary PWM overlap, and dead time. Every bounded sequence finishes with stop and emergency-stop cleanup. Failures are exported to CSV and JSON instead of being hidden behind a successful-looking user interface.

**On screen**

Run:

```powershell
py -3 -u .\tools\full_system_preflight.py --url http://127.0.0.1:18080
```

Then show:

- terminal output;
- Saleae PWM capture;
- exported `summary.json`;
- a visible ESTOP transition.

## 1:25–1:55 — FOC versus MIC

**Voice-over**

> The experiment compares conventional FOC with MIC, a lookup-table policy that adjusts the magnetizing-current reference. MIC is allowed only in a valid steady state. It is disabled on faults, communication degradation, invalid feedback, or excessive speed mismatch.

**On screen**

- Web HMI switching from FOC to MIC.
- Live fields: mode, measured speed, current, `mic_active`, and estimated saving.
- A simple result chart produced from fresh measurements.

## 1:55–2:15 — The result

Use only values measured during the final recorded run. Do not quote placeholder savings.

**Voice-over template**

> In this operating point, both modes maintained comparable speed. MIC changed the magnetizing-current reference while remaining inside the configured current and speed limits. The complete time series and pass/fail summary are exported with the test.

**On screen**

- Side-by-side FOC and MIC traces.
- Highlight measured values and pass/fail thresholds.

## 2:15–2:30 — Closing

**Voice-over**

> MIC AI is not just a motor demo. It is a reproducible bridge between an experimental control idea and evidence from real power electronics. Codex helped make the whole system inspectable, testable, and safer to iterate.

**On screen**

- Motor bench running at a conservative operating point.
- Project name and repository address.

## Recording checklist

- Record horizontal 1080p video.
- Use large terminal and UI fonts.
- Hide Wi-Fi credentials, device serials, personal paths, and private tokens.
- Use fresh test artifacts generated during the recording session.
- Include one uninterrupted shot proving that the UI command reaches the real motor.
- Avoid unverified claims such as “AI reduces losses by X%” without measured evidence.
- Keep mains and DC-bus wiring guarded and out of reach.
