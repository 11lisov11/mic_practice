# 30-second V/f profile: offline preparation, not live release

## Confirmed Powered Result

The operator confirmed shaft rotation and mains off after
`stopped_zero_motor_trial_r1`. All seven active telemetry snapshots had zero
UART rejection counters and zero MCSDK current/occurred fault masks. Outputs
were confirmed off at completion. General commissioning remains incomplete.

The frozen Uno 1008 source explicitly sets its ESTOP latch and local fault 4
when its bounded run deadline expires, before forcing outputs off. Thus the
terminal ESTOP signature at approximately three seconds is consistent with the
configured timer, not evidence of a renewed UART fault. The original automatic
report remains failed; it has not been edited to manufacture a pass.

`stopped_zero_motor_trial_r1/operator_result_review.json` separately retains the
operator confirmation and an offline replay with the corrected interpretation.
The replay recognizes the terminal signature only after clean active snapshots,
near the configured deadline, with outputs off and no UART/MCSDK fault evidence.
It does not prove a unique stop cause: the firmware has no dedicated RUNLIMIT
reason in its telemetry. No latch is cleared or live safety check disabled.

## Requested Profile

The maximum is nominal 50 electrical Hz, not an instruction for overspeed.
The installed Nucleo limits ramp slew to 5 Hz/s and uses a minimum ramp duration
of 3 seconds. The native MCSDK ramp manager was compiled and executed unchanged
on the host, using the pinned receiver's duration helper at 500 Hz.

50 Hz plan:

- START with a fixed 50 Hz target; native ramp reaches 50 Hz at 10.000 s.
- Retain the target until 18.020 s.
- Request 0.1 Hz, not zero; native ramp reaches 0.1 Hz at 27.982 s.
- STOP at 30 s. Proposed independent emergency deadline: 33 s.

20 Hz first-stage alternative:

- START with a fixed 20 Hz target; native ramp reaches 20 Hz at 4.000 s.
- Retain the target until 24.020 s.
- Request 0.1 Hz; native ramp reaches 0.1 Hz at 27.980 s.
- STOP at 30 s, with the same proposed independent deadline.

Zero-frequency commands currently switch off PWM immediately. They cannot
implement the requested smooth deceleration. These timings concern electrical
reference generation, not measured rotor speed or a simulated physical motor.
Final rotor standstill is not proven by reference frequency reaching 0.1 Hz.

## DC-Link Constraint

The operator reports no braking resistor and capacitors of 470 and 220 uF.
Their connection is still awaiting confirmation. The following values apply
only if they are parallel, giving 690 uF of reported external capacitance.

For an illustrative upper prior of J=0.0004 kg*m^2, 325 V initial bus voltage,
one pole pair and lossless return of all kinetic energy to that capacitance:

- 50 Hz: 19.739 J, conditional projected bus voltage 403.535 V.
- 20 Hz: 3.158 J, conditional projected bus voltage 338.791 V.

This inertia is a simulation assumption, not a nameplate-derived identified
value. Attached-load inertia, electrical/mechanical losses and any additional
board capacitance are not included. These calculations are neither predictions
of measured voltage nor hardware approval. They show why a full-speed braking
test cannot be released solely from a successful three-second start.

ST specifies the STEVAL-IPM15B input range as 125..400 VDC:
https://www.st.com/resource/en/data_brief/steval-ipm15b.pdf
The existing experimental HMI window remains narrower, at 250..360 V.

## Evidence and Remaining Work

- `vf_30s_50hz_690uf_r1`: native ramp CSV and conditional energy envelope.
- `vf_30s_20hz_690uf_r1`: native ramp CSV and conditional energy envelope.
- `runlimit_profile_regression_r1/report.json`: 43/43 unchanged-source suites.
- Terminal-classification checks: 243 mock scenarios, no hardware commands.

No 30-second live run has occurred. The installed gate still permits one
3-second / 10-Hz trial with a 10-second ARM lifetime. A longer run requires an
explicitly reviewed profile permission and adequate ARM lifetime, not bypassing
the existing limits or simply changing SET RUNLIMIT. Current telemetry remains
unqualified, and the available frequency display is not measured rotor speed.

Await capacitor connection confirmation and choice of first-stage 20 Hz ramp
or preparation of 50 Hz with a coast stop. An active full-speed brake needs
additional regeneration evidence. Mains must remain off during preparation.
