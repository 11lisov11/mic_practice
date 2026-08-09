# C6-BCR confirmatory replication audit

- Replication pass: `true`
- World novelty established: `false`
- Hardware ready: `false`
- Root seeds: `[20260810, 20260811]`
- Total repetitions: `48`
- Aggregate held-out coverage: `0.950625`
- Target coverage: `0.950000`
- Aggregate undercoverage p-value: `0.716102`
- Aggregate OOD coverage: `0.546771`
- Median C6/raw 5D hypervolume ratio: `0.739117`
- C6 sharpness wins: `42/48`
- Paired sign-test p-value: `5.04374e-08`

## Checks

- [x] `at_least_two_confirmatory_series`
- [x] `all_individual_audits_pass`
- [x] `root_seeds_are_unique`
- [x] `all_split_seeds_are_unique_across_series`
- [x] `protocol_is_identical_across_series`
- [x] `at_least_48_total_repetitions`
- [x] `aggregate_coverage_not_significantly_below_target_1pct`
- [x] `aggregate_median_hypervolume_reduction_at_least_10pct`
- [x] `aggregate_paired_sharpness_sign_test_below_5pct`
- [x] `aggregate_ood_limit_exposed`
