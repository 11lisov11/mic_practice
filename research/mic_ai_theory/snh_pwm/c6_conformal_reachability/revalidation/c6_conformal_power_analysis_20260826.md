# Exact binomial non-inferiority power plan

- Assumed true coverage: `0.950000`
- Exact lower-bound threshold: `0.920000`
- One-sided error probability: `0.010000`

## Fixed designs

| Probes | Critical successes | Critical empirical coverage | Acceptance power |
|---:|---:|---:|---:|
| 400 | 381 | 0.952500 | 0.467970 |
| 800 | 754 | 0.942500 | 0.853783 |

## Minimum designs

| Desired power | Minimum probes | Critical successes | Achieved power |
|---:|---:|---:|---:|
| 0.80 | 694 | 655 | 0.800754 |
| 0.90 | 897 | 844 | 0.904913 |
| 0.95 | 1069 | 1004 | 0.951162 |

Joint power for two independent 400-probe series: `0.218996`.

Boundary: exact binomial design calculation for independent coverage indicators; it does not repair a failed locked protocol and does not establish model adequacy, recursive coverage, or hardware validity
