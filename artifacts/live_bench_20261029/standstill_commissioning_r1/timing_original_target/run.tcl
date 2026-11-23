# Temporary CPU-only benchmark on a confirmed discharged USB bench.
# Preserve/restore all firmware SRAM and architectural registers. Never reset,
# write flash, call a motor routine, or change TIM/ADC/GPIO registers.
reset_config none
init
set was_running [expr {[string equal [$_TARGETNAME curstate] "running"]}]
halt
wait_halt 2000
proc saved_register {name} {
 set value [reg $name]
 if {![regexp {0x[0-9a-fA-F]+} $value hex]} {error "register unavailable: $name"}
 return $hex
}
set names {r0 r1 r2 r3 r4 r5 r6 r7 r8 r9 r10 r11 r12 lr pc xpsr msp psp control basepri faultmask primask}
set saved [dict create]
set snapshot_error [catch {
 foreach name $names {dict set saved $name [saved_register $name]}
 if {[catch {saved_register s0}]} {
  for {set i 0} {$i<16} {incr i} {set name d$i;dict set saved $name [saved_register $name]}
 } else {
  for {set i 0} {$i<32} {incr i} {set name s$i;dict set saved $name [saved_register $name]}
 }
 dict set saved fpscr [saved_register fpscr]
 set demcr [lindex [read_memory 0xe000edfc 32 1] 0]
 set dwt_ctrl [lindex [read_memory 0xe0001000 32 1] 0]
 set dwt_cycles [lindex [read_memory 0xe0001004 32 1] 0]
 dump_image {C:/mic_practice/artifacts/live_bench_20261029/standstill_commissioning_r1/timing_original_target/sram_before.bin} 0x20000000 0x8000
} snapshot_message]
if {$snapshot_error} {
 if {$was_running} {resume}
 echo "RAM_TIMING_SNAPSHOT_FAILED: $snapshot_message"
 shutdown error
}
set execution_error [catch {
 reg primask 1
 load_image {C:/mic_practice/artifacts/live_bench_20261029/standstill_commissioning_r1/timing_original/timing.elf}
 mwh 0x20007ff0 0xbe00
 mww 0xe000edfc [expr {$demcr|0x01000000}]
 mww 0xe0001000 [expr {$dwt_ctrl|1}]
 reg msp 0x20007f00
 reg psp 0x20007f00
 reg lr 0x20007ff1
 reg pc 0x20000124
 resume
 wait_halt 3000
 set stopped_pc [saved_register pc]
 if {$stopped_pc!=0x20007ff0 && $stopped_pc!=0x20007ff2} {error "unexpected benchmark stop: $stopped_pc"}
 dump_image {C:/mic_practice/artifacts/live_bench_20261029/standstill_commissioning_r1/timing_original_target/timing_result.bin} 0x200025f0 304
} execution_message]
halt
wait_halt 2000
set restore_error [catch {
 load_image {C:/mic_practice/artifacts/live_bench_20261029/standstill_commissioning_r1/timing_original_target/sram_before.bin} 0x20000000 bin
 verify_image {C:/mic_practice/artifacts/live_bench_20261029/standstill_commissioning_r1/timing_original_target/sram_before.bin} 0x20000000 bin
 dump_image {C:/mic_practice/artifacts/live_bench_20261029/standstill_commissioning_r1/timing_original_target/sram_restored.bin} 0x20000000 0x8000
 mww 0xe0001004 $dwt_cycles
 mww 0xe0001000 $dwt_ctrl
 mww 0xe000edfc $demcr
 dict for {name value} $saved {
  if {$name!="primask"} {reg $name $value}
 }
 reg primask [dict get $saved primask]
} restore_message]
if {$restore_error} {
 echo "RAM_TIMING_RESTORE_FAILED_TARGET_LEFT_HALTED: $restore_message"
 shutdown error
}
if {$was_running} {resume}
echo "RAM_TIMING_SRAM_AND_REGISTERS_RESTORED"
if {$execution_error} {
 echo "RAM_TIMING_EXECUTION_FAILED: $execution_message"
 shutdown error
}
echo "RAM_TIMING_COMPLETED_NO_FLASH_NO_MOTOR_COMMANDS"
shutdown
