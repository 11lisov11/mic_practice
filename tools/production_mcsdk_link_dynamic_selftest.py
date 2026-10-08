"""Execute unchanged production UART/control functions with host MCSDK/HAL mocks."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


PREAMBLE = r'''
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#define MC_NO_FAULTS 0U
#define MC_OVER_TEMP 0x08U
#define HAL_OK 0
#define RESET 0
#define UART_FLAG_ORE 1U
#define UART_FLAG_NE 2U
#define UART_FLAG_FE 4U
#define UART_FLAG_PE 8U
#define UART_FLAG_RXNE 16U
#define USART1_IRQn 37
void HAL_NVIC_DisableIRQ(int) {}
void HAL_NVIC_EnableIRQ(int) {}
enum MCI_State_t { IDLE, RUN, FAULT_NOW, FAULT_OVER };
struct { struct { int unused; } _Super; } BusVoltageSensor_M1;
struct { int unused; } TempSensor_M1;
struct UART_Registers { uint32_t ISR, RDR; } uart_registers;
struct { UART_Registers *Instance; } huart1 = { &uart_registers };
uint32_t now_ms;
uint16_t bus_v, mc_fault, mc_occurred;
MCI_State_t motor_state;
bool start_succeeds = true, tx_succeeds = true;
unsigned starts, stops, ramps, tests;
struct { bool moe, bie, level_low; unsigned flags; } test_timer;
#define TIM1 (&test_timer)
#define GPIOA 0
#define GPIO_PIN_6 64
#define GPIO_PIN_SET 1
bool LL_TIM_IsEnabledAllOutputs(decltype(TIM1) t) { return t->moe; }
int HAL_GPIO_ReadPin(int, int) { return test_timer.level_low ? 0 : 1; }
void LL_TIM_ClearFlag_BRK(decltype(TIM1) t) { if (!t->level_low) t->flags &= ~1U; }
void LL_TIM_ClearFlag_BRK2(decltype(TIM1) t) { if (!t->level_low) t->flags &= ~2U; }
bool LL_TIM_IsActiveFlag_BRK(decltype(TIM1) t) { return t->flags & 1U; }
bool LL_TIM_IsActiveFlag_BRK2(decltype(TIM1) t) { return t->flags & 2U; }
void LL_TIM_EnableIT_BRK(decltype(TIM1) t) { t->bie = true; }
int16_t ramp_target;
uint16_t ramp_duration;
std::array<uint8_t, 32> reply;
uint32_t HAL_GetTick() { return now_ms; }
MCI_State_t MC_GetSTMStateMotor1() { return motor_state; }
int16_t MC_GetMecSpeedReferenceMotor1() { return ramp_target; }
uint16_t MC_GetCurrentFaultsMotor1() { return mc_fault; }
uint16_t MC_GetOccurredFaultsMotor1() { return mc_occurred; }
bool MC_StopMotor1() { ++stops; if (!mc_fault) motor_state=IDLE; return true; }
bool MC_StartMotor1() { ++starts; if (start_succeeds) motor_state=RUN; return start_succeeds; }
bool MC_AcknowledgeFaultMotor1() { if (!mc_fault) motor_state=IDLE; return !mc_fault; }
void MC_ProgramSpeedRampMotor1(int16_t target, uint16_t duration) {
 ++ramps; ramp_target=target; ramp_duration=duration;
}
template<class T> uint16_t VBS_GetAvBusVoltage_V(T *) { return bus_v; }
template<class T> int16_t NTC_GetAvTemp_C(T *) { return 25; }
template<class T> int HAL_UART_Transmit(T *, uint8_t *data, unsigned size, unsigned) {
 if (size!=reply.size()) std::abort();
 std::memcpy(reply.data(), data, size); return tx_succeeds ? HAL_OK : 1;
}
#define __HAL_UART_GET_FLAG(h, flag) (false)
#define __HAL_UART_CLEAR_OREFLAG(h) ((h)->Instance->ISR &= ~UART_FLAG_ORE)
#define __HAL_UART_CLEAR_NEFLAG(h) ((h)->Instance->ISR &= ~UART_FLAG_NE)
#define __HAL_UART_CLEAR_FEFLAG(h) ((h)->Instance->ISR &= ~UART_FLAG_FE)
#define __HAL_UART_CLEAR_PEFLAG(h) ((h)->Instance->ISR &= ~UART_FLAG_PE)
'''


CASES = r'''
void check(bool condition, const char *name) {
 ++tests;
 if (!condition) { std::fprintf(stderr, "FAIL %s (check %u)\n", name, tests); std::exit(1); }
}
using Frame = std::array<uint8_t, UNO_FRAME_LEN>;
void checksum(Frame &f) { f.back()=uno_crc_xor(f.data()); }
Frame frame(uint8_t flags, uint8_t mode, uint32_t freq=0, uint8_t seq=1) {
 Frame f{}; f[0]=UNO_CMD_HDR0; f[1]=UNO_CMD_HDR1; f[2]=UNO_PROTOCOL_VERSION;
 f[3]=flags; f[4]=mode; f[5]=seq;
 for (unsigned i=0; i<4; ++i) f[6+i]=(uint8_t)(freq>>(8*i));
 checksum(f); return f;
}
void feed(const Frame &f) { for (auto b : f) uno_consume_byte(b); }
void reset(bool ready=false) {
 now_ms=0; bus_v=ready ? 310 : 0; mc_fault=mc_occurred=0; motor_state=IDLE;
 starts=stops=ramps=0; ramp_target=0; ramp_duration=0;
 start_succeeds=tx_succeeds=true; uart_registers={}; test_timer={}; reply={}; uno_link_init();
 if (ready) { uno_update_softstart_state(0); now_ms=3500; uno_update_softstart_state(now_ms); }
}
void scenarios() {
 reset(true); test_timer.level_low=true; test_timer.flags=1;
 feed(frame(UNO_FLAG_CLEAR_FAULT,0,0));
 check(uno_link.fault_latched && !test_timer.bie && starts==0, "CLEAR cannot rearm sustained break");
 test_timer.level_low=false; feed(frame(UNO_FLAG_CLEAR_FAULT,0,0,2));
 check(!uno_link.fault_latched && test_timer.bie && test_timer.flags==0 && starts==0,
       "clean CLEAR rearms interrupt without restarting motor");
 reset(true); test_timer.moe=true;
 check(!uno_rearm_break_irq() && !test_timer.bie, "active outputs cannot rearm break interrupt");
 reset(); feed(frame(UNO_FLAG_ENABLE, UNO_MODE_SCALAR, 5000));
 check(starts==0 && !uno_link.command_enabled, "zero bus no start");
 bus_v=310; uno_update_softstart_state(0);
 now_ms=3499; feed(frame(1,3,5000,2)); check(starts==0, "settle not early");
 now_ms=3500; feed(frame(1,3,5000,3));
 check(starts==1 && uno_link.command_enabled && motor_state==RUN, "start after 3500 ms");
 check(ramp_target==RPM_2_SPEED_UNIT(300) && ramp_duration==3000, "5 Hz ramp units");
 feed(frame(1,3,20000,4));
 check(starts==1 && ramps==2 && ramp_target==RPM_2_SPEED_UNIT(1200), "20 Hz no restart");
 feed(frame(1,3,20000,5)); check(ramps==2, "same speed no duplicate ramp");
 feed(frame(0,0,0,6)); check(!uno_link.command_enabled && motor_state==IDLE, "STOP");
 reset(true); feed(frame(1,3,5000)); feed(frame(UNO_FLAG_ESTOP,0,0,2));
 check(uno_link.fault_latched && uno_link.fault_code==UNO_FAULT_ESTOP && motor_state==IDLE, "ESTOP stops");
 feed(frame(1,3,5000,3)); check(starts==1, "ESTOP blocks restart");
 feed(frame(0,0,0,4)); check(uno_link.fault_latched, "STOP does not clear ESTOP");
 feed(frame(UNO_FLAG_CLEAR_FAULT,0,0,5)); check(!uno_link.fault_latched, "clean CLEAR releases latch");
 reset(true); feed(frame(1,3,5000)); now_ms+=300; uno_link_poll();
 check(!uno_link.fault_latched, "watchdog accepts 300 ms");
 ++now_ms; uno_link_poll();
 check(uno_link.fault_code==UNO_FAULT_TIMEOUT && motor_state==IDLE, "watchdog stops at 301 ms");
 reset(true); feed(frame(1,3,5000,255)); feed(frame(1,3,5000,0));
 check(!uno_link.fault_latched, "sequence wraps");
 feed(frame(1,3,5000,0)); check(uno_link.fault_latched && motor_state==IDLE, "frozen ENABLE stops");
 reset(true); start_succeeds=false; feed(frame(1,3,5000));
 check(uno_link.fault_latched && !uno_link.command_enabled, "MCSDK start failure latches");
 reset(true); feed(frame(1,3,5000)); mc_fault=0x400; motor_state=FAULT_NOW; uno_link_poll();
 check(uno_link.fault_latched && !uno_link.command_enabled, "MCSDK DP stops command");
 for (auto state : {FAULT_NOW, FAULT_OVER}) {
  reset(true); motor_state=state; feed(frame(1,3,5000));
  check(starts==0 && uno_link.fault_latched, "fault state rejects start");
 }
 reset(true); tx_succeeds=false; feed(frame(1,3,5000));
 check(uno_link.fault_latched && motor_state==IDLE, "reply TX failure stops");
 for (unsigned flag=1; flag<=8; flag<<=1) {
  reset(true); feed(frame(1,3,5000)); uart_registers.ISR=flag; USART1_IRQHandler(); uno_link_poll();
  check(uno_link.fault_latched && motor_state==IDLE && uart_registers.ISR==0, "UART hardware error stops");
 }
 reset(true); uno_link.good_count=UINT16_MAX; feed(frame(0,0));
 check(uno_link.good_count==UINT16_MAX, "counter saturates");
 reset(true); feed(frame(1,3,5000));
 check(reply[3] & UNO_STATUS_PWM_ACTIVE, "RUN telemetry PWM bit");
 check(reply[31]==uno_crc_xor(reply.data()) && reply[14]==0, "reply CRC and no relay");
 uint32_t build=uno_u32le(&reply[23]);
 check(build==MIC_NUCLEO_FW_BUILD_ID && (reply[29]&UNO_TELEMETRY_FW_BUILD_VALID), "reply build identity");
 for (uint16_t v : {0,199,200,249,250,310,385,386}) {
  reset(); bus_v=v; uno_update_softstart_state(0); uno_update_softstart_state(3500);
  check(uno_link.softstart_ready==(v>=250 && v<=385), "initial bus threshold");
  reset(true); bus_v=v; uno_update_softstart_state(3501);
  check(uno_link.softstart_ready==(v>=200 && v<=385), "hold bus hysteresis");
 }
 reset(); bus_v=310; now_ms=UINT32_MAX-1000; uno_update_softstart_state(now_ms);
 now_ms+=3499; uno_update_softstart_state(now_ms); check(!uno_link.softstart_ready, "settle wrap before boundary");
 ++now_ms; uno_update_softstart_state(now_ms); check(uno_link.softstart_ready, "settle uint32 wrap");
 reset(true); now_ms=UINT32_MAX-100; feed(frame(1,3,5000)); now_ms+=301; uno_link_poll();
 check(uno_link.fault_code==UNO_FAULT_TIMEOUT, "watchdog uint32 wrap");
 reset(true); feed(frame(1,3,10000));
 for (unsigned i=2; i<=61; ++i) { now_ms+=50; feed(frame(1,3,10000,(uint8_t)i)); }
 check(ramps==1 && ramp_duration==3000, "stable target heartbeats never restart ramp");
 reset(true); feed(frame(1,3,50000));
 check(ramp_duration==10000, "50 Hz starts at no more than 5 Hz per second");
 reset(true); feed(frame(1,3,5000)); bus_v=199; uno_link_poll();
 check(motor_state==IDLE && uno_link.fault_latched && uno_link.first_reason==UNO_DIAG_BUS,
       "loss of bus hold range stops without waiting for UART or MCSDK undervoltage");
 bus_v=310; now_ms+=3500; feed(frame(1,3,5000,2));
 check(starts==1 && uno_link.fault_latched, "bus recovery cannot auto-restart");
 reset(true); feed(frame(1,3,5000)); bus_v=386; uno_link_poll();
 check(motor_state==IDLE && uno_link.first_reason==UNO_DIAG_BUS, "overvoltage stops between frames");
}
void exhaustive_commands() {
 const uint32_t max_freq=MOTOR_MAX_SPEED_RPM*POLE_PAIR_NUM*1000U/60U;
 for (unsigned flags=0; flags<256; ++flags) for (unsigned mode=0; mode<256; ++mode)
  for (uint32_t freq : {0U, 1U, max_freq, max_freq+1U}) {
   reset(true); feed(frame((uint8_t)flags,(uint8_t)mode,freq));
   bool valid=flags==UNO_FLAG_ENABLE && mode==UNO_MODE_SCALAR && freq>=100 && freq<=max_freq;
   check(starts==(valid ? 1U : 0U), "all 256 flags x 256 modes x 4 frequencies");
  }
 for (unsigned byte=0; byte<UNO_FRAME_LEN; ++byte) for (unsigned bit=0; bit<8; ++bit) {
  reset(true); Frame f=frame(1,3,5000); f[byte]^=(uint8_t)(1U<<bit); feed(f);
  check(starts==0, "each single-bit corruption cannot start");
 }
 for (unsigned byte=14; byte<31; ++byte) {
  reset(true); Frame f=frame(1,3,5000); f[byte]=1; checksum(f); feed(f);
  check(starts==0 && uno_link.fault_latched, "service fields reject ENABLE");
 }
 for (unsigned byte=6; byte<31; ++byte) {
  reset(true); uno_latch_fault(UNO_FAULT_ESTOP);
  Frame f=frame(UNO_FLAG_CLEAR_FAULT,0); f[byte]=1; checksum(f); feed(f);
  check(uno_link.fault_latched && starts==0, "dirty CLEAR cannot release latch");
 }
}
void diagnostic_scenarios() {
 // Replay the exact observed NE-only fault during RUN, including queued data.
 for (unsigned prefix=0; prefix<UNO_FRAME_LEN; ++prefix)
  for (unsigned queued=0; queued<UNO_FRAME_LEN; ++queued) {
  reset(true); feed(frame(1,3,10000,80));
  Frame pending=frame(1,3,10000,81);
  for (unsigned i=0; i<prefix; ++i) uno_consume_byte(pending[i]);
  for (unsigned i=0; i<queued; ++i)
   check(uno_rx_push(pending[(prefix+i)%UNO_FRAME_LEN]), "queue bytes behind partial frame before NE");
  uart_registers.ISR=UART_FLAG_NE; USART1_IRQHandler(); uno_link_poll();
  check(motor_state==IDLE && uno_link.fault_latched && !uno_link.command_enabled,
        "NE during RUN stops at every parser position");
  check(uno_link.first_reason==UNO_DIAG_UART && uno_link.first_uart_errors==4
        && uno_link.first_sequence==80 && uno_link.first_current_faults==0,
        "NE-only evidence matches observed production fault");
  check(uno_rx_head==uno_rx_tail && uno_link.parser_state==0 && uno_link.parser_index==0,
        "NE discards queued bytes and resets partial parser");
  feed(frame(1,3,10000,82));
  check(starts==1 && uno_link.fault_latched, "NE cannot recover through ENABLE");
  feed(frame(0,0,0,83));
  check(uno_link.fault_latched, "STOP cannot silently clear NE");
  feed(frame(UNO_FLAG_CLEAR_FAULT,0,0,84));
  check(!uno_link.fault_latched && starts==1 && !uno_link.command_enabled,
        "explicit CLEAR releases NE without auto-start");
 }
 reset(true); feed(frame(1,3,5000)); uart_registers.ISR=UART_FLAG_ORE | UART_FLAG_FE;
 mc_fault=0x40; mc_occurred=0x440; USART1_IRQHandler(); uno_link_poll();
 check(uno_link.first_reason==UNO_DIAG_UART && uno_link.first_uart_errors==0x0a,
       "UART flags captured before hardware clear");
 check(uno_link.first_current_faults==0x40 && uno_link.first_occurred_faults==0x440,
       "first current and occurred MCSDK masks retained");
 const auto first_state=uno_link.first_motor_state;
 feed(frame(UNO_FLAG_ESTOP,0,0,2)); feed(frame(0,0,0,3));
 check(uno_link.first_reason==UNO_DIAG_UART && uno_link.first_motor_state==first_state,
       "STOP and ESTOP cannot overwrite first cause");
 check(reply[11]==(UNO_DIAG_TAG|UNO_DIAG_UART) && reply[12]==0xaa
       && ((reply[15] | (reply[16]<<8))==0x40)
       && ((reply[27] | (reply[28]<<8))==0x440) && reply[14]==0,
       "diagnostic reply layout preserves reserved relay and masks");
 mc_fault=0; motor_state=FAULT_OVER; feed(frame(UNO_FLAG_CLEAR_FAULT,0,0,4));
 check(uno_link.first_reason==0 && reply[11]==UNO_DIAG_TAG,
       "only clean CLEAR releases stored diagnostics");
 for (unsigned mask=1; mask<16; ++mask) {
  reset(true);
  uart_registers.ISR=((mask&1)?UART_FLAG_PE:0)|((mask&2)?UART_FLAG_FE:0)
    |((mask&4)?UART_FLAG_NE:0)|((mask&8)?UART_FLAG_ORE:0);
  USART1_IRQHandler(); uno_link_poll();
  check(uno_link.first_reason==UNO_DIAG_UART && uno_link.first_uart_errors==mask,
        "all UART flag combinations distinguished");
 }
 reset(true); tx_succeeds=false; feed(frame(1,3,5000));
 check(uno_link.first_reason==UNO_DIAG_TX && uno_link.first_tx_status==1,
       "transmit failure retains HAL status");
 reset(true); Frame f=frame(1,3,5000); f[31]^=1; feed(f);
 check(uno_link.first_reason==UNO_DIAG_CRC, "CRC reason");
 reset(true); f=frame(1,3,5000); f[2]=3; checksum(f); feed(f);
 check(uno_link.first_reason==UNO_DIAG_VERSION, "version reason");
 reset(true); feed(frame(1,3,5000)); feed(frame(1,3,5000));
 check(uno_link.first_reason==UNO_DIAG_REPLAY, "replay reason");
 reset(true); feed(frame(UNO_FLAG_ESTOP,0));
 check(uno_link.first_reason==UNO_DIAG_ESTOP, "ESTOP reason");
 reset(true); f=frame(1,3,5000); f[14]=1; checksum(f); feed(f);
 check(uno_link.first_reason==UNO_DIAG_SERVICE, "service reason");
 reset(true); feed(frame(1,2,5000));
 check(uno_link.first_reason==UNO_DIAG_COMMAND, "command reason");
 reset(true); feed(frame(1,3,0));
 check(uno_link.first_reason==UNO_DIAG_FREQUENCY, "frequency reason");
 reset(true); mc_fault=4; mc_occurred=4; motor_state=FAULT_NOW;
 uno_send_reply();
 check(uno_link.first_reason==UNO_DIAG_MCSDK && uno_link.first_current_faults==4,
       "MCSDK fault visible even with no ENABLE command");
 reset(true); bus_v=386; feed(frame(1,3,5000));
 check(uno_link.first_reason==UNO_DIAG_BUS, "bus guard reason");
 reset(true); start_succeeds=false; feed(frame(1,3,5000));
 check(uno_link.first_reason==UNO_DIAG_START, "start API reason");
 reset(true); feed(frame(1,3,5000)); now_ms+=301; uno_link_poll();
 check(uno_link.first_reason==UNO_DIAG_TIMEOUT, "watchdog reason");
 reset(true); uno_capture_diagnostics(UNO_DIAG_UART,8,0);
 f=frame(UNO_FLAG_CLEAR_FAULT,0); f[6]=1; checksum(f); feed(f);
 check(uno_link.first_reason==UNO_DIAG_UART, "dirty CLEAR cannot erase evidence");
 reset(true); mc_fault=4; mc_occurred=4; motor_state=FAULT_NOW; uno_send_reply();
 uart_registers.ISR=UART_FLAG_ORE; USART1_IRQHandler(); uno_link_poll(); uno_send_reply();
 check(uno_link.first_reason==UNO_DIAG_MCSDK && uno_link.last_bad_reason==UNO_DIAG_UART,
       "new bad counter cause not hidden behind earlier MCSDK fault");
 check((reply[12]>>4)==8 && (reply[22]>>4)==UNO_DIAG_UART,
       "last UART flags and counter cause exported independently");
 reset(true);
 for (unsigned i=0; i<127; ++i) check(uno_rx_push((uint8_t)i), "RX ring capacity");
 check(!uno_rx_push(128), "RX ring never overwrites unread bytes");
 for (unsigned i=0; i<127; ++i) { uint8_t b=255; check(uno_rx_pop(&b)&&b==i,"RX order"); }
 for (unsigned cycle=0; cycle<1000; ++cycle) {
  for (unsigned i=0; i<64; ++i) check(uno_rx_push((uint8_t)i), "ring wrap producer");
  for (unsigned i=0; i<64; ++i) { uint8_t b=255; check(uno_rx_pop(&b)&&b==i,"ring wrap consumer"); }
 }
 reset(true);
 for (unsigned seq=1; seq<=3; ++seq) for(auto b:frame(1,3,5000,seq))
  check(uno_rx_push(b), "buffer frames while main is delayed");
 uno_link_poll();
 check(starts==1 && uno_link.good_count==3 && !uno_link.fault_latched,
       "main consumes delayed complete frames without loss or duplicate start");
 uno_rx_overflow=1; uno_link_poll();
 check(uno_link.fault_latched && motor_state==IDLE && uno_link.last_bad_reason==UNO_DIAG_RX_BUFFER,
       "software RX overflow remains fail closed and diagnosed");
}
int main() {
 scenarios(); diagnostic_scenarios(); exhaustive_commands();
 std::printf("{\"pass\":true,\"assertions\":%u,\"command_combinations\":262144,\"single_bit_corruptions\":256}\n", tests);
}
'''


MUTATIONS = {
    "late_settle": (">=\n      MIC_EXTERNAL_SOFTSTART_SETTLE_MS", ">\n      MIC_EXTERNAL_SOFTSTART_SETTLE_MS"),
    "early_watchdog": ("> UNO_LINK_TIMEOUT_MS) {", ">= UNO_LINK_TIMEOUT_MS) {"),
    "zero_frequency_start": ("frequency_millihz < min_frequency_millihz || frequency_millihz > max_frequency_millihz ||\n      uno_mcsdk_fault_present()",
                             "false || frequency_millihz > max_frequency_millihz ||\n      uno_mcsdk_fault_present()"),
    "replay_allowed": ("frame[5] == uno_link.last_seq", "false"),
    "STOP_leaves_enabled": ("uno_link.command_enabled = false;", "/* missing disable */"),
    "dirty_CLEAR": ("uint8_t index = 6U;", "uint8_t index = 14U;"),
    "CRC_check_removed": ("uno_link.frame[UNO_FRAME_LEN - 1U] != uno_crc_xor(uno_link.frame)", "false"),
    "start_failure_ignored": ("IDLE && !MC_StartMotor1()", "IDLE && MC_StartMotor1()"),
    "NE_detection_removed": ("(UART_FLAG_ORE | UART_FLAG_NE | UART_FLAG_FE | UART_FLAG_PE);",
                             "(UART_FLAG_ORE | UART_FLAG_FE | UART_FLAG_PE);"),
    "UART_error_queue_not_flushed": ("if (errors != 0U || overflow != 0U) uno_rx_head = uno_rx_tail = 0U;",
                                     "/* queue incorrectly retained after error */"),
}


def mutation_check(compiler: str, program: str, out: Path) -> list[dict]:
    results = []
    # Mutations only affect temporary host translation units, never firmware files.
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        for name, (before, after) in MUTATIONS.items():
            if program.count(before) != 1:
                raise RuntimeError("Mutation anchor must be unique: " + name)
            unit, exe = folder / "mutant.cpp", folder / "mutant.exe"
            unit.write_text(program.replace(before, after, 1), encoding="utf-8")
            built = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                                    str(unit), "-o", str(exe)], capture_output=True, text=True, timeout=60)
            (out / (name + "_compile.log")).write_text(built.stdout + built.stderr, encoding="utf-8")
            if built.returncode:
                raise RuntimeError("Mutation must compile before testing: " + name)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
            (out / (name + "_run.log")).write_text(run.stdout + run.stderr, encoding="utf-8")
            results.append({"name": name, "detected": run.returncode != 0 and "FAIL " in run.stderr,
                            "failure": run.stderr.strip()})
    return results


def generate(root: Path) -> tuple[str, list[Path]]:
    project = root / "mcsdk_reference/AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV"
    main = project / "Src/main.c"
    motor = project / "Inc/acim_motor_parameters.h"
    stm = project / "Inc/mc_stm_types.h"
    text = main.read_text(encoding="utf-8-sig")
    # This entire USER CODE section is copied unchanged, including the parser and watchdog.
    begin = text.index("enum {", text.index("/* USER CODE BEGIN 0 */"))
    end = text.index("static void MX_USART1_UART_Init(void) {", begin)
    block = text[begin:end]
    definitions = motor.read_text(encoding="utf-8-sig")
    macros = []
    for name in ("POLE_PAIR_NUM", "MOTOR_MAX_SPEED_RPM"):
        match = re.search(r"^#define\s+" + name + r"\s+(\d+)", definitions, re.M)
        if not match:
            raise RuntimeError("Missing motor parameter " + name)
        macros.append(f"#define {name} {match[1]}")
    stm_text = stm.read_text(encoding="utf-8-sig")
    for name in ("U_01HZ", "U_RPM", "SPEED_UNIT"):
        match = re.search(r"^#define\s+" + name + r"\s+([^\n]+)", stm_text, re.M)
        if not match:
            raise RuntimeError("Missing speed unit " + name)
        macros.append(f"#define {name} {match[1]}")
    match = re.search(r"^#define\s+RPM_2_SPEED_UNIT\(rpm\)\s+([^\n]+)", stm_text, re.M)
    if not match:
        raise RuntimeError("Missing speed conversion")
    macros.append("#define RPM_2_SPEED_UNIT(rpm) " + match[1])
    return PREAMBLE + "\n" + "\n".join(macros) + "\n" + block + CASES, [main, motor, stm]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--mutation-check", action="store_true")
    args = parser.parse_args()
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    report = {"pass": False, "scope": "unchanged production control functions; mocked MCSDK/HAL, no physical PWM",
              "hardware_validated": False, "test_modifies_firmware": False,
              "source_includes_fault_diagnostics": True}
    try:
        program, sources = generate(root)
        unit = out / "host_test.cpp"
        unit.write_text(program, encoding="utf-8")
        report["sources"] = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
        compiler = shutil.which("g++")
        if not compiler:
            raise RuntimeError("g++ is required")
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "test.exe"
            result = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                                     str(unit), "-o", str(exe)], capture_output=True, text=True, timeout=60)
            (out / "compile.log").write_text(result.stdout + result.stderr, encoding="utf-8")
            if result.returncode:
                raise RuntimeError("Host compilation failed; see compile.log")
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
            (out / "run.log").write_text(run.stdout + run.stderr, encoding="utf-8")
            if run.returncode:
                raise RuntimeError("Dynamic test failed: " + run.stderr.strip())
            report.update(json.loads(run.stdout))
        if args.mutation_check:
            report["mutations"] = mutation_check(compiler, program, out)
            report["pass"] = report["pass"] and all(m["detected"] for m in report["mutations"])
    except Exception as exc:
        report["pass"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
