# MIC Project Chat Handoff, 2026-10-12

## Start Here

### CURRENT, 2026-10-15 Moscow: basic 5->10->5 PASS; extension tripped runtime Break near12.7Hz

Permanent installed pair remains Uno1505/Nuc1504; original calibration unchanged.
Operator freshly confirmed powerbank, closed stand, motor connected, mains/J4 ON,
PC USB and ALL Saleae probes/GND removed before the following runs.

1. r3/powered_manual_1792055829149795500/report.json: PASS5->10->5, accel2/decel0.5,
   51 active samples/34.531s observed active span; request-to-end36.359s (not exact
   shaft-on time). All targets settled, active session survived old30s ARM TTL.
   Vbus315..319, fatal UART/bad/CRC/sequence0, no runtime MCSDK faults.
   User: "Да, вращался ровно, ускорение и снижение заметны". This visual confirmation
   applies to this basic profile only, not measured shaft RPM. One archived startup-only
   DP CLEAR before START, no runtime acknowledgement. STOP/PWM0/ARM0 confirmed.
2. r3/powered_manual_1792056019094763800/report.json: FAIL attempted5->20->50->20->5.
   One START, zero CLEAR. Settled5, then runtime TIM1 Break / MC_DP_FAULT0x0400
   while ramping toward20. Last valid active reference12.6Hz, cached fault12.7Hz.
   20/50 NOT reached/qualified. UART fatal/bad/CRC/sequence remained0; no bytes dropped.
   First_start_window raw tick291465, context291422 (43ms old), state6/seq116,
   Vbus317, temp52C; BIF1/B2IF0/BKE1/MOE0, PA6HIGH at ISR. Single pin sample
   does not identify SD pulse duration or physical source. No qualified phase current/J4.
   STOP confirmed SAFE/PWM0/ARM0/estop1. No CLEAR or retry after runtime fault.

User questioned requested power OFF. We clarified it is not needed to read logs and
kept mains/J4 ON, stand closed, wiring unchanged. Do NOT claim OFF or power-removal
qualification. Actual stopped powered observation r3/powered_stopped_after_break:
11samples/10.969s/+221 replies, bus318, UART fresh/fatal0, all observed outputs OFF,
fault preserved, no START/CLEAR. Physical state flags remain powerbank/ON, PCUSB/probes
removed; no authorization to program through PC while this state remains ON.

Equipment question answered: user has only the existing Saleae. Saleae inputs share USB
ground with PC, so do not connect it to energized HOT_GND. Arduino USB-C can host devices,
but official Saleae Logic software does not support ARM Linux on Uno Q, and Saleae states
it is the only supported software path to the analyzer. Do not ask again about isolated
scope availability. Hardware-free next route: Nucleo circular DMA ring-buffer for PA6/BKIN,
freeze at first Break, publish separate passive Wi-Fi pages only after outputs stop.
No protection weakening. Design note r3/hardware_review/next_step_sd_capture_ru.md.
Not yet implemented or built. A single Nucleo programming update requires power off and
independent safe-bus verification; log analysis itself does not. Current fault remains latched.

Static source audit: at10Hz current V/f amplitude law jumps20Vpeak to35.921Vpeak
(FLUX_K0.5717009, offset20, threshold10). Not a proven cause: basic10Hz passed,
runtime fault was later near12.7, no current/SD recording. No blind boost/filter/BKIN
changes, no automatic retry. Save success separately from full50 failure in Session.
Aggregate: r3/hardware_review/hardware_verification.json; actual_runs.png plots saved
field-reference/Vbus telemetry, NOT PWM waveform or rotor speed. All source evidence
retained. qualification.json is frozen pre-install/offline proof; do not relabel it as
full-range physical qualification. Final installed code and calibration remain unchanged.

### PREVIOUS: R3 installation before powered runs

User replied "готово" to exact mains/J4 OFF + independent meter<20 V + both PC USB question.
Fresh enumeration showed Uno3880458060/COM10 and ST-LinkCOM13. HMI initially503 method get
not available after cold Linux boot (uptime1minute, arduino-router active). A verified-only
reset of EXISTING1503 Uno image using tools/verify_unoq_sketch.cfg restored RPC; no flash
write in that recovery. Log Session/manual_r3_verify_existing_uno_reset.log. No user cable
reconnection or Linux router restart/password needed. Fresh SAFE/PWM0/ARM0/Vbus10/age9ms.

Installed artifacts/live_bench_20261015/manual_scalar_working_pair_r3, Uno1505/Nuc1504.
Installer completed normally: Nuc verified write+full readback equal, Uno upload verified,
HMI/static staged+replaced with backup, calibration original SHA unchanged.
HMI SHA0c6f750862b1425a25b9e3a12a3cdff74128fe2688e759c1be8fa02e6e595118.
manifest.installedTrue; root recovery history r1->r2->manualr1->manualr2->manualr3.
Session.manual_scalar_candidate points r3, pending_manual_scalar_candidateNone.

Archive before programming fault acknowledgement in r3/installation:
before_programming_fault_acknowledgment.json + logs_before_programming_fault_acknowledgment.txt.
Exact cutover LINK_TIMEOUT: transport7/bad1/first_reason13/last_bad13/masks0/0/
UARTflags0, no recorded break; stopped/off/bus10/independent<20 physical confirmation.
One STOP+CLEAR acknowledged that known programming gap. No further CLEAR or START.
After: SAFE/PWM0/ARM0/fault0, transport/bad/integrity/sequence0, actual reference0/valid1,
manual capability1, accel2/decel0.5/downmodeRAMP/freqcmd0. Eight stopped real samples,
observed7.703s/+154 valid replies, no changes to calibration. installation/report.json and
idle_samples.json. Not a powered or active-waveform qualification.

HISTORICAL PHYSICAL QUESTION AT THIS CHECKPOINT: both boards to powerbank,
PCUSB+allSaleaeprobes/GND removed, closed stand, ON15V+mains throughsoftstart, motor stays.
Need user "платы на повербанке, питание включено" before new START. Current Session flags
operator_all_power_off_confirmedTrue/meterBelow20True/mainsFalse/J4False/pcUSBdisconnectedFalse,
manual_scalar_powered_preparation_confirmedFalse/operator_powerbank_and_power_on_confirmedFalse.
Do not infer ON from elapsed time or old powerbank reply. Once fresh reply arrives set
powerbank/preparation/pcUSBdisconnected/saleae_all_probes_disconnected/mains/J4True and
powerOFF/meterBelow20False. Then fresh status+run tools/run_manual_scalar_powered.py --run.
Runner exact1505/1504,5->10->5,accel2/decel0.5,atleast36s manual then STOP; independent operator
watchdog and all current wire guards preserved. Zephyr bit32 NE-only is advisory in host.
No reflash or calibration changes for that test; no fixture or motor disconnection.
No real50Hz/decel/continuousTTL/newactivePWM waveform yet claimed. Physical motor rotation
needs operator observation; field frequency is not measured rotor speed. Old powered
attempts remain separate, detailed in PREVIOUS below. USB/Saleae not isolated from HOT_GND.

### PREVIOUS: r2 installed1503/1502; r3 correction prepared before installation

Latest user confirmed original programming state: mains/J4 OFF, meter<20 V, both PC USB;
authorized flash and verification that slider changes PWM. Installed manual r1 (1501/1502),
then immediately found real RouterBridge uses String rpc_get, whereas feature initially
extended only the MessagePack array. Corrected actual text producer and decoder in r2
(1503/1502), Nucleo not rewritten but full readback rechecked. All writes verified,
original calibration SHA a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17 unchanged.
Installed HMI SHA964252beaceabe86098b40f8067eb32d2ef8649b67a7179673dfdcf8aff431e2.

Real Chrome -> WiFi HMI -> Uno accepted slider0,5,20,50,20,5,0 and accel2/decel0.5.
Evidence r2/physical_idle_slider/browser_slider_real_hardware.json and report.json.
Actual Saleae12.06272s at4MHz: all6 inputsLOW, no active PWM proof; probe continuity
not re-established by staticLOW. Saved capture_absolute/idle.sal +CSV. First relative
export failed due app working-directory permissions; corrected absolute path succeeded.
Separate30s idle collector interrupted when both USB disappeared during operator
transfer; no30s continuous result claimed. Screenshot installed_manual_controls.png
in output/playwright/manual_scalar_20261015 is actual installed UI. The other old
manual_controls.png is MOCK. Isolated Chrome manual-live closed; no heartbeat left there.

User then freshly confirmed powerbank, PC USB+Saleae probes/GND removed, mains/J4 ON.
Two START attempts on r2 are archived, both STOP/SAFE/PWM0/ARM0 confirmed:
- powered_manual_1792054480579761100: host monitor falsely rejected Uno cumulative
  UART_ERROR_NOISE flag32/count1. Actual wire fault/CRC/sequence0, MCU masks0/0.
  Host fixed: NE-only Zephyr bit5 advisory; other flags/dropped bytes/CRC/sequence/
  timeout remain rejected.17 guard checks in r2/host_run_guard_correction.json.
- powered_manual_1792054565059339000: wire remained healthy; field reference0
  throughout~8s despite RUN and local Uno reference5. Not qualified as smooth ramp.
  Root cause in actual MCSDK mc_interface.c MCI_GetMecSpeedRefUnit: it returns
  fRotorFreqRef_RPM, updated only by VF_CL. VF_OL updates ramp manager/flux frequency.
  Must use ACIM_VF_GetMecSpeedRefUnit instead. No further START until correction.
  Initial cold-start UV/DP0x404 record was archived and acknowledged exactly once
  before firstSTART: first_since_boot MOEfalse/start_windowfalse/contextinvalid/seq0,
  first_start_window not captured. Second attempt had fault0 and no CLEAR.

R3 artifacts/live_bench_20261015/manual_scalar_working_pair_r3 READY1505/1504.
Recipe tools/prepare_manual_vf_reference_fix.py, DO NOT re-run over frozen package.
Only Nuc source differences vs r2: Inc/break_wire.h, Src/main.c, Src/mc_interface.c.
Fix getter, plus segment continuation uses MC_HasRampCompletedMotor1 rather than
rounded integer equality (down ramp can round to next integer long before completion).
Uno peer build/tag/diagnostic identity updated1504, Uno1505. Static unchanged.
R3 HMI SHA0c6f750862b1425a25b9e3a12a3cdff74128fe2688e759c1be8fa02e6e595118.
Builds PASS Nuc0errors/0warnings (build wrapper exit2 is old non-gating missing separate
hardware release preflight, not compiler failure); Uno loaderPASS. qualify-onlyPASS.
Actual SDK ramp/VF_OL flux/API functions executed140073 assertions incl old zero-getter
negative control and early-integer-rounding regression. vf_reference_selftest/report.json.
UART proof tests_completion/report.json2106+4 mutations+oldNEnegative; manual tests_manual_r2
2103 Nuc/9308 Uno/33 HTTP; textRouterBridge20; normalHTTP42;5 guard suites.
manifest uart_selftest_report points tests_completion. No R3 hardware writes yet.

