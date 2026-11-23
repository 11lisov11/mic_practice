# Installation and Idle Verification, 2026-10-12

## Final Installed Pair

- Uno Q 2026101205: `uno_peer_r2/uno_build/UNOQ_MOTOR.ino.elf-zsk.bin`;
  SHA256 `afd0c72fc33c1519d9a85b6fd43356057a66048f82d20e1ebbbd56cd5e714714`.
- Nucleo 2026101204: `candidate_r5/nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin`;
  SHA256 `f35dfb3c583b1e6f4822d62f3e7971f3a7cac0e3beed76565f273dbfa203e949`.
- HMI refreshed after the button press: `hmi_stop_candidate_r1/web_hmi/server.py`;
  SHA256 `21bda96fae14b0fa13db27d1fb21edd6f059e6d2037199944bdae50999569276`.
  UI SHA256 `42700af1d5aad3409f49b00ed64c0d615bb490640cad5c8f4139380a6d53aa27`.
  Original installation used `wait_candidate_r6/web_hmi/server.py`, SHA256
  `5b9a25097b8d590db98ddcd37b121f30f573f4465fea67c512231a2f0dc40d15`;
  that frozen file remains unchanged as the baseline.
- Original calibration unchanged: SHA256
  `a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17`.

`install_r4/report.json`: programmer verification, exact Nucleo readback, Uno
loader/sketch verification and HMI hash verification all pass. Live Wi-Fi
confirms both IDs. Operator confirmed mains physically disconnected, J4 off
and measured bus <=2 V before installation. ARM/START/CLEAR counts are zero.

## Installation Findings And Corrections

The old Uno diagnostic whitelist rejected the new peer; snapshot packets also
embedded the old ID. Both peers now agree on 2026101204. Uno control/scheduling
is unchanged apart from its own ID; only the two peer diagnostic headers change.

The first latch draft incorrectly assumed an active-LOW button. MB1367 B1
connects B_USER to VDD; R26 pulls the released input LOW. Final source and IOC
use active HIGH and rising EXTI. ST schematic, sheet 3:
https://www.st.com/resource/en/schematic_pack/mb1367-g431rb-c04_schematic.pdf
Intermediate images 1201/1202/1203 are superseded; do not reuse them.

## Verification

- `selftest_r6/report.json`: 1038 STOP checks, 49 waiting/qualification checks;
  five broken variants detected, including wrong button polarity.
- `peer_selftest_r2/report.json`: 17 matched-peer checks; old decoder rejection
  reproduced as a negative control.
- `hmi_guards_r5/report.json`: five existing HMI guard suites pass.
- Both target builds pass; Uno dynamic-loader check has no TLS issues.
- `installed_idle_r1/summary.json`: 30-second direct Wi-Fi idle check passes.
  Correct UART messages 1615 -> 2216 (+601); bad-frame counters stay zero;
  no HTTP errors; authenticated logs download successfully.
- SAFE, PWM=0, ARM=0, reported bus 0 V throughout.
- Diagnostics valid again: first cause MC_UNDER_VOLT, masks 0x0004/0x0004.
  This was not cleared or represented as powered-start readiness.
- Local latch stays 0 without pressing B1; no false idle stop in final image.

## Pending Physical Test

Operator confirmed pressing B1 USER. Raw status changed from 9 to 141 (0x8D),
and current fault is ESTOP. Operator subsequently confirmed release. The next
10-second direct Wi-Fi observation (`b1_released_idle_r1/release_verify.json`,
11 snapshots) confirms latch retention, SAFE, PWM=0, ARM=0, reported bus 0 V,
and no new UART/HTTP errors. No CLEAR/ARM/START was sent. Active-PWM coast stop, restart inhibition under ENABLE
and explicit release/rearm remain physically unverified on this pair. Host
tests and the idle press are not physical active-PWM timing measurements.

The derived HMI latch initially incorrectly stayed at zero. The HMI-only fix
is installed and verified: `hmi_stop_install_r2/report.json`; API regression
has 70 checks and five existing HMI guard suites pass. First-fault history and
original calibration are preserved. See `HMI_STOP_FIX_REPORT.md`. The first
HMI restart attempt required a sudo password; the retained failed report is
`hmi_stop_install_r1/report.json`. The verified owned HMI process was restarted
under systemd; neither MCU was reflashed.

Accepted preparation waits without a countdown, but new physical qualification
is still required. No attestation was fabricated and the live HMI is not armed
or prepared for a powered run. The 3-second trial limit, 300-ms watchdog and
BKIN remain. This is not an unrestricted powered release.
