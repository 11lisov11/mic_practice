#ifndef MIC_FOC_TIMING_IRQ_H
#define MIC_FOC_TIMING_IRQ_H
#include "main.h"
#include "foc_timing_core.h"
extern ft_irq_meter mic_foc_irq_meter;
static inline ft_irq_token mic_foc_irq_begin(void){
 /* A handler also called as an ordinary C function is not IRQ time. */
 uint32_t outer=(__get_IPSR()!=0U)&&((SCB->ICSR&SCB_ICSR_RETTOBASE_Msk)!=0U);
 uint32_t now=DWT->CYCCNT;
 ft_irq_token t=ft_irq_enter(&mic_foc_irq_meter,now,outer);__DMB();return t;
}
static inline void mic_foc_irq_end(ft_irq_token*t){
 __DMB();ft_irq_leave(&mic_foc_irq_meter,*t,DWT->CYCCNT);__DMB();
}
/* GCC cleanup covers every early return as well as normal handler completion. */
#define MIC_FOC_IRQ_SCOPE ft_irq_token mic_foc_scope \
 __attribute__((cleanup(mic_foc_irq_end)))=mic_foc_irq_begin()
#endif