PENDING PHYSICAL QUESTION: switch mains/J4 OFF, independent meter<20 V, both USB PC.
Leave motor connected, preserve calibration. Existing old powerOFF flags are FALSE;
user must answer before installer. Once confirmed set session flags operator_all_power_off_confirmed,
dc_bus_meter_independent_below_20v_confirmed True, mains_on/j4_15v_on False,
pc_usb_disconnected False, manual_scalar_powered_preparation_confirmed False.
Then installer --candidate ...manual_scalar_working_pair_r3; supports1505/1504 and actualSDK proof.
After full verified install archive programming timeout before a single exact known STOP/CLEAR.
Update Session.manual_scalar_candidate from r2 to r3 only after successful install.
Then ask one physical transfer/power-on confirmation and run tools/run_manual_scalar_powered.py --run.
Runner now targets final1505/1504,5->10->5,2Hz/s up/0.5 down,36s min manual session then STOP.
Fresh manual_scalar_powered_preparation_confirmed required. No automatic retries/CLEAR loops.
No actual50Hz/downshift/activePWM waveform/newcontinuous expiry yet proved. Motor speed/current
unqualified. Saleae and PC are not galvanically isolated from HOT_GND under mains.
No need to disconnect motor, recalibrate, ask PSU model or use old fixture firmware.
No agents, goals, automation, commits, PRs, or worktrees created. Preserve unrelated dirty files.

### PREVIOUS PREPARATION: permanent manual1501/1502 compiled/qualified, before installation

User requests continuous scalar0..50 Hz control, acceleration and coast STOP,
without braking resistor. Clarified lower target must automatically settle
to reduced frequency without new START. Candidate:
artifacts/live_bench_20261015/manual_scalar_working_pair_r1, Uno1501/Nuc1502.
Source transforms tools/manual_scalar_sources.py/manual_scalar_web.py,
shared tools/manual_scalar_control.h, recipe prepare_manual_scalar_pair.py.
DO NOT re-run recipe after qualification: it resets mutable manifest proof
pointers and refreshes source mtimes. Sources/binaries/tests now match.

New mode explicitly uses SET RUNMODE MANUAL, SET RUNLIMIT0 and CONTROL HEARTBEAT.
Uno independently ESTOPs after3s without operator pulse; old bounded profile
keeps positive backup runlimit. HMI forwards authenticated operator pulses,
running manual session survives total ARM expiry, all runtime health guards
retained. Accel0.1..50 Hz/s, decel0.1..5 Hz/s; slow ramps segmented<=60s.
Default decrease stays enabled and ramps down in short segments. Nucleo pauses
at350 V, resumes<=340 V, protects by stop>=360 V. Hardware/load behavior NOT
yet verified. STOP/0 Hz is coast. Optional stopped-configured downmode COAST.
Scalar command unused voltage bytes10..13 now carry tagged rate; service/brake
bytes14..38 stayzero, CLEAR allzero unchanged. UART NE r2 header unchanged.
Reply A0/A1 carries field-reference/hold only when no retained first fault;
all faults retain90 diagnostic format. Decoder accepts new tag only for1502.
RPC array99 fields; stale field reference is not substituted into fresh freq.
Original calibration and all core measurement/PWM/model/protection source
files unchanged. New matching pair audited into HMI calibration identities.

QUALIFIED qualification.json: both target builds, Nuc0errors/0warnings,
loader check passed, source/image hashes verified. tests_final2106 with4
guard mutations and old NE negative control; tests_manual_r5:2103 Nuc,
9308 Uno,33 HTTP/RPC cases; selftest42 normal HTTP cases;5 guard suites at
hmi_guards_final/report.json. Actual Chrome against local mocked RPC tested
independent rate fields, START,50->20 while RUN, active beyond ARM expiry,
STOP. browser_qualification.json binds all static hashes; screenshot in
output/playwright/manual_scalar_20261015/manual_controls.png is a MOCK.
Browser manual-scalar-20261015 closed and local preview process38627 ended.
No live ARM/START/firmware/calibration writes in this preparation.

Latest actual hardware: STILL1415/1414; fresh SAFE/PWM0/ARM0/Vbus3 V,
UART transport0, fault5 expected low bus. Actual BOTH PC USB detected:
ADB3880458060 device/COM10, ST-Link COM13. This supersedes old powerbank/324 V
snapshot but DOES NOT establish independent discharge or J4/mains OFF.
Session.pending_manual_scalar_candidate points new candidate;
dc_bus_meter_independent_below_20v_confirmed resetFalse. Current physical
QUESTION PENDING: confirm mains and15 V OFF, independent meter<20 V.
Motor remains connected; do not ask to reconnect USB already observed.

After this answer set operator_all_power_off_confirmed=True,
dc_bus_meter_independent_below_20v_confirmed=True,mains_on=False,j4_15v_on=False,
pc_usb_disconnected=False; fresh SAFE/low bus + identities/hashes first.
Then run tools/install_uart_recovery_working_pair.py --candidate ...manual_scalar_working_pair_r1.
Installer now accepts1501/1502, requires manual/static/browser proofs, stages
three static assets, backs up server/static and replaces while HMI paused.
One permanent pair, full Nuc readback, verified Uno write, original cal SHA.
Session validates chained r1->r2->manual and manifest hmi_guard_report pointer.
No install yet, manifest.installedFalse. No approval request needed: feature
request authorizes update; pending question is physical state for programming.
Do NOT flash on stale flags or while J4/mains are live.

Programming timeout may require archive/exact one acknowledged STOP/CLEAR
under power OFF as previous installs; no blind CLEAR loop. New startup UV
remains physical, do not relabel as UART. After installation prove stopped
idle, actual operator heartbeat, full new RPC/UI fields and preserved cal.
Never claim real50 Hz/decel/hold qualification from local mock tests.

### PREVIOUS, 2026-10-15 Moscow: browser key missing; verified key copied privately

User screenshot shows disabled Пуск and HV error: control access key is missing
or invalid. Browser localStorage unoqControlToken is empty/stale; the saved
PC control token was accepted by a normal authenticated operator-heartbeat POST.
Evidence manual_hmi_r1/browser_key_verification.json. No ARM/START, no firmware
or calibration writes; fresh SAFE/PWM0/ARM0/Vbus324 V/UART0. This test heartbeat
does not prove browser login. Saved key copied to Windows clipboard with
Set-Clipboard without printing the value; operator must paste into top
Доступ к стенду / Ключ управления field and click Применить, then normal HV ARM
and Пуск. Do not paste the key into the ARM phrase field or expose it in chat.
Browser automation remains unavailable (kernel assets missing), so field entry
was handed to the operator. No auth bypass or server auth setting change.

### PREVIOUS, 2026-10-15 Moscow: manual UI prepared, operator START pending

User asks to proceed with manual control. Fresh read: WORKING15/14, SAFE/PWM0/
ARM0/fault0/Vbus324 V/valid temperature48 C/UART transport0; previous NE8,
accepted6/drop4 unchanged. HMI and original calibration hashes verified.
Sent only MODE VF and SET FREQ5; confirmed SAFE/PWM0/ARM0 and frequency setpoint5.
NO START or ARM, no firmware/calibration writes in this preparation. Evidence:
artifacts/live_bench_20261015/manual_hmi_r1/before_full.json and preparation.json.

Manual UI at http://192.168.1.138:8080/ uses VF, frequency slider, ARM 310V
confirmation/normal HV arm, Пуск/Стоп. Current run limit15s and browser operator
heartbeat remain. First manual frequency range3..5 Hz; acceleration not adjustable
in installed firmware. Operator will press START; do not claim a new manual run
or frequency-change result without evidence. Mains/J4 remain ON, motor connected,
both controllers on powerbank, PC/Saleae absent. Do not request power-off or
fixture swap merely to use existing controls.

Served index.html/app.js archived in manual_hmi_r1/served_static for exact labels.
open_in_codex browser request returned queued; do not claim the panel was rendered.
CUA browser initialization failed with missing kernel asset path, no UI actions
performed; API/status and source inspection succeeded. Browser token/session
authorization was NOT verified: status operator-heartbeat0 before opening panel.
Do not reveal the existing control token in output/URLs. If operator sees a
control-key prompt, handle authentication before ARM/START; no auth bypass.

### PREVIOUS, 2026-10-14: r2 powered scalar run PASSED; smooth rotation confirmed

Installed WORKING Uno2026101415/Nucleo2026101414 completed one normal5 Hz START
to ordinary host STOP (nominal stop10s after START request, MCU backup15s).
20 active samples span8.391s,19 samples at5 Hz reference span7.828s; these
are sample intervals, NOT measured electrical run duration or rotor speed.
User confirmed this r2 motor rotation was smooth: «ровно врзался». Current
report physical_rotation_verified=True; rotor speed/current remain unqualified.

Evidence: uart_recovery_working_pair_r2/powered_vf_1792011214155394100/report.json,
samples.json, logs.txt, before_clear_full.json. Before START exact cold-start
UV|DP snapshot0x404 archived: first BKIN boot/MOE0/context unavailable/seq0,
no start-window break. One justified CLEAR yielded clean SAFE. One START,
no retry, no firmware or calibration writes. NE observed0->8, accepted0->6,
recovered drops0->4; UART transport/bad/integrity/sequence0 throughout and
MCSDK fault masks0/0 after clear. Active Vbus318..321 V, response age max91ms.
Normal HTTP START200, STOP200, final SAFE/PWM0/ARM0/fault0 verified.

User challenged proposed power removal; request rescinded because it was an
additional transition test, not needed to complete this successful run.
Mains and J4 REMAIN ON by operator choice, both boards on powerbank, PC USB
and Saleae removed, motor connected. Latest fresh Vbus323 V, SAFE/PWM0/ARM0,
UART0/MCfault0. Do NOT treat the bus as discharged or reconnect PC.
90s read-only collector retained power_off_transition_samples.json/errors.json,
but actual power stayed ON322->323 V: powered_stopped_idle_report.json explicitly
labels it powered idle, NOT power-off evidence. No new network/UART errors.
The earlier r1 power-off result remains separate historical evidence.

