# Legacy AIR56B2 Loss-Balance Audit

Status: **PASS**. Audit replay and algebraic checks only; legacy scientific conclusions remain provisional.

600 existing holdout contexts, 12 simulated parameter samples. No training, optimization, or historical artifact edits.
All cases retained, including any infeasible points. Common fixed current: 0.83 A.

## Shaft-Torque Correction

At fixed current/speed/temperature, add friction torque before evaluating losses:
`Te = Tshaft + B*omega_m + Tc`. Positive differences below mean the legacy evaluation understated loss.

| Current choice | Minimum delta W | Median delta W | Maximum delta W | Corrected infeasible |
| --- | ---: | ---: | ---: | ---: |
| legacy_fixed | 0.419445 | 5.634340 | 38.681766 | 0 |
| legacy_neural | 0.713793 | 4.488406 | 26.241971 | 0 |
| common_fixed_083 | 0.417024 | 5.659049 | 38.921586 | 0 |

## Core-Free dq Identity

Residual: `1.5*(vd*id + vq*iq) - Te*omega_m - P_stator_copper - P_rotor_copper`.
Original/corrected voltages use identical currents and electromagnetic torque within each interpretation.
The corrected leakage is `Lls + Lm_eff*Llr/(Lm_eff + Llr)`.

| Current choice / torque interpretation | Original median W | Original max abs W | Corrected max abs W |
| --- | ---: | ---: | ---: |
| legacy_fixed / legacy | 1.292985 | 8.920787 | 1.705e-13 |
| legacy_fixed / shaft_corrected | 1.426164 | 9.363842 | 1.137e-13 |
| legacy_neural / legacy | 1.200806 | 8.393533 | 1.705e-13 |
| legacy_neural / shaft_corrected | 1.308203 | 8.765408 | 1.705e-13 |
| common_fixed_083 / legacy | 1.292936 | 8.940970 | 1.137e-13 |
| common_fixed_083 / shaft_corrected | 1.428414 | 9.384226 | 1.705e-13 |

## Virtual Wattmeter Limitation

`P_virtual = Tshaft*omega_m + total_loss` is synthetic, not an implemented power estimator.
After both corrections, `P_virtual - (P_dq_corrected + P_inverter_prior) = P_core_prior`.
With legacy torque semantics, that gap is `P_core_prior + P_mechanical` instead.
Core and inverter priors are NOT validated by the core-free identity. No current-carrying iron-loss branch exists.
Voltage/current amplitudes remain approximate proxies, not a complete power-consistent measurement circuit.
Saved actions are not re-optimized; all historical efficiency/policy conclusions remain provisional.

## Reproduction and Provenance

Run with the environment used for this audit (the imported wrapper requires PyTorch):
```powershell
& "C:\mic_practice\.venv-research-gpu\Scripts\python.exe" -B "C:\mic_practice\research\mic_ai_theory\snh_pwm\source\tools\audit_air56b2_loss_balance.py"
```

All audit checks passed: `True`. Absolute numerical tolerance: 1e-9 in W/V/A.
JSON contains every row, input/source SHA-256 hashes, residuals, feasibility counts and integrity checks.

- `air56b2_fidelity_bundle.json`: `5a95aab1a02643f17e4a41f7a2e957cc1de43d5f13d7487a7fbed7ec7748b115`
- `air56b2_policy_benchmark.json`: `7d7a20a2b5b92c4f794a5dd81c5f356ac52e971ee27cbb513884a2a769420d55`
- `audit_air56b2_loss_balance.py`: `ba9a58dec25a69de6deb7fe74c95a130a093bfc39b043c13d3b84e7d3a760336`
- `air56b2_loss_thermal.py`: `29783c4b657f5e38ca6ffe84a534761c1554a5e9f25658c5b120203212d7611c`
- `run_air56b2_measurement_adaptation.py`: `c25b41476490ca44d70e695475b9514f4542a4e1a4539c8bc1df7346dfa59275`
- `air56b2_measurement_context.py`: `fca4435376da30e06385ccfa6f48c3b08be8752ee577f5e3ac2541a8c98e5004`
- `air56b2_measured_loss_fit.py`: `7128ace1114132dead29e5494a4ab692be94af0ebb3c4da11bb58637c241e04e`
