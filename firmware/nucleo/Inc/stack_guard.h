#ifndef MIC_STACK_GUARD_H
#define MIC_STACK_GUARD_H
#include <stdint.h>
/* The stack floor is linker-enforced ABOVE data/noinit/unchanged512B heap.
 * Fill only unused stack before HAL/NVIC initialization. No IRQ masking in RUN.
 * First32bytes are a fail-closed canary; PC reads the rest for high-water data.
 */
extern uint32_t __StackLimit;
enum {MIC_STACK_PATTERN=0xa5a55a5aU,MIC_STACK_GUARD_WORDS=8};
volatile uint32_t mic_stack_guard_failed;
static void mic_stack_guard_init(void){
 uint32_t sp;__asm volatile("mrs %0,msp":"=r"(sp));
 volatile uint32_t *at=&__StackLimit;
 for(; (uintptr_t)at+64U<sp;++at)*at=MIC_STACK_PATTERN;
 __DMB();
}
static int mic_stack_guard_ok(void){
 volatile uint32_t *at=&__StackLimit;
 for(unsigned i=0;i<MIC_STACK_GUARD_WORDS;++i)
  if(at[i]!=MIC_STACK_PATTERN){mic_stack_guard_failed=1U;return 0;}
 return mic_stack_guard_failed==0U;
}
#endif