Current Linux boot e20a19c7-18e6-45c8-a2da-c9fa2b944a93 after powerbank transfer.
Installed HMI8680ac48bc10de88a79a8abb458d46a771dc40b948bf7beb5eb033fca78216d7
and original calibration hashes rechecked unchanged after successful run.
qualification.json and installation/report.json now point to real powered proof;
their original hardware_commands0/start_commands0 describe offline/installation
phases, not the subsequent powered START. Online acceleration remains absent.
No pending power-off confirmation or new firmware action required for this run.

### PREVIOUS INSTALLATION CHECKPOINT, 2026-10-14 20:48 UTC / 23:48 Moscow

User acknowledged both USB connected and independently checked residual<20 V,
all mains/J4 OFF, motor remains connected. Both actual devices visible: ADB
3880458060/COM10, Nucleo ST-Link/COM13. Fresh prewrite SAFE/PWM0/Vbus0 V,
old13/12 identities, no UART errors. r2 WORKING1415/1414 now INSTALLED and
both writes verified, Nucleo full readback matched. Primary HMI
8680ac48bc10de88a79a8abb458d46a771dc40b948bf7beb5eb033fca78216d7.
Original calibration byte-identical and accepted. RPC resumed without USB
recovery. Current Linux boot199f9dfb-997c-463a-90a6-2c0062703bbf.

Known programming timeout LINK_TIMEOUT7/bad1/last_bad13 was archived, no UART
flags or NE, masks4/4 (zero-bus undervoltage), and acknowledged exactly once
with STOP/CLEAR while all power OFF. Physical undervoltage retained.
Actual post-update idle PASSED:31.157s/42 samples/+595 valid replies/no new errors.
Final SAFE/PWM0/ARM0/Vbus0 V/UART transport0/bad0, recovered-discard1 cutover
history, expected undervoltage fault5/masks4/4. MODE VF/SET FREQ5 prepared.
No START/ARM performed on r2 yet. Proof in r2/installation/report.json,
idle_samples.json, programming_timeout_before_clear.json and full saved logs.
Installed source/image hashes match qualification.json; current Session validates
history r1->r2. Historical fixture writes remain disabled.

Runner tools/run_uart_recovery_powered_vf.py now derives expected pair from
validated installed working_pair, slices commands to the current invocation;
runner_precheck_test.json proves new pair/NE metadata accepted and old pair/real
faults rejected. Physical speed/current remain unqualified. Acceleration unchanged.

PENDING physical question: transfer both boards from PC USB to powerbank, keep
Saleae disconnected, close stand, ON15 V/mains via original soft-start, report
ready. After acknowledgment set pc_usb_disconnected/mains_on/j4_15v_on and current
operator_powerbank_and_power_on_confirmed. Verify fresh pair15/14/stopped telemetry
and unchanged HMI/calibration hashes, then run one normal5 Hz/10s host observation/
15s MCU backup with operator heartbeat using the prepared runner. Archive exact
cold-start UV/BKIN before one justified CLEAR; no repeated clears/unexplained
fault acknowledgment. User already authorizes the motor work. No recalibration,
no motor unplug, no new firmware for this next run. Powered validation of r2 is
still pending; r1 physical rotation result must NOT be relabeled as r2 success.

### PREVIOUS CHECKPOINT: r1 motor rotation confirmed; r2 prepared

Installed pair is still1413/1412 (r1). User confirmed motor rotation during the
explicitly requested repeat: «да вращался четенько ура». Two actual START commands
were sent; a third preparatory invocation sent NO START/CLEAR because the retry
script checked the retained fault too early. That script ordering was corrected.
First START HTTP timed out and tripped NE; second START HTTP200 confirmed RUN.
Second trace includes VF_RUN/PWM1 at reported reference2.68 and5 Hz, then UART
NOISE_REJECTED5/reason12/NE4, MCUstateRUN6/seq149, masks0/0. NE counters3->5,
accepted1->2, dropped1->2; a discard appeared before the new NE mark. Do NOT claim
ten-second stable operation or measured rotor speed. Rotation is physically
confirmed; reference frequency is not a qualified speed measurement.

Both actual failed START traces retained under r1:
powered_vf_1792005571186497600 (first),
powered_vf_1792005837590319500 (requested repeat, physical_rotation_verified=True).
powered_vf_1792005776086698600 was a preparatory assertion, no START/CLEAR.
Startup0x404 is MC_UNDER_VOLT|MC_DP_FAULT, NOT MC_SW_ERROR (0x80). Its first
BKIN record was at boot1178ms/MOE0/context unavailable/before START; it was
acknowledged once. Powered UART faults had no MCSDK fault bits. The requested
repeat cleared only the exact retained fault of our own prior START, after
checking immutable diagnostic identity and no start-window BKIN; no blind loop.

User then confirmed mains/J4 OFF, both boards remain on powerbank. Actual
post-switch30.719s/39 samples/+596 good replies, no network/new UART errors,
SAFE/PWM0 throughout. Bus245->187 V during that observation; do not call this
discharged or reconnect PC from that old reading. Later fresh telemetry11 V.
First-fault UART record remains latched and preserved; no post-run CLEAR.
Power-off evidence confirmed_power_off_report.json/confirmed_power_off_samples.json
under the requested-repeat folder. Older120s collector saw mains still ON
317..321 V; it does NOT prove the off transition.

r2 permanent WORKING candidate BUILT/TESTED, NOT installed yet:
`artifacts/live_bench_20261014/uart_recovery_working_pair_r2`, pair1415/1414,
HMI8680ac48bc10de88a79a8abb458d46a771dc40b948bf7beb5eb033fca78216d7.
Corrects the remaining over-strict policy: a full-CRC/fresh-sequence verified
single-NE packet is advisory and no longer spends the damaged-packet budget
or erases established clean-link qualification. NE counters remain visible.
Actual discarded packets still use2/1s budget and never feed300ms watchdog.
Hard UART errors, repeated data damage, replay, bad command, local stop,
MCSDK protection and clean-only CLEAR retained. PWM/ADC/filter/protection
sources unchanged, calibration points preserved. Forty successive intact NE
packets pass actual-code tests; r1 header is a negative regression and fails.
2106 assertions + four guard mutations + five HMI suites +42 HTTP tests passed,
both targets built, source/image hashes verified: qualification.json.

PENDING user physical question: when independent meter<20 V, connect BOTH USB
to PC while all power remains OFF; leave motor connected; acknowledge USB-ready.
Root session pending_uart_recovery_candidate=r2; independent-below20 flag reset
False pending this NEW acknowledgment. Do not reuse the pre-powered flag.
After acknowledgment: check actual devices/fresh SAFE/low bus, set flag True,
run install_uart_recovery_working_pair.py --candidate .../r2. New installer accepts
mf predecessor13/12, stages distinct backup, verifies both writes and preserves
calibration; Session validates installed recovery_history chain. Then verify
known cutover fault once (only known programming timeout, archived) and idle.
After transfer back to powerbank/power-on, run one normal5 Hz bounded start.
Online acceleration is still not implemented. No fixture swaps or motor unplug.

### PREVIOUS INSTALLATION CHECKPOINT, 2026-10-14 18:23 UTC: r1 installed

Current WORKING pair Uno2026101413/Nucleo2026101412:
`artifacts/live_bench_20261014/uart_recovery_working_pair_r1`.
Both writes verified; full Nucleo readback matched. Primary HMI SHA
952de2e96d7ab6bef8e5a321f209769a00caf390268f3f71dbb1c6ab1c587639.
RPC recovered without USB cold boot. Current Linux boot
2b7e1087-a6a7-4603-9075-b7634f17553d, Wi-Fi8080/SSH2222 work.
No fixture images in this bundle. Historical fixture writes now disabled.

User priority: one working firmware and online scalar V/f START/STOP/frequency/
acceleration. Do not repeat calibration or motor disconnection. Motor IS connected
to J3. UART10 cm, direct common GND, away from power wiring. J4 is a lab supply.
Original Vbus calibration SHAa89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17
and original capture identities/points unchanged; matching pair accepted by HMI.
PWM/ADC/IIR/motor/protection sources byte-identical to former working1411/1410.
Online acceleration remains hardcoded/unimplemented: do not claim it works.

Last physical confirmation: ALL mains/J4 OFF, independently measured residual
BELOW20 V, explicit authorization to program; motor left connected. BOTH PC USB
visible and used. Do not assume powerbank restored yet. Latest SAFE/PWM0/ARM0/
Vbus2 V; all UART fatal/integrity/sequence/hardware/passive counters0, transport0.
Expected low-bus undervoltage fault5/masks4/4. Recovered-discard1 is visible cutover
history. Known programming LINK_TIMEOUT7/bad1/last_bad13 had no UART flags;
full record saved, acknowledged with exactly one STOP/CLEAR while power OFF.
Expected undervoltage retained. Never loop CLEAR on unexplained powered faults.
Real-board idle after update PASSED:30.828s,41 samples,+589 correct responses,
no new errors, HMI and calibration hashes verified.

Repair: clean LINK frames, including STOP, qualify intact single-NE packets at
START/change/RUN equally. Bad packets discarded/resynchronized with shared
2 events/1s budget; known loss permits a bounded forward sequence gap. Discards
NEVER apply commands or feed300 ms watchdog. Replay/backward/unexplained gaps,
persistent damage, PE/FE/ORE, RX overflow and NE without RX data still fail-stop.
CLEAR must be clean. Reply35/36 now expose `mc_recovered_drops` (bp alias).
2061 actual-code tests through Nucleo ISR/ring/control/reply -> full Uno parser/
decoder -> HMI passed, including344 single-bit corruptions,43 NE positions,
insertion/deletion at all43 positions, power loss, watchdog, four guard mutations.
Five HMI suites and42 HTTP tests/two START-STOP-frequency cycles passed.
These mock HAL/MCSDK tests are NOT powered hardware validation.

PENDING async physical question: both boards from PC USB to powerbank, Saleae
probes remain removed, close stand, ON15 V/mains via soft-start, report ready.
Once ready: fresh safe-off status, one normal5 Hz bounded start with operator
heartbeat,15s MCU backup and host STOP, save full UART/voltage trace; evaluate
power-off transition. User already authorizes motor work. New pair has NOT run
powered yet. No new calibration or fixture swap.

