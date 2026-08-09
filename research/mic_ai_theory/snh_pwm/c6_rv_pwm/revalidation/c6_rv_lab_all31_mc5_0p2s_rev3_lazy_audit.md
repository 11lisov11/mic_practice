# C6-RV-PWM mathematical audit

- Exploratory mathematical ready: `true`
- Publication protocol complete: `false`
- Novelty established: `false`
- Hardware ready: `false`
- Scenarios: `31`
- Paired trials: `5`
- Duration per trial: `0.200000 s`
- Speed error vs FOC-SVM: better `29`, worse `1`, inconclusive `1`
- Max observed current: `4.580244 A`
- Viability predecessor triggered: `true`
- Viability predecessor rejected a candidate: `false`

## Checks

- [x] `host_only_claim`
- [x] `novelty_not_overclaimed`
- [x] `at_least_six_scenarios`
- [x] `at_least_three_paired_trials`
- [x] `at_least_0p05s_exploratory_duration`
- [x] `proposed_controller_present`
- [x] `c6_numeric_equivariance`
- [x] `candidate_set_reduced`
- [x] `no_observed_software_safety_violation`
- [x] `no_unexpected_fault_latch`
- [x] `expected_fault_injection_response`
- [x] `current_trip_threshold_present`
- [x] `observed_current_below_trip`
- [x] `falsification_declared_incomplete`
- [x] `paired_speed_effects_complete`

## Warnings

- viability predecessor was triggered but did not reject a candidate; its benefit is not demonstrated
- speed error is significantly worse than FOC-SVM in 1 scenarios
- counterexample search found a parameter region with positive speed regret
- publication protocol requires 31 scenarios, MC30 and at least 0.2 s per trial
