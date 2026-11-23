"""Test the actual RAM recorder and candidate IRQ against host register stubs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from decode_ipm_break_snapshot import decode, MAGIC, SIZE, FIELDS
from ipm_sd_irq_selftest import function
from prepare_ipm_break_snapshot import HEADER, REFERENCE, patched_irq, patched_main


def host_program():
    irq = patched_irq((REFERENCE / "Src/stm32g4xx_mc_it.c").read_text(encoding="utf-8-sig"))
    library = (REFERENCE / "Src/pwm_curr_fdbk.c").read_text(encoding="utf-8-sig")
    program = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#define __weak
#define TIM_SR_BIF (1U << 7)
#define TIM_SR_B2IF (1U << 8)
#define MC_DP_FAULT 0x400
#define MC_NO_FAULTS 0
#define MC_OVER_VOLT 2
#define MC_OVER_CURR 1
struct TIM_TypeDef { uint32_t SR, DIER, BDTR, CNT, ARR, CCR1, CCR2, CCR3; } timer;
struct { uint32_t IDR; } gpio;
#define TIM1 (&timer)
#define GPIOA (&gpio)
void __DMB() {}
#include "first_break_snapshot.h"
volatile mic_break_snapshot_t mic_first_break;
volatile mic_break_snapshot_t mic_first_start_break;
volatile uint32_t mic_break_start_window;
volatile uint32_t mic_break_irq_count;
volatile mic_break_context_t mic_break_context[2];
volatile uint32_t mic_break_context_index, mic_break_context_valid;
struct PWMC_Handle_t { bool OverVoltageFlag, OverCurrentFlag, driverProtectionFlag, BrakeActionLock; uint8_t Motor; };
struct { PWMC_Handle_t _Super; } PWM_Handle_M1;
unsigned off_calls, scheduler_calls, cases;
uint32_t clock_ms;
bool held_low;
uint32_t HAL_GetTick() { return clock_ms; }
bool LL_TIM_IsActiveFlag_BRK(TIM_TypeDef *t) { return (t->SR & TIM_SR_BIF) != 0; }
bool LL_TIM_IsActiveFlag_BRK2(TIM_TypeDef *t) { return (t->SR & TIM_SR_B2IF) != 0; }
void LL_TIM_ClearFlag_BRK(TIM_TypeDef *t) { if (!held_low) t->SR &= ~TIM_SR_BIF; }
void LL_TIM_ClearFlag_BRK2(TIM_TypeDef *t) { if (!held_low) t->SR &= ~TIM_SR_B2IF; }
void LL_TIM_DisableIT_BRK(TIM_TypeDef *t) { t->DIER &= ~(1U << 7); }
void PWMC_SwitchOffPWM(PWMC_Handle_t *) { ++off_calls; timer.BDTR &= ~(1U << 15); }
void MC_Scheduler() { ++scheduler_calls; }
void reset() {
 std::memset(const_cast<mic_break_snapshot_t *>(&mic_first_break),0,sizeof(mic_first_break));
 std::memset(const_cast<mic_break_snapshot_t *>(&mic_first_start_break),0,sizeof(mic_first_start_break));
 std::memset(const_cast<mic_break_context_t *>(mic_break_context),0,sizeof(mic_break_context));
 mic_break_start_window=0; mic_break_irq_count=0; mic_break_context_index=0; mic_break_context_valid=0;
 PWM_Handle_M1={}; off_calls=scheduler_calls=0; held_low=false; clock_ms=1234;
 timer={0,1U<<7,(1U<<12)|(1U<<15),37,4000,500,1500,2500}; gpio.IDR=0;
}
'''
    program += function(library, "PWMC_DP_Handler") + "\n"
    program += function(library, "PWMC_IsFaultOccurred") + "\n"
    program += function(irq, "TIMx_BRK_M1_IRQHandler") + "\n"
    program += r'''
int main(int argc, char **argv) {
 static_assert(sizeof(mic_break_snapshot_t)==92, "RAM ABI");
 for (unsigned flags=0; flags<4; ++flags) {
  reset(); timer.SR=((flags&1)?TIM_SR_BIF:0)|((flags&2)?TIM_SR_B2IF:0);
  const uint32_t original_sr=timer.SR;
  TIMx_BRK_M1_IRQHandler();
  assert(scheduler_calls==1 && timer.SR==0 && (timer.BDTR & (1U<<12)));
  assert(off_calls==((flags&1U)+((flags>>1U)&1U)));
  if (!flags) {
   assert(mic_first_break.magic==0 && mic_break_irq_count==0);
   assert(timer.BDTR & (1U<<15)); assert(timer.DIER & (1U<<7));
  } else {
   assert(mic_first_break.magic==MIC_BREAK_MAGIC && mic_break_irq_count==1);
   assert(mic_first_break.schema==2 && mic_first_break.bytes==92);
   assert(mic_first_break.tim_sr==original_sr);
   assert(mic_first_break.tim_dier==(1U<<7));
   assert(mic_first_break.tim_bdtr==((1U<<12)|(1U<<15)));
   assert(mic_first_break.tick_ms==1234 && mic_first_break.tim_cnt==37);
   assert(mic_first_break.tim_arr==4000 && mic_first_break.tim_ccr1==500);
   assert(mic_first_break.tim_ccr2==1500 && mic_first_break.tim_ccr3==2500);
   assert(mic_first_break.context_valid==0);
   assert(!(timer.BDTR&(1U<<15)) && !(timer.DIER&(1U<<7)));
   assert(PWMC_IsFaultOccurred(&PWM_Handle_M1._Super)==MC_DP_FAULT);
  }
  ++cases;
 }
 reset(); mic_break_context_t a={1200,-17,6,0,0,321,-50,99};
 mic_break_publish_context(&a);
 timer.SR=TIM_SR_BIF; gpio.IDR=1U<<6; timer.BDTR&=~(1U<<15);
 TIMx_BRK_M1_IRQHandler();
 assert(mic_first_break.context_valid==1 && mic_first_break.gpioa_idr==(1U<<6));
 assert(mic_first_break.context.reference_speed_unit==-17);
 assert(mic_first_break.context.temperature_deci_c==-50);
 assert(mic_first_break.context.tick_ms==1200 && mic_first_break.context.command_sequence==99);
 assert(!(mic_first_break.tim_bdtr&(1U<<15))); ++cases;
 mic_break_snapshot_t saved=*const_cast<const mic_break_snapshot_t *>(&mic_first_break);
 mic_break_context_t b={1235,100,7,0x400,0x400,320,520,100};
 mic_break_publish_context(&b); timer.SR=TIM_SR_B2IF; clock_ms=1300;
 TIMx_BRK_M1_IRQHandler();
 mic_break_snapshot_t repeated=*const_cast<const mic_break_snapshot_t *>(&mic_first_break);
 assert(std::memcmp(&saved,&repeated,sizeof(saved))==0 && mic_break_irq_count==2); ++cases;
 mic_break_irq_count=UINT32_MAX; TIMx_BRK_M1_IRQHandler(); // no active flag
 assert(mic_break_irq_count==UINT32_MAX); timer.SR=TIM_SR_BIF;
 TIMx_BRK_M1_IRQHandler(); assert(mic_break_irq_count==UINT32_MAX); ++cases;
 reset(); held_low=true; timer.SR=TIM_SR_BIF;
 for (unsigned i=0;i<1000;++i) if(timer.DIER&(1U<<7)) TIMx_BRK_M1_IRQHandler();
 assert(off_calls==1 && scheduler_calls==1 && mic_break_irq_count==1);
 assert(timer.SR==TIM_SR_BIF && !(timer.DIER&(1U<<7)) && (timer.BDTR&(1U<<12))); ++cases;
 // A preempted publisher has written the inactive bank but not published it.
 reset(); mic_break_publish_context(&a);
 mic_break_copy_context(&mic_break_context[mic_break_context_index^1U],&b);
 timer.SR=TIM_SR_BIF; TIMx_BRK_M1_IRQHandler();
 assert(mic_first_break.context.command_sequence==99); ++cases;
 reset(); mic_break_publish_context(&b); timer.SR=TIM_SR_BIF;
 TIMx_BRK_M1_IRQHandler();
 assert(mic_first_break.context.command_sequence==100); ++cases;
 assert(mic_first_start_break.magic==0); // Startup/idle event did not consume START recorder.
 mic_break_start_window=1; clock_ms=1500; timer.SR=TIM_SR_BIF;
 TIMx_BRK_M1_IRQHandler();
 assert(mic_first_start_break.magic==MIC_BREAK_MAGIC && mic_first_start_break.start_window==1);
 assert(mic_first_start_break.tick_ms==1500 && mic_first_break.tick_ms==1234); ++cases;
 mic_break_start_window=0; clock_ms=1600; timer.SR=TIM_SR_B2IF;
 TIMx_BRK_M1_IRQHandler(); mic_break_start_window=1; clock_ms=1700; timer.SR=TIM_SR_BIF;
 TIMx_BRK_M1_IRQHandler();
 assert(mic_first_start_break.tick_ms==1500 && mic_first_break.tick_ms==1234); ++cases;
 if (argc==2) {
  FILE *f=std::fopen(argv[1],"wb"); assert(f);
  mic_break_snapshot_t fixture=*const_cast<const mic_break_snapshot_t *>(&mic_first_break);
  assert(std::fwrite(&fixture,1,sizeof(fixture),f)==sizeof(fixture)); std::fclose(f);
 }
 std::printf("%u host IRQ/snapshot cases passed\n",cases);
}
'''
    return program


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    program = out / "host_test.cpp"
    program.write_text(host_program(), encoding="utf-8")
    with tempfile.TemporaryDirectory() as folder:
        executable = Path(folder) / "snapshot.exe"
        build = subprocess.run([shutil.which("g++"), "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(HEADER.parent), str(program), "-o", str(executable)], capture_output=True, text=True)
        (out / "compile.log").write_text(build.stdout + build.stderr)
        if build.returncode:
            raise RuntimeError("Host compilation failed; see compile.log")
        run = subprocess.run([str(executable), str(out / "fixture.bin")], capture_output=True, text=True)
        (out / "run.log").write_text(run.stdout + run.stderr)
        if run.returncode:
            raise RuntimeError("Snapshot host assertions failed")
    checks = []
    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
    fixture = decode((out / "fixture.bin").read_bytes())
    check("decode actual C struct", fixture["captured"] and fixture["cached_context"]["vbus_v"] == 320)
    check("no event zero record", not decode(bytes(SIZE))["captured"])
    values = list(struct.unpack("<23I", (out / "fixture.bin").read_bytes()))
    for field in (15, 20):
        signed = values.copy(); signed[field] = 0xFFFFFFCE
        result = decode(struct.pack("<23I", *signed))
        check(f"signed field {field}", result["raw"][FIELDS[field]] == -50)
    rollover = values.copy(); rollover[3] = 5; rollover[14] = 0xFFFFFFFE
    check("tick rollover", decode(struct.pack("<23I", *rollover))["cached_context"]["age_ms"] == 7)
    invalid_context = values.copy(); invalid_context[13] = 0
    check("missing context not synthesized", decode(struct.pack("<23I", *invalid_context))["cached_context"] is None)
    for name, data in (("short", bytes(SIZE-1)), ("long", bytes(SIZE+1)),
                       ("uncommitted", struct.pack("<23I", 0, *values[1:]))):
        try:
            decode(data)
        except ValueError:
            checks.append(name)
        else:
            raise AssertionError(name)
    for index, bad in ((0, MAGIC^1), (1, 3), (2, 84), (4, 0), (13, 2), (22, 2)):
        corrupt = values.copy(); corrupt[index] = bad
        try:
            decode(struct.pack("<23I", *corrupt))
        except ValueError:
            checks.append(f"reject invalid field {index}")
        else:
            raise AssertionError(index)
    original_main = (REFERENCE / "Src/main.c").read_text(encoding="utf-8-sig")
    new_main = patched_main(original_main)
    check("normal UART builder unchanged except context", 'reply[14] = 0U;' in new_main)
    check("CLEAR does not erase first hardware event", function(new_main, "uno_clear_diagnostics") == function(original_main, "uno_clear_diagnostics"))
    wrapped_start = ('    if (start_state == IDLE) {\n'
        '      mic_break_start_window = 1U;\n'
        '      if (!MC_StartMotor1()) {\n'
        '        mic_break_start_window = 0U;\n'
        '        start_failed = true;\n'
        '      }\n'
        '    }')
    original_start = '    if (start_state == IDLE && !MC_StartMotor1()) start_failed = true;'
    check("command guard unchanged apart from diagnostic marker",
          function(new_main, "uno_handle_valid_frame").replace(wrapped_start, original_start)
          == function(original_main, "uno_handle_valid_frame"))
    check("STOP unchanged apart from diagnostic marker",
          function(new_main, "uno_stop_motor").replace("  mic_break_start_window = 0U;\n", "")
          == function(original_main, "uno_stop_motor"))
    original_irq = (REFERENCE / "Src/stm32g4xx_mc_it.c").read_text(encoding="utf-8-sig")
    new_irq = patched_irq(original_irq)
    check("protection IRQ otherwise byte-identical",
        function(new_irq,"TIMx_BRK_M1_IRQHandler").replace("  mic_break_capture_first(HAL_GetTick());\n", "") == function(original_irq,"TIMx_BRK_M1_IRQHandler"))
    report = dict(pass_=True, host_irq_cases=12, decoder_and_source_cases=len(checks),
                  checks=checks, hardware_commands=0,
                  scope="Host register stubs; not physical ISR timing or IPM fault-cause qualification",
                  source_sha256=hashlib.sha256(HEADER.read_bytes()).hexdigest())
    report["pass"] = report.pop("pass_")
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"pass": True, "cases": 12+len(checks)}))


if __name__ == "__main__":
    main()