Previous real START on1411/1410 reached MCSDK RUN then NE4/reason12/
transport5 NOISE_REJECTED/masks0/0/seq159; CRC and sequence counters0.
Exact rejected raw packet unavailable; lost bits/physical interference source
not proven. Distinguish this from Oct12 Uno-side noise and programming timeout.
Evidence: current package qualification.json, tests_final/report.json,
hmi_guards/report.json, selftest.json, installation/report.json,
installation/idle_samples.json, programming_timeout_before_clear.json.
Prior powered trace: snapshot_stop_sync_hil_r1/normal_scalar_run_1791999436989648600.
Tools: prepare_uart_recovery_pair.py, uart_recovery_pair_selftest.py,
install_uart_recovery_working_pair.py; historical Session validates current proof.

### HISTORICAL CHECKPOINT: working 1411/1410, stop diagnostic rejection fixed

Installed WORKING pair: Uno2026101411 / Nucleo2026101410, package
`artifacts/live_bench_20261014/pwm_filter_pair_r7`. Both writes verified and
Nucleo readback hash matched. Primary HMI SHA256:
93d21c9381dc0e93613f3a638497ccb6b6525c4051f7c117068382a82ebcf0c4.
HMI predecessor3cf6e59e... retained as server.py.before_pwm_filter_pair_r7.
Owned fixture HMI stopped; primary running/unpaused, paused_primary_pid=None.
Current Linux boot80efa2f2-1f53-4194-9661-5648b3f203b4 after the operator's
confirmed transfer to powerbank. Previous boot2f1d2cc2-bf16-4f14-80f1-e1ecff58ef37
belongs to the earlier Uno USB cold-boot recovery.
No new motor or high-voltage start.

Final SAFE/PWM=0/ARM=0/vdc=0 V; UART/core/passive error counters0,
transport_fault0. bp_fault5, first MCSDK fault masks4/4: actual zero-bus
undervoltage, NOT MC_SW_ERROR or UART noise. After MCU swap link timeout6
and last_bad13 appeared during programming; full pre-CLEAR status retained,
one justified CLEAR acknowledged it with safe-off/0V/fresh telemetry checks.
Do not clear unexplained/new powered faults or repeat flash for RPC recovery.
Final idle span30.078s,+598 good frames, no new errors.

Actual cause of the detached-stop bad page captured in r6: CRC-valid43-byte
page, peer1495 matches, first reason5 NOT_FRESH_OFF; localPWM0, last peer
status0x6d still PWM-active, age5ms. Incoming page was rejected correctly
because its preceding normal reply still described the on snapshot.
This is not proof of the Oct12 powered UART_ERROR_NOISE cause.
r7 caches successfully published safe-off normal reply; sender also requires
this cache before passive pages. All former physical MOE/state/start/rate gates,
receive guards and strict HMI zero-error policy retained. PWM/filter/HFT code
unchanged.14 actual-emitter tests+omission mutation,5752 differential decisions,
388 actual control-parser cases,381 wire cases and real43-byte HMI decode passed.

Final detached fixture1492/1493 test PASSED ALL strict gates.2.962376s active,
carrier16k, no overlap at4MHz, min gap1.25us, LOW tail3.778114s;
phase offsets -119.907/+120.095deg, acceleration1.666040Hz/s. No bad pages,
no first-reject flag, both snapshots available and +47 good passive pages
after stop. Diagnostics were not disabled to achieve a pass.
Final evidence `artifacts/live_bench_20261014/snapshot_stop_sync_hil_r1/`
(FINAL_RESULT.json,RESULT_RU.md,run_1791993029505542400,programming_timeout_before_clear,
production readback/upload/idle logs). Earlier failed traces are retained.

USER STEERING, 2026-10-14: operator supplied actual DC-bus meter0.32 V, then
objected to repeatedly replacing already captured calibration points. Do NOT
execute the superseded plan to capture a new zero: capture would discard the
existing high point. No calibration API POST, reset, migration or point rewrite
was performed. Treat0.32 V as an independent discharged-bus check only.
Read-only review collected20 fresh SAFE/PWM0/ARM0 samples: controller mean0 V,
std0 V, all ERROR_FIELDS0; zero-region agreement passed. Primary HMI and original
calibration hashes verified unchanged before/after. Current file and remote/local
archives remain byte-identical SHA
a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17.
Saved points are meter0 / MC0 V and meter322.7 / MC325 V, original identity
Uno2026092901/Nucleo2026100601; original integrity/span check passes.
Evidence: snapshot_stop_sync_hil_r1/vbus_preservation_review_1791995033559009700/report.json
and samples.json; script tools/review_vbus_calibration_preservation.py.

HMI still reports identity incompatibility for1411/1410. A real measurement
change occurred in r3/r4: IIR now retains its fractional remainder, removing
the former constant-input lag (host-characterized maximum255 internal units,
1.618652 V with conversion factor416). This is distinct from later diagnostic
changes, which leave the filter unchanged. Do not demand a new two-point
calibration for every diagnostic firmware revision; preserve capture provenance
and audit measurement compatibility separately. No powered verification of the
changed filter has occurred, and no HV gate was relaxed to appease the operator.
Any future working-voltage verification is a separate physical stage; do not
automatically POST calibration captures or ask repeated zero/setup questions.
No pending calibration measurement question; no immediate motor START.
HV remains explicitly blocked in HMI pending qualification/measurement review.

LATEST PHYSICAL STAGE, 2026-10-14: operator confirmed both Uno Q and Nucleo
now powered from powerbank, both PC USB connections removed, Saleae USB removed.
Read-only direct Wi-Fi idle passed30 seconds,40 samples,+596 good frames;
expected1411/1410 pair, all ERROR_FIELDS0, transport_fault0, SAFE/PWM0/ARM0,
bus0 V, only expected zero-bus undervoltage5/masks4/4. Original calibration
and HMI hashes unchanged; no ARM/START/CLEAR, calibration or firmware writes.
Evidence: snapshot_stop_sync_hil_r1/autonomous_idle_1791995712628013400/report.json,
status.jsonl, summary.json, logs.txt. Current boot ID is recorded above.
J4 DRIVER-SUPPLY STAGE COMPLETED: operator confirmed ONLY15 V on J4.
The discharged-bus precheck correctly refused controller Vbus8 V (>2 V), so
no zero-point capture or PWM was attempted. Operator then measured actual
DC-link9.5 V with J1/motor detached. Do not call this bus discharged or use
the earlier0.32 V reference for the powered-J4 condition.
30-second direct Wi-Fi observation passed42 samples,+603 good frames,
all ERROR_FIELDS0, transport_fault0, SAFE/PWM0/ARM0, only undervoltage5/masks4/4.
Controller Vbus ranged9..10 V, mean9.666667,std0.471405 V; last fresh read10 V.
This does not qualify the Vbus gain at working voltage. Temperature telemetry
valid47 C, fault0 (reported sensor reading, not an independent thermometer).
Original calibration and HMI hashes unchanged; no ARM/START/CLEAR or writes.
New first-since-boot BKIN record appeared after J4 activation: tick309697,
BIF1, PA6 sampled LOW at IRQ, MOE0; cached context age13 ms,Vbus0,UV4/4.
First-start-window record remains uncaptured. Do not claim a current trip,
measure pulse duration from this snapshot, discard the first record, or CLEAR
the evidence without a separately justified operation. The 15-V-to-bus path
has not been uniquely identified; do not label it proven bootstrap backfeed.
Evidence: snapshot_stop_sync_hil_r1/j4_driver_idle_1791996153341614900/report.json,
status.jsonl, summary.json, logs.txt; first live status in j4_15v_first_status.json.
J4 OFF CONFIRMED, 2026-10-14: user replied ready to OFF15 V instruction.
Eight read-only samples showed controller5 V with all communication errors0,
SAFE/PWM0/ARM0 and fresh link. Operator then independently measured2.5 V.
Do not claim a discharged bus based on the earlier0.32 V reference or on the
controller5 V. J4 off report: j4_off_1791997173694116000/report.json and samples.json.
This is a discharge check, NOT a new zero calibration capture.

WORKING-VOLTAGE PREPARATION CONFIRMED: user replied ready to all three steps:
independent meter<2 V before re-wiring, ALL Saleae probes including GND removed,
J1 connected to original SWITCHED-OFF source, motor remains disconnected.
Both boards stay on powerbank, PC USB removed; J4 and mains OFF pending the
next explicit operator instruction. Do NOT repeat probe-removal confirmation.
Fresh precheck passed exact1411/1410, SAFE/PWM0/ARM0/START0/trial0, errors0,
no active controller/external outputs, reported Vbus1 V,fresh link.
Original calibration/HMI hashes unchanged, no ARM/START/CLEAR or any writes.
Evidence working_bus_prepared_1791997766415076200/report.json; only the bound
meter<2 V was confirmed, no exact new zero reference is claimed or recorded.
GET-only charge telemetry collection started for300 seconds (exec session5077),
folder working_bus_charge_1791997766415589900 (status.jsonl available while running;
summary/logs appear on completion). Capture includes the unpowered baseline;
do not judge the charging transient with the working-point stability guard.
NEXT operator instruction: secure meter probes, close stand, enable J4 15 V,
then mains through existing soft-start; report power on and NEW meter reading.
This is measurement-only, motor remains disconnected and HMI ARM is blocked.
Neither J4 nor mains has been confirmed ON for this stage yet.

Working-bus read-only verification is now prepared:
tools/verify_vbus_preserved_points.py, exact1411/1410,20 GET-only samples,
new independent meter250..360 V, original HMI/calibration hashes before/after,
same existing3%/5 V comparison and0.5%/1 V stability tolerances. No calibration
POST/reset, ARM/START/CLEAR, MCU/HMI changes or voltage-gate relaxation.
Retained UV latch5 with CURRENT fault mask0 and occurred mask4 is allowed only
for reading; any current fault, unknown peer, stale sensor or error rejects.
20 offline checks passed, including fake-opener enforcement of GET-only requests,
error-counter mutation and unstable-sample rejection; original archive unchanged.
Preparation evidence: passive_working_bus_preparation_r1/plan.json,offline_checks.json.
This tool does NOT make the old calibration valid in HMI or authorize motor start.
Do not use the OLD322.7 V as a new meter reading. No working HV capture yet.
Autonomous idle does not qualify the changed Vbus filter at working voltage,
the old powered UART-noise cause or the next motor start.

