#include <cassert>
#include <cstdio>
#define __DMB() ((void)0)
#ifndef MIC_STACK_GUARD_H
#define MIC_STACK_GUARD_H
#include <stdint.h>
/* The stack floor is linker-enforced ABOVE data/noinit/unchanged512B heap.
 * Fill only unused stack before HAL/NVIC initialization. No IRQ masking in RUN.
 * First32bytes are a fail-closed canary; PC reads the rest for high-water data.
 */
uint32_t stack_space[1056];
#define __StackLimit stack_space[0]
enum {MIC_STACK_PATTERN=0xa5a55a5aU,MIC_STACK_GUARD_WORDS=8};
volatile uint32_t mic_stack_guard_failed;
static void mic_stack_guard_init(void){
 uintptr_t sp=(uintptr_t)&stack_space[1024];
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

int main(){
 for(unsigned i=0;i<1056;++i)stack_space[i]=0;
 mic_stack_guard_init();assert(mic_stack_guard_ok());
 assert(stack_space[1007]==MIC_STACK_PATTERN&&stack_space[1008]==0&&stack_space[1024]==0);
 for(unsigned i=0;i<8;++i){mic_stack_guard_failed=0;stack_space[i]^=1;assert(!mic_stack_guard_ok());
  stack_space[i]^=1;assert(!mic_stack_guard_ok());mic_stack_guard_failed=0;assert(mic_stack_guard_ok());}
 puts("guard boundaries and sticky fail-closed PASS");
}