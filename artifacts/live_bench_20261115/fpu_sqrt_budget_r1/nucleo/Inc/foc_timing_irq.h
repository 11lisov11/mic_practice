#ifndef MIC_FOC_TIMING_IRQ_H
#define MIC_FOC_TIMING_IRQ_H
#include "main.h"
#include "foc_timing_core.h"
#include "irq_breakdown.h"
extern ft_irq_meter mic_foc_irq_meter;
extern ib_meter mic_foc_irq_detail;
typedef struct {ft_irq_token root;uint32_t begin,id,real;} mic_irq_token;
static inline mic_irq_token mic_foc_irq_begin(unsigned id,int vector){
 uint32_t real=__get_IPSR()==(uint32_t)(vector+16);
 uint32_t outer=real&&((SCB->ICSR&SCB_ICSR_RETTOBASE_Msk)!=0U);
 uint32_t now=DWT->CYCCNT;
 mic_irq_token t={ft_irq_enter(&mic_foc_irq_meter,now,outer),now,id,real};__DMB();return t;
}
static inline void mic_foc_irq_end(mic_irq_token*t){
 __DMB();uint32_t now=DWT->CYCCNT;
 ft_irq_leave(&mic_foc_irq_meter,t->root,now);
 if(t->real)ib_leave(&mic_foc_irq_detail,t->id,now-t->begin);
 __DMB();
}
#define MIC_FOC_IRQ_SCOPE_NAMED(id,vector) mic_irq_token mic_foc_scope \
 __attribute__((cleanup(mic_foc_irq_end)))=mic_foc_irq_begin(id,vector)
#endif
