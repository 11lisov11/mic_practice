
#include <cassert>
#include <cstdio>
#include "foc_timing_core.h"
#include "irq_breakdown.h"
struct Clock{uint32_t CYCCNT;};static Clock clock_hw,*DWT=&clock_hw;
struct Scb{uint32_t ICSR;};static Scb scb,*SCB=&scb;
static const uint32_t SCB_ICSR_RETTOBASE_Msk=2048;
static uint32_t ipsr;static uint32_t __get_IPSR(){return ipsr;}static void __DMB(){}
ft_irq_meter mic_foc_irq_meter={};ib_meter mic_foc_irq_detail={};
#ifndef MIC_FOC_TIMING_IRQ_H
#define MIC_FOC_TIMING_IRQ_H

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

static void early_return(){MIC_FOC_IRQ_SCOPE_NAMED(2,37);DWT->CYCCNT+=10;return;}
int main(){
 ipsr=53;SCB->ICSR=2048;DWT->CYCCNT=100;
 auto uart=mic_foc_irq_begin(2,37);DWT->CYCCNT=110;
 ipsr=41;SCB->ICSR=0;auto update=mic_foc_irq_begin(4,25);DWT->CYCCNT=160;mic_foc_irq_end(&update);
 ipsr=53;SCB->ICSR=2048;DWT->CYCCNT=200;mic_foc_irq_end(&uart);
 assert(mic_foc_irq_meter.cycles==100&&mic_foc_irq_meter.roots==1);
 assert(mic_foc_irq_detail.irq[2].count==1&&mic_foc_irq_detail.irq[2].cycles==100);
 assert(mic_foc_irq_detail.irq[4].count==1&&mic_foc_irq_detail.irq[4].cycles==50);
 // C call to another IRQ helper is not a second hardware exception.
 auto helper=mic_foc_irq_begin(1,11);DWT->CYCCNT=210;mic_foc_irq_end(&helper);
 assert(mic_foc_irq_detail.irq[1].count==0&&mic_foc_irq_meter.roots==1);
 early_return();assert(mic_foc_irq_detail.irq[2].count==2&&mic_foc_irq_meter.roots==2);
 puts("{\"actual_IRQ_wrapper_nested\":true,\"C_helper_not_double_counted\":true,\"early_return_cleanup\":true}");
}