LATEST PHYSICAL STATE overrides the earlier permanent dry-test probe pattern:
Saleae ALL probes/GND now removed per the specific power-stage preparation;
Saleae USB and both PC USB disconnected, boards on powerbank. J1 now connected
to OFF original source; motor U/V/W still detached; J4 OFF. Do not ask to repeat
these completed preparations or ask laboratory PSU model. Earlier dry stages
left Saleae probes attached with only its USB removed; that is historical now.

### Historical r6/r7 work detail, 2026-10-14: completed as above

User asked "что дальше"; continued software diagnosis without asking to rewire
permanently connected Saleae. r6 instruments first rejected page; valid/first
record/raw packet/context are additive and cannot ACK control or refresh watchdog.
5752 differential cases preserve every r4 assembler decision. Actual byte parser
388 control cases +381 wire cases and end-to-end HMI decode of actual43-byte frame
passed. First r5 fixture decoder missed1408 and was rejected BEFORE hardware;
r6 corrected that. HMI initially used an incorrect80-character frame length;
fixed to86 and deployed HMI-only before the first instrumented PWM run, retaining
old files/proofs and new qualification_frame_fix/reject_selftest_r2. No extra
MCU programming was done for that HMI correction.

Measured r6 fixture1494/1495 rejected exactly one CRC-valid43-byte diagnostic
page at stop. Peer1495 matched. Reason5 NOT_FRESH_OFF; captured prior status0x6d,
local PWM0, status age5ms. Packet+CRC32c independently validated. This explains
the new detached test's bad-page increment, NOT the Oct12 physical UART noise.
Evidence: snapshot_reject_hil_r2/run_1791992054652665000/reject_cause_proof.json.
r6 working1409/1408 was programmed/verified, then RPC did not recover after
owned HMI restart. User performed requested Uno-only USB cold boot. Linux boot
now2f1d2cc2-bf16-4f14-80f1-e1ecff58ef37, RPC recovered with no reflash for recovery.

NEW r7 fix caches whether the last successfully transmitted normal control reply
had both enabled/PWM bits off. Nucleo emits passive pages only with that cache
true, in addition to all existing MOE/state/command/start-window/rate gates.
Receive acceptance policy and strict zero-error HMI guards unchanged. Active
PWM/controller/filter/HFT code unchanged. r7 working1411/1410, fixture1492/1493.
14 actual-emitter/publication tests passed; omission mutation caught. Matched
peer/wire/HMI suites and full target builds passed.

r7 detached hardware run PASSED ALL original strict gates:2.962376s PWM,
carrier16k, no overlap, min deadtime1.25us at4MHz, LOW tail3.778114s,
phase offsets -119.907/+120.095deg, acceleration1.666040Hz/s. Bad pages0,
hardware/CRC/sequence/drop counters0, first-reject flag0; passive pages resume
after stop (+47 good), both records available. Not silently disabling diagnostics.
No B1 latency/motor speed/HV release proved. Evidence:
snapshot_stop_sync_hil_r1/run_1791993029505542400/ (SAL,CSV,status,report,waveform,
modulation_ramp.json,stop_sync_proof.json).

ACTIVE operation: restoring final WORKING1411/1410 via snapshot_stop_sync_hil_r1.
To avoid RPC requests during MCU swaps, driver stops only owned fixture HMI,
SIGSTOPs verified arduino-owned primary HMI, flashes/byte-verifies both new
working images, waits7s for Uno Bridge startup, then SIGCONTs same primary in
finally. No root service, sudo or router changes. If interrupted while paused,
use driver resume_primary; breadcrumb paused_primary_pid is in session.json.
After restore finish observe (~30s idle), retain final hashes and update this
current-state section. HV stays explicitly blocked; old calibration bytes intact
but invalid for new filter. Next physical measurement is new Vbus calibration,
not immediate motor START. Do not repeat PSU/model/probe questions.

### Historical r4 state, 2026-10-14: superseded by latest active work above

Installed WORKING IDs: Uno 2026101407 / Nucleo 2026101406, package
`artifacts/live_bench_20261014/pwm_filter_pair_r4/`. Both MCU writes verified;
Nucleo full-image readback matched. Primary HMI SHA256:
0e896bfc4df50e53c1783c2eb017a0d4e77d60f67207200dd51cef2917b53902.
Backup predecessor HMI: `server.py.before_pwm_filter_pair_r4` (701f01b7...).
Original calibration SHA a89603c26... unchanged; invalid for new filter identity.
HV explicitly blocked on 1406/1497 pending new qualification. No powered start.
Both owned fixture HMI processes stopped. Current SAFE/PWM=0/ARM=0/bus=0 V;
estop=0, Nucleo bp_fault=1 and first ESTOP with masks 0/0 from programming
cutover remains latched. Do not claim all fault fields are zero.

Permanent operator fact: Saleae six PWM wires AND logic GND are always connected;
ONLY Saleae USB is unplugged/replugged. The probe-ready request was answered;
do not repeat it. Current J1 and motor U/V/W physically detached, J4 off,
USB to PC attached, as confirmed for this detached test. Earlier generic
"all Saleae wires removed" confirmations must not override the latest correction.

r4 fixture 1496/1497 was measured and then replaced by working 1407/1406:
2.974376 s active, carrier16k, zero overlap, min gap1.25us at4MHz, final LOW
3.959047s. Ramp-aware sine fit passes:1.666391Hz/s, end4.903Hz,
phase offsets -120.187/+119.893deg, R2>0.9985. Four adversarial ramp-analysis
tests passed. No B1/PC13 edge measured and no new motor speed qualification.
Primary UART hardware/CRC/sequence/drop errors all0. Passive snapshot bad_pages
grew0->1 on auto stop again; actual packet reject reason unobserved. Offline
replay proves CRC-valid pages are counted bad if fresh-off gate is false,
but that is only a possible explanation. Strict combined capture report FAILED;
waveform qualification PASSED separately. No HV release or powered-cause proof.

New r4 fix skips HFT calculations when physical MOE off, eliminating r3's false
boot MC_SW_ERROR. Guard is in actual ARM assembly before angle/controller calls;
active nonfinite/range errors still switch PWM off and fault. Fixture first
zero-bus fault mask4 without SW128 observed before single programming CLEAR.
92160 valid PWM cases,40 invalid/off cases,8192 filter cases with -Ofast passed;
full builds, byte-identical wire headers, peer/HMI/interlock/stop suites passed.
Do not restore r3 1405/1404, which triggered false software fault on boot.

Final passive check:19 observations,29.437s sample span,+586 good frames;
no new UART or passive-page errors. Session pwm_filter_hil_r2 is RESTORED,
idle_30s_pass true. No repeating flash to fix RPC: both restore operations
recovered RPC without reboot. Evidence and human result:
`artifacts/live_bench_20261014/pwm_filter_hil_r2/FINAL_RESULT.json`, `RESULT_RU.md`,
`run_1791989745601632900/` (SAL,CSV,status,strict report,waveform,ramp fit),
`snapshot_policy_replay/`, final readback/upload/idle logs.
User's authorized flash-and-retest task completed; next program diagnostic is
reject-reason capture for the passive page, not another PSU/model question.

### Historical operator clarification and intermediate r4 work, 2026-10-14

SALEAE PROBES ARE PERMANENTLY CONNECTED: user disconnects/reconnects ONLY its
USB, not the six PWM wires or logic GND. User explicitly clarified this after
the repeated probe-ready question. Treat the question as answered, do not ask
to reconnect the same probes. Earlier reports of all probe wires removed must
not be assumed current. This detached test has confirmed J1/U/V/W disconnected
and J4 off; no power or motor activation has occurred in this new stage.

r3 fixture 1498/1499 PWM capture completed: 2.9803775 s, carrier 16 kHz,
no overlap, minimum deadtime 1.25 us at 4 MHz, final LOW tail 3.406 s.
Ramp-aware analysis passes: 1.66655 Hz/s over nominal 3 s, final about 4.913 Hz,
phase offsets -119.972/+120.029 deg, sinusoidal fits R2>0.9985. A whole-window
constant-frequency fit failed because production's ramp is 3 s; retain that
failed analysis and use the physically correct ramp model. Four adversarial
synthetic waveform tests pass. Primary UART hardware/CRC/sequence/drop counters
all 0. Passive snapshot bad_pages grew 0->1 at automatic stop; exact packet
reason is not captured. Strict combined capture report remains FAILED; waveform
and primary transport findings are separately qualified, no HV release.

r3 working pair 1405/1404 was restored/byte-verified and 30 s idle passed,
but the new finite guard revealed a FALSE MC_SW_ERROR at boot with outputs off.
The HFT unconditionally called the controller with an uninitialized/zero bus
normalizer. New package r4 adds an early return when physical MOE is off;
active invalid inputs still switch outputs off and preserve fault processing.
Both r4 pairs built/qualified (40 host invalid/off cases), exact active PWM code
unchanged from r3. r4 IDs: working 1407/1406, detached fixture 1496/1497.
Session `artifacts/live_bench_20261014/pwm_filter_hil_r2` installs this revision.
Latest active operation is installing fixture 1496/1497; finish ready/capture,
retain diagnostics, restore NEW 1407/1406, and 30 s observe. No extra physical
question or re-wiring needed. Previous session r1 is historical; don't restore
1405/1404 merely from the older section below.

### Historical r3 preparation, 2026-10-14: superseded by the latest section above

User explicitly authorized flashing and retesting ("ну го еще раз тестить прошивай").
This supersedes the earlier no-flash request. User then confirmed J1 and motor
U/V/W physically detached; mains and J4/15 V off, bus discharged, PC USB attached.
Do not re-ask those facts or the laboratory PSU model.

New versioned package: `artifacts/live_bench_20261014/pwm_filter_pair_r3/`.
Working pair 1405/1404 is built and qualified but NOT yet installed. Detached
fixture 1498/1499 IS installed, Uno loader/sketch verify passed; Nucleo full
image readback matched its actual image hash (manifest records exact size).
RPC works without cold boot. Current fixture status:
SAFE, PWM=0, ARM=0, bus=0 V, UART errors=0, local stop=0; SET FREQ 5 staged only.
No ARM or START sent in this session yet. One STOP/CLEAR acknowledged the
stopped zero-bus programming cutover, with pre-clear diagnostic retained.

Primary HMI is now 701f01b7a57da13c1d25ee4d2bd008b442ef76bf497e5ea2727c0632c2fc72a6.
Previous 992b3c20... saved as server.py.before_pwm_filter_20261014. It recognizes
new snapshots and explicitly blocks HV on 1404/1499 pending new qualification.
Old calibration bytes and UI preserved. The calibration is INVALID for the
new filter identity; never extend its old whitelist to bypass this.
LV-only fixture HMI uses port 8081 and remote directory
`/home/arduino/.local/share/mic-ai/pwm-filter-hil-20261014`.

