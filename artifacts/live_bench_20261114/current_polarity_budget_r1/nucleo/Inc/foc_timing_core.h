#ifndef MIC_FOC_TIMING_CORE_H
#define MIC_FOC_TIMING_CORE_H
#include <stdint.h>
#include <string.h>
/* Only the outermost instrumented handler writes this meter. Nested handlers
 * are included in its interval and never double-counted. Thread snapshots use
 * seq, without masking any interrupt or changing its priority. */
typedef struct {volatile uint32_t seq,cycles,roots;} ft_irq_meter;
typedef struct {uint32_t begin,outer;} ft_irq_token;
typedef struct {uint32_t now,irq,roots,valid;} ft_clock;
static inline ft_irq_token ft_irq_enter(ft_irq_meter*m,uint32_t now,uint32_t outer){
 ft_irq_token t={now,outer};if(outer)++m->seq;return t;
}
static inline void ft_irq_leave(ft_irq_meter*m,ft_irq_token t,uint32_t now){
 if(t.outer){m->cycles+=now-t.begin;++m->roots;++m->seq;}
}
typedef struct {
 uint32_t wall,irq,cpu_upper,roots,max_wall,max_irq,max_cpu;
 uint32_t queue,adc_age,result_age,max_queue,max_result,steps,errors;
} ft_perf;
/* IRQ body time is a LOWER bound: exception entry/return and profiler edge
 * instructions stay in cpu_upper. No estimate is used as a safety exemption. */
static inline void ft_measure(ft_perf*p,ft_clock a,ft_clock b){
 uint32_t wall=b.now-a.now,irq=b.irq-a.irq;
 p->wall=wall;
 if(!a.valid||!b.valid||irq>wall){++p->errors;p->irq=0;p->cpu_upper=wall;p->roots=0;}
 else {p->irq=irq;p->cpu_upper=wall-irq;p->roots=b.roots-a.roots;}
 if(wall>p->max_wall)p->max_wall=wall;
 if(p->irq>p->max_irq)p->max_irq=p->irq;
 if(p->cpu_upper>p->max_cpu)p->max_cpu=p->cpu_upper;
}
enum {FT_NONE=0,FT_NO_SAMPLE=1,FT_ADC_INVALID=2,FT_ADC_AGE=3,
 FT_ESTIMATE_AGE=4,FT_OBSERVER_DT=5,FT_FAST_DURATION=6,
 FT_CONTROL=7,FT_OBSERVER=8,FT_REGULAR_ADC=9};
typedef struct {uint32_t state,word[28];} ft_first_fault;
#endif
