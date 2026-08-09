# SNH-PWM long-horizon revalidation

- Host ready: `true`
- Hardware ready: `false`
- Scenarios: `31`
- Monte Carlo trials: `30`
- Duration per trial: `0.200000 s`
- Speed error vs FOC-SVM: better `26`, worse `3`, inconclusive `2`
- Max plant current: `5.652610 A`

## Checks

- [x] `hardware_claim_false`
- [x] `all_required_scenarios_present`
- [x] `scenario_count_at_least_31`
- [x] `mc_trials_at_least_30`
- [x] `duration_at_least_0p2s`
- [x] `duration_gate_pass`
- [x] `paired_common_random_numbers`
- [x] `controller_present_in_all_scenarios`
- [x] `no_unexpected_critical_faults`
- [x] `expected_fault_injection_response`
- [x] `trip_threshold_present`
- [x] `plant_current_below_trip`
- [x] `paired_effects_complete`

## Warnings

- AI confidence fallback occurred in: regeneration, sensor_delay, sensor_dropout, speed_sensor_failure
- speed-error comparison is not universally superior: worse=3 inconclusive=2