Full target compiler uses -Ofast. The r2 package's ordinary isfinite guards
were therefore superseded BEFORE FLASH by integer exponent classification in r3.
Host -Ofast vectors passed (92160 valid, 39 invalid, 8192 filter cases), and
isfinite mutant was detected. Actual production AND fixture ARM disassembly
contains all three PWM and seven VF exponent masks/early error branches.
Both full Nucleo builds and both Uno llext checks passed; detached interlock,
button stop, peer decoding, HMI guard suites and old-calibration rejection pass.
Source/binary baseline images remain unchanged. r1/r2 are superseded; don't flash.

`tools/pwm_filter_hardware_session.py` and session
`artifacts/live_bench_20261014/pwm_filter_hil_r1/session.json` control the active
stage. A journal encoding exception happened AFTER the Nucleo write command;
it was corrected and installation verified by readback without repeating writes.
The error retained in session.json is historical, resolved by resume_fixture.

Required pending input: channels 0..5 UH/UL/VH/VL/WH/WL + logic GND ready on
Saleae. One async request sent; do not launch before its reply. Once ready,
run `capture` (8 s Saleae, 3 s MCU max, authenticated heartbeat, auto STOP),
analyze six-channel carrier/deadtime/no overlap and 5 Hz three-phase envelope,
then `restore` installs NEW working 1405/1404, and `observe` checks 30 s idle.
Do not rerun firmware writes merely because RPC needs recovery. Preserve actual
capture failures; no automatic powered retry or motor start is authorized here.

### Latest offline PWM/filter work, 2026-10-14: user redirected to program audit

Operator clarified UART TX/RX about 10 cm, direct common GND present, routed
away from motor U/V/W and mains. During the powered trial both Uno Q and Nucleo
used USB ports of the powerbank. J4 uses a laboratory supply. Do not repeat
questions about these facts. User explicitly objected to more supply/wiring
questions and redirected work to pulse formation and filters. Keep the earlier
request not to flash for now; no further physical action was requested.

Exact retained Nucleo 1204 functions were executed on the host, with the real
sinusoid lookup table and mocked registers. Three defects reproduced:
zero modulation normalizer reaches NaN duty and three CCR writes with a success
return; fixed-point Vbus filter drops fractional residual and can stop 255 u16
units below constant input; unavailable ADC sentinel 0xFFFF returns fault=0
even while the sensor stores an earlier UV/OV fault. The latter concerns the
returned/current fault flags, not deletion of first-fault evidence.

Prepared isolated patch/source fragments under
`artifacts/live_bench_20261014/pwm_filter_audit_r6/candidate_unflashed/`.
PWM/controller reject invalid input before CCR conversion; HFT handles MC_SW_ERROR
through output-off/fault processing; Vbus filter retains a fractional remainder,
resets it on init, and preserves previous fault on unavailable ADC.
92,160 valid PWM comparisons have identical duties/CCR; 39 invalid input/cutoff
cases, 8192 constant-input filter cases, three unavailable-ADC fault cases and
threshold/hysteresis checks passed. New filter constant-input lag=0; rise/fall
95% each=766 samples. Six mutations detected. Four changed C translation units
pass Cortex-M4 hard-float syntax checks. Retained ELF/BIN/HEX match manifest;
four ELF functions disassembled (timer initialization inlined into main).

All source/binary baselines untouched; no board access, control commands,
firmware writes, new preparation or calibration changes. Installed pair remains
1205/1204 and HMI 992b3c20... from the completed passive decoder fix below.
No physical cause of the 2026-10-12 UART incident established by this audit.
The zero normalizer was not observed in that powered trial. BKIN/UART/deadtime
settings and cumulative-zero HMI guard unchanged. Host HFT propagation tests
stub angle-update dispatch and do not qualify target pulse or IRQ timing.
The patch is NOT a versioned flash release: filter handle layout/DC bias change;
full rebuild, calibration-contract review and target qualification remain before
deployment. Human report: `pwm_filter_audit_r6/RESULT_RU.md`.
Earlier r1-r3 failed host harness runs retained; r2/r3 reverse-angle failures
were an unsigned test-generator arithmetic bug, not a firmware finding.

### Latest HMI-only fix completed, 2026-10-14: passive 1204 snapshots decoded

User said "давай" after the proposed UART analysis/passive HMI correction.
J1/mains and J4/15 V remain reported off, discharged bus, PC USB connected.
Installed HMI SHA256 is now
`992b3c20c8573681f195de3a208a461359c22673b83e3f2d578f87e16ce212d1`.
Only the passive decoder predicate changes: known Nucleo 1102 OR 1204,
instead of 1102 only. Other HMI AST, actuator functions and guards are identical.
Canonical asset `research/ipm_break/hmi_snapshot.py` is corrected as well.
Wire headers match after build-ID/whitespace normalization; the snapshot
layout header is byte-identical. Retained MCU artifacts were not modified.

93 offline decoder/route/installer checks passed; seven broken decoder
mutations were detected; five existing HMI guard suites passed. Replaying all
six retained powered-trial status samples gives exactly the same guard results,
including rejection on `uno_rx_hw_errors`. MCU flashing, CLEAR, ACK, ARM,
START, calibration changes and new powered preparation: NONE.

Install: exact predecessor/current/calibration hashes checked, backup retained
as `/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/server.py.before_passive_decoder_20261014`.
Only the verified arduino-owned HMI process was terminated for systemd restart
(PID 549 -> 1245). Linux boot ID stayed `33ca73bb-edb9-4dab-a360-5a3f49be1d4c`.
UI and original calibration hashes unchanged, first-fault fields/error counters
preserved, same firmware 1205/1204, SAFE/PWM=0/ARM=0/reported bus=0 V.
20 subsequent observations span 30.329 s, +604 good frames, no new errors.
Both passive snapshot records available. First-since-boot: BIF with MOE off,
start_window=0, context_valid=0 (no cached-context interpretation possible).
First-start-window: no recorded break. This is the current boot's record,
not a recapture or explanation of the 2026-10-12 powered incident.

Evidence: `artifacts/live_bench_20261014/passive_decoder/`
(`candidate_r1`, `selftest_r2`, `guards_r1`, `install_r1`, `decoder.diff`,
`uart_incident_analysis.json`). Installed SDK header verifies bit 0x20 is
UART_ERROR_NOISE. The Nucleo accepted-NE policy covers its received commands;
Uno hardware noise is measured on the other receiver and is not per-byte/frame
correlated by its existing queue. Original trial also had encoder I2C errors
0 -> 21 with -5; neither observation identifies the physical interference source.
Keep cumulative-zero HMI guard unchanged. No powered repetition is qualified.

The subsequently supplied wiring/power facts and user's software-directed scope
are recorded in the newer PWM/filter section above. Keep PC connected with J1/J4 off.

### Latest passive check, 2026-10-14: PC USB connected, no firmware write

The user resumed hardware work and reported J1/mains and J4/15 V off,
the DC bus discharged, and all boards already connected to the PC. No new
numeric independent meter reading was supplied. Do not infer a powered-stage
configuration or authorization from this passive check.

Direct Wi-Fi HTTP GET `/api/status` only, 20 observations spanning 30.032 s:
Uno 2026101205 / Nucleo 2026101204, SAFE, PWM=0, HV ARM=0, HV START=0,
reported bus 0 V, +598 good frames, no new UART/CRC/sequence/drop/short-write
or break-page errors. All passive observation checks passed. Current mask
is 4 (zero-bus undervoltage), occurred mask is 1028; the latter is retained
without interpreting its extra bit as an identified physical cause.

Evidence: `artifacts/live_bench_20261014/usb_passive_20261014T104256Z/`
(`status.jsonl`, `summary.json`). No CLEAR, ACK, ARM, START, reboot, HMI change,
calibration change or flash write was sent. Current cumulative noise counters
are zero; this does not erase or invalidate the retained 2026-10-12 powered
trial incident. Research ADC simulations remain host-only and are not installed
on either board. Keep J1 and J4 off with the PC connected. At this stage the
decoder correction was pending; the newer completed HMI section above supersedes
that pending item. A healthy idle link does not qualify communication during powered PWM.

### Latest powered trial in this chat: rotation confirmed, trial failed on UART noise

The user explicitly asked to start the motor here, repeatedly said go, confirmed
autonomous 5 V from a powerbank, motor/J3 restored, both PC USB connections and
ALL Saleae wires/GND removed, closed/secured setup, J4 on, then mains through
soft-start. The original chat was idle at the coordination snapshot. No MCU
firmware write was repeated; production remains 1205/1204.

The installed HMI is NOW SHA256
`88f0764f881b5bbc7cb8e1e0b40954fe7d2e63450edd568cd8b92f83550d2d6b`.
Candidate `short_trial_candidate_r2` adds an honest alternative schema for one
5-Hz/3-s trial based on the measured fixture plus exact ten-code-section
equivalence. It keeps production-active-PWM, exact-button-latency, forced
ENABLE, current-telemetry and general-HV-release claims FALSE. Exact retained
evidence hashes are embedded. 135 adversarial/AST/preparation checks and five
existing HMI guard suites passed. Actuator and live-monitor functions remain
unchanged. MCU hashes and original calibration bytes remain unchanged.
`short_trial_prepare_r1` accepted non-actuating preparation at 0 V; no waiting
deadline, active ARM <=10 s, live 250..360 V/fault/temperature/transport checks,
30-s/100-new-frame idle qualification, one-shot and 3-s limits retained.

Aux observation `short_trial_aux_r1` passed (+190 frames, about 9 V, PWM/ARM 0).
Powered idle `short_trial_powered_idle_r1` passed after one specifically
identified undervoltage ACK: 326 V, temp 48 C, fault 0, 35 observations.
One START was issued in `motor_short_r1`. VF_RUN/PWM=1 and ramp to 5 Hz were
observed. User confirmed physical rotation: "да успел". The overall trial is
FAILED, not a successful fault-free 3-s run. Do not automatically retry.

