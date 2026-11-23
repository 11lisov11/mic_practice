ENTRY(bench_run)
MEMORY { RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 32K }
SECTIONS {
 .text : { *(.text*) *(.rodata*) } >RAM
 .ARM.extab : { *(.ARM.extab*) } >RAM
 .ARM.exidx : { *(.ARM.exidx*) } >RAM
 .data : { *(.data*) } >RAM
 .bss (NOLOAD) : { *(.bss*) *(COMMON) . = ALIGN(8); } >RAM
 _end = .;
 ASSERT(. < 0x20007400, "CPU-only fixture leaves less than 3 KiB stack")
}