`uno_rx_hw_errors` rose 0->1, flags 32/0x20 = Zephyr UART_ERROR_NOISE.
NE observed/accepted counters reached 3; primary bad/CRC/sequence and transport
fault stayed zero; break diagnostic bad-page count became 1. HMI log explicitly
says `HV_RUNTIME_REJECT RX snapshot trial transport unhealthy: uno_rx_hw_errors`
with successful STOP/ESTOP. First Nucleo fault then ESTOP, masks 0/0, UART flags 0,
state 8, seq 110. Do NOT call this a uniquely established MC_DP/IPM hardware trip.
The physical cause of UART noise is not identified. Do not relax the guard or
erase the noise/fault counters just to report a successful test.

User confirmed power off after instructions to turn mains and J4 off. PWM=0,
ARM=0, SAFE are confirmed; bus fell through 57 V, 24->19 V during a saved idle
recording, then to 2 V in the last saved telemetry. Keep all external wires off
until independent meter discharge confirmation if wiring work is needed.
One-shot gate is consumed. No CLEAR or new preparation/START after the incident.
Read `motor_short_r1/RESULT_RU.md`, `report.json`, `wifi_logs.txt`, `power_off_r1`,
`final_off_status.json` before future work.

Additional HMI bug found: `break_wire_status()` still accepts ONLY Nucleo 1102,
so 1204 snapshots were mislabeled stale_or_wrong_peer. Installed file/service
has NOT been modified for that bug. A passive one-off in-memory whitelist
correction read the same RPC without actuator commands, saved as
`motor_short_r1/passive_break_decode.json`. It decoded the old first BIF at
bus 0 V, MOE off, context UnderVolt 4/4, start_window 0; first_start_window has
no record. Respect snapshot capture-scope limitations. Next work is analysis
of CRC-validated NE policy versus the HMI cumulative-zero guard, and tested
passive decoder correction, with no automatic powered repetition. Older
pending-recovery/no-powered-trial statements below are historical.

### Latest recovery completed in the original chat

The user returned to the original chat and requested that it continue. It
read the new chat's completed B1/PWM test and verified restore; no test or
firmware write was repeated. Full access/recovery details are now in
docs/UNOQ_ACCESS_RUNBOOK_20261012.md. Sudo password is unknown (including to
the user); SSH uses a key, which does not grant sudo. Do not keep asking for
that password or guess factory credentials.

User cold-booted Uno only. Linux boot ID changed to
cf8c52bb-a93d-4013-a646-65a846c1c033; RPC is restored. 30 seconds of direct
Wi-Fi: +591 good frames, no UART/HTTP errors, 1205/1204, SAFE/PWM=0/ARM=0,
reported bus 0 V. Original calibration and HMI hash 21bda96f... still match.
Evidence: artifacts/live_bench_20261012/local_button/post_cold_boot_r1.
This supersedes the pending cold-boot/recovery requests in the older sections
below. No powered release was created; do not start hardware automatically.
Hardware work is currently continued by the original chat; another chat must
not concurrently actuate or flash the same stand.

### Latest active stage: detached physical LOCAL STOP test preparation

LATEST UPDATE (supersedes pending preparation paragraphs below): user
reconnected Uno USB, ADB recovered; `pwm_session_r2` successfully installed
fixture 1298/1299 and verified bytes. Initial automatic capture ran to the
three-second limit; no B1 occurred, so its pass=false result is retained.
Fixture Nucleo reset produced a latched FE/NE UART error; six saved idle
observations showed stable bad_count=1 and +82 good frames, bus 0 V/PWM off.
Normal CLEAR was accepted on the detached fixture after saving the before/after
snapshots. A subsequent automatic acquisition conflicted with the operator's
already running Saleae recording and never reached START.

User then explicitly requested START while watching their own Saleae recording.
That manual-capture run succeeded: operator confirmed B1 pressed/released,
LOCAL STOP seen at 2.0 s from START request, PWM off, zero bus and no new UART
errors. User supplied `C:/Users/USER/Desktop/Session 8.sal`; archived under
`pwm_session_r2/manual_run_1791818470131763700/operator_capture.sal`. The file
confirms six 16-kHz PWM signals, no overlap at metadata-confirmed 4-MHz sampling,
active span 1.468041 s, then six outputs LOW for 9.645371 s. No PC13 front was
captured; no exact button-to-off latency or forced-ENABLE test is claimed.
`.../report.json` passes. Capture SHA256:
`abade1d935e0f508bbd4d8c87d6f53f833e4c9728f8e0d3eaebe89e08be489e4`.
See `artifacts/live_bench_20261012/local_button/PWM_LOCAL_STOP_REPORT.md`.

Both production images were restored/verified (Nucleo exact readback; Uno
loader/sketch verification) and fixture HMI 8081 stopped, but primary HMI RPC
is unavailable (503/timeouts). DO NOT blindly rerun restore, as that reflashes
already verified images. HMI SHA and original calibration still match. Owned
HMI process restart did not recover RPC. `verify_restart_unoq_sketch.cfg`
verified the unchanged Uno images and restarted it WITHOUT flash writes,
then Nucleo was reset within 0.078 s; RPC still did not recover. Router is root
UID 0 and cannot be restarted by arduino without sudo authentication.

CURRENT REQUIRED USER ACTION: cold boot Uno Linux by unplugging/replugging
ONLY Uno's USB for five seconds, retaining Nucleo/Saleae and power isolation.
The request is pending; this is a second, distinct USB recovery after restore,
not the earlier pre-install recovery. After confirmation, verify live 1205/1204,
SAFE/PWM=0/ARM=0/bus 0 V, preserved calibration and fresh transport. No further
active run is needed for the successful button capture. Complete recovery
before concluding the task. No powered-motor release or production active PWM
claim was made. The lower paragraphs describe earlier preparation/history.

The user asked whether to run the motor, then authorized preparing the isolated
PWM/B1 test and is awaiting instructions. They confirmed: measured bus 0 V,
STEVAL J1 and motor U/V/W physically disconnected, J4 remains off, Saleae is
connected. They want to keep only the six existing PWM probes: do not require
a PC13 probe. Therefore exact button-edge-to-off latency cannot be measured;
record cessation of six PWM signals plus operator press and STOP telemetry.

Prepared `pwm_fixture_r1` from frozen production 1205/1204, with distinct test
IDs Uno 2026101298 / Nucleo 2026101299. Real ADC telemetry, filtered bus <=2 V,
5-Hz command ceiling, MCU 3-second hard cap; virtual modulation normalization
only in this detached fixture. It is never for a powered motor. Both builds
pass; Uno loader check has no TLS issues. `pwm_fixture_selftest_r5/report.json`
passes (1038 STOP checks, 1000 raw and 451 filtered-voltage vectors, 3-second
boundary/wrap/stale-ADC tests, diagnostic peer decoder, nine negative HMI gates).
Earlier selftest attempts r1-r4 failed on test setup/extraction and are retained.
`pwm_fixture_code_r1/report.json` compares ten unlinked compiled PWM/IRQ/STOP
sections with production: all equal; TIM1 initializer and local STOP sources
also match. These are source/fixture-transfer checks, not production active
PWM or HV qualification. `pwm_idle_before_r1/report.json` physically confirms
all six connected PWM signals LOW at 4 MHz before any temporary installation.

New tools: `prepare_local_stop_pwm_fixture.py`, `local_stop_fixture_selftest.py`,
`local_stop_zero_bus_session.py`. The session tool uses pinned production image
hashes for restore, exact Nucleo readback, verified Uno upload configuration,
retains original HMI/calibration, and starts a separate LV-only fixture HMI on
port 8081; fixture HV ARM is explicitly denied and IDs/2-V bus/5-Hz checked.
Its run action sounds a short PC beep after START confirmation, then the
operator should promptly press/release B1. Captures only channels 0-5 for five
seconds; MCU/HMI run caps remain three seconds. No button timing may be claimed.
The run action has not been executed and the physical button test is pending.

First installation attempt `pwm_session_r1` failed before Uno programming at
ADB's makedir stage: `adb.exe: device offline`. Its attempted restore also
failed at that same ADB stage. Live Wi-Fi still reports production 1205/1204,
SAFE, PWM=0, ARM=0, bus 0 V and LOCAL STOP=1. Nucleo flash readback before the
attempt matches the production hash. Neither START nor ARM nor CLEAR has been
sent in this stage. Original HMI/calibration hashes still match. A staged
fixture HMI file exists at `/home/arduino/.local/share/mic-ai/local-stop-hil-20261012/server.py`,
but no fixture process was started. The installer now checks ADB before any
write-attempt flag and permits reuse of that exact pinned staged directory.

`adb reconnect offline` did not recover the transport. The user has been asked
to unplug/replug ONLY Uno's USB cable (leave Nucleo/Saleae and power isolation
unchanged) and report completion. Await that required physical action before
retrying install with a NEW session directory (e.g. pwm_session_r2), not r1.
Do not flash the old fixtures or fabricate active-PWM evidence. After the
detached test, explicitly restore and verify production 1205/1204 and original
calibration, save reports and clarify remaining physical qualification limits.

The user explicitly requested a new, separate chat because the original thread
is too long. Continue in C:\mic_practice; do not start from scratch or replace
existing files with stock examples. The original thread remains the history.
Read CURRENT_BENCH_STATUS_RU.md and the live report below, then inspect git
status before editing. Numerous unrelated and earlier agent/user changes are
present: do not revert, clean, reset or automatically commit/push them.

Latest user action: confirmed the Nucleo B1 USER button is released after pressing
it following the firmware update. The next 10-second Wi-Fi observation retains
LOCAL STOP=1, SAFE, PWM=0, ARM=0, reported bus 0 V; no new errors.
The immediately preceding operator confirmation was mains physically
disconnected, J4 15 V off, DC bus <=2 V, USB connected for programming.
Current Wi-Fi reports 0 V, SAFE, PWM 0, ARM 0. No START/ARM/CLEAR has been
sent in this installation/button stage. No need to ask those same physical
questions again for passive reads; reassess explicitly before a changed stage.

## Current Live Button Result And Corrected HMI

Update after continuing in the new chat: the HMI-only LOCAL STOP correction is
installed. Current API reports `hmi_local_stop_latched=1` with raw status 141;
`mc_fault_detail` begins `current=LOCAL_STOP_PC13; first=MCSDK_FAULT`.
The first diagnostic fields remain reason 8, masks 0x0004/0x0004, sequence 227.
Neither MCU nor the calibration changed. No ARM/START/CLEAR was sent.

Root cause: `AppState.arm_snapshot(status)` derived the bit from its ARM-only
output dictionary instead of the raw `status` argument. The formatter now
adds current STOP context without replacing first-fault evidence. The flight
recorder/diagnostic dedup keys include current fault and latch, so a STOP
transition is logged even when the stored first fault is unchanged. The UI
prioritizes the controller LOCAL STOP bit and retains first details in its
tooltip. The shared fix is applied to `web_hmi/server.py` and by
`prepare_trial_wait_fix.py`; archived baselines are not rewritten.

Current HMI: `hmi_stop_candidate_r1/web_hmi/server.py`, SHA256
`21bda96fae14b0fa13db27d1fb21edd6f059e6d2037199944bdae50999569276`.
UI SHA256 `42700af1d5aad3409f49b00ed64c0d615bb490640cad5c8f4139380a6d53aa27`.
Reports: `hmi_stop_selftest_r1/report.json` (70 checks, real HTTP route and
negative baseline control); `hmi_stop_guards_r1/report.json` (five suites);
`hmi_stop_install_r2/report.json` (success, resumes retained failed r1 restart);
`hmi_stop_install_r2/scope_verify.json` (control functions/handlers unchanged);
`hmi_stop_installed_idle_r1/summary.json` and `local_stop_verify.json` (30-second
direct Wi-Fi, 29 snapshots, +590 good frames, zero new errors, latch=1 throughout,
first-fault fields and earlier downloaded log lines retained);
`HMI_STOP_FIX_REPORT.md`. Remote backups use `.before_local_stop_hmi_fix`.
The exact owned HMI process was restarted under systemd after passwordless
sudo was unavailable. No MCU restart/reflash was needed.

Operator has now confirmed B1 USER is released. Passive retention check passed:
`b1_released_idle_r1/summary.json` and `release_verify.json`, 10 seconds,
11 snapshots, raw status 141 and HMI latch=1 throughout, +200 good frames,
no UART/HTTP errors, PWM=0, ARM=0, bus reported 0 V. First-fault fields still
match the pre-fix snapshot. CLEAR/ARM/START counts remain zero. This confirms
idle latch retention after operator-confirmed release; active-PWM stopping,
restart inhibition under ENABLE and explicit safe reset remain unqualified.

The following read is the historical pre-fix evidence:

Read direct Wi-Fi /api/status after the reported press:

```
fw_build=2026101205  mc_fw_build=2026101204
state=SAFE  pwm=0  vdc=0.0  hmi_hv_armed=0
bp_status=141 (0x8D: LOCAL_STOP=0x80, FAULT=0x08, ESTOP=0x04, LINK=0x01)
bp_fault=1  mc_diag_valid=1
bp_good=9707  bp_bad=0  bp_bad_cnt=0  bp_transport_fault=0
hmi_local_stop_latched=0
```

Before the press, the 30-second recorded idle run had bp_status=9 and no
local-stop bit, PWM off, +601 correct frames and no errors. The new 0x80 bit
is evidence of the installed Nucleo latch becoming set after the operator
action; it is NOT an active-PWM stop timing measurement. Explicit release of
the button was not separately confirmed in the latest message.

RESOLVED: hmi_local_stop_latched was 0 even though bp_status & 0x80 is 1.
The deployed fix and evidence are described above. Keep raw bp_status intact
and do not clear the latch to hide an inconsistency. First-fault history correctly
still records prior zero-bus MC_UNDER_VOLT, masks 0x0004/0x0004; the current
fault is ESTOP and local-stop bit gives the new context. Do not overwrite
first-fault history with a claimed unique physical driver fault.

## Installed Images And Evidence

Final reports are under artifacts/live_bench_20261012/local_button:

- DEPLOY_REPORT.md: final installation and remaining physical checks.
- install_r4/report.json: successful installation, readback and calibration.
- installed_idle_r1/summary.json, status.jsonl, logs.txt: direct Wi-Fi evidence.
- candidate_r5/nucleo: Nucleo 2026101204, BIN/ELF/HEX in STM32CubeIDE/Debug.
- uno_peer_r2/UNOQ_MOTOR and uno_build: Uno Q 2026101205.
- wait_candidate_r6/web_hmi/server.py: installed Linux HMI.
- selftest_r6/report.json: 1038 STOP checks, 49 lifecycle checks, five negative
  controls including reversed MB1367 button polarity.
- peer_selftest_r2/report.json: 17 diagnostic/snapshot compatibility checks.
- hmi_guards_r5/report.json: five existing HMI guard suites.
- regression_r1/report.json: preceding baseline 57-suite regression, not a
  physical qualification of this new pair.

Final SHA256:

- Nucleo BIN: f35dfb3c583b1e6f4822d62f3e7971f3a7cac0e3beed76565f273dbfa203e949
- Uno flash ELF-ZSK BIN: afd0c72fc33c1519d9a85b6fd43356057a66048f82d20e1ebbbd56cd5e714714
- Initial HMI (superseded only by the HMI-only fix above): 5b9a25097b8d590db98ddcd37b121f30f573f4465fea67c512231a2f0dc40d15
- Unmodified calibration: a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17

Earlier images 1201/1202/1203 are superseded. FIX_REPORT.md is explicitly marked
superseded. Installation attempts and failures are retained, not counted as
final successes. Do not replay install_local_stop.py blindly: it is a pinned
one-off installer expecting predecessor versions/hashes which no longer match.

## Firmware Changes And Important Lessons

research/local_stop/local_stop.inc and local_stop.h implement a sticky local
STOP. Strong PC13 callback sets the flag, disables TIM1 MOE immediately, and
requests MCSDK STOP only after bMCBootCompleted. ENABLE cannot release it.
Output-enable sites check the latch, pin and pending EXTI inside a short saved
PRIMASK section; BKIN remains hardware-active. CLEAR requires released button,
no pending edge, outputs off, MCSDK IDLE and no current/past MCSDK faults.
CLEAR does not START. With zero bus, under-voltage can prevent fault release;
do not bypass that to make tests look successful.

MB1367 B1 is ACTIVE HIGH; released is LOW, R26 pulldown. C source and IOC use
RISING EXTI. The first draft assumed LOW and falsely latched at boot; final
1204 fixes it. Official ST schematic, sheet 3:
https://www.st.com/resource/en/schematic_pack/mb1367-g431rb-c04_schematic.pdf

New Nucleo build IDs must be added to Uno diagnostic decoding and BW_NUCLEO_BUILD
on BOTH snapshot peers. This was initially missed, producing unavailable
diagnostics. Final 1205/1204 is a matched pair with the issue corrected.

Uno was based on the verified 1108 TLS-free sketch; only build ID and the two
diagnostic peer headers change. Earlier dynamic loader failures came from
k_current_get TLS relocations; k_sched_current_thread_query is used instead.
tools/unoq_llext_check.py must pass before exporting any new Uno image. Internal
RPC can become unavailable after programming/hotplug; verify live identity
before considering repeated flashing. It recovered after the final update;
do not request another reboot without evidence it is needed.

Tools: prepare_nucleo_local_stop.py, prepare_unoq_local_stop_peer.py,
prepare_trial_wait_fix.py, local_stop_wait_selftest.py,
local_stop_peer_selftest.py, nucleo_button_restart_audit.py.
Generators pin artifact baselines; preserve those frozen sources and reports.

## HMI And Access

- Direct Wi-Fi: http://192.168.1.138:8080, /api/status read-only.
- WifiHmi(..., via_wsl=False) for actual Wi-Fi evidence.
- collect_wifi_telemetry.py provides HTTP GET-only telemetry/log capture.
- Private token file .unoq_ssh/control_token. Never print credentials.
- SSH arduino@192.168.1.138:2222, pinned .unoq_ssh/id_ed25519 and known_hosts.
- ADB Uno serial 3880458060; most recent USB COM10.
- ST-Link/Nucleo serial 003A002C3335510933383531; COM13.
- STM32CubeProgrammer CLI under C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin.
- Remote HMI /home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/server.py, service
  unoq-hmi.service. Use its .venv Python for modules, not bare system Python.
- Calibration /home/arduino/.config/mic-ai/vbus_calibration.json. Preserve bytes,
  original identity and measured point 322.7 V versus MCU 325 V, zero 0/0.
  No repeat zero calibration has been requested or performed.

After valid authenticated low-bus preparation, waiting no longer expires.
This is NOT an unlimited motor-running permission. Fresh powered idle
observations, identity, fault, voltage, temperature and transport checks still
apply. Active ARM expiry, one-shot use, 3-second trial and 5-Hz ceiling remain.
Identity change/counter rollback invalidates preparation. New-pair physical
PWM/local-STOP evidence is required; none was fabricated. Current session is
not prepared or armed. Do not silently renew an old grant under HV.

## Hardware And Safety Scope

AIR56B2 induction-motor stand: Nucleo G431RB + IHM09M2 + STEVAL-IPM15B, supervised
by Uno Q. UART Nucleo PB6 TX / PB7 RX, Uno D0/D1 Serial1, common reference.
PWM PA8/PA9/PA10 and PA7/PB0/PB1; SD active LOW on PA6/TIM1_BKIN, TP23.
AS5600 connects through Uno Q I2C2; communication and qualified angle/speed
are distinct. Encoder is not required for current scalar V/f.

Powered operation is autonomous with PC USB and ALL Saleae wires disconnected;
Wi-Fi controls/log retrieval only. On powered stand do not attach debugger,
flash images, touch wiring or run pin diagnostics. No power-stage activation
is authorized by this handoff. User is frustrated by repeated confirmations
and artificial preparation expiry: carry forward established state and ask
only genuinely missing facts for a changed physical test.

Prior motor rotation was operator-confirmed; a previous 50-Hz/30-second attempt
stopped around 5.5 s with MC_DP, not a proven successful 30-second run. The new
pair is verified in idle only. Do not promise full protection, fault-free
powered operation, certified safety or resolved MC_DP on that basis.

## Broader Project Goals

Roadmap: scalar V/f first, then vector FOC, AI adaptation and eventually learned
modulation/observation. Use AIR56B2 documented nameplate data; do not label
hidden fitted electrical parameters as nameplate or measured identification.
Documentation should be assembly-ready PDF/SVG with coherent connector tables;
editable CAD imports are secondary. Article/Word work has separate existing
artifacts; do not re-edit the article merely to accomplish this bench task.

Separate theoretical track C:\mic_theory, GitHub 11lisov11/mic_theory issue #1:
sensorless probing symmetry, asymmetric noise and Bayesian risk, strong fixed
baselines, shared seeds, untouched held-out sets. No true angle in online
algorithms, no positive claim without statistics/literature verification.
Do not confuse simulation evidence with hardware validation. Old research
automation may still exist; this handoff does not retarget or authorize it to
actuate hardware. Check current reports in that track before future research.
