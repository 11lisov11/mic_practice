#ifndef MIC_IRQ_BREAKDOWN_H
#define MIC_IRQ_BREAKDOWN_H
#include <stdint.h>
#include <string.h>
enum {IB_COUNT=9};
typedef struct {volatile uint32_t seq,count,cycles;} ib_counter;
typedef struct {ib_counter irq[IB_COUNT];} ib_meter;
typedef struct {uint32_t count[IB_COUNT],cycles[IB_COUNT],valid,stamp;} ib_snapshot;
/* One writer per real exception; same-priority IRQs cannot preempt themselves.
 * Counts/cycles are inclusive: nesting is NEVER summed as CPU utilisation. */
static inline void ib_leave(ib_meter*m,unsigned id,uint32_t elapsed){
 if(id>=IB_COUNT)return;
 ib_counter*c=&m->irq[id];++c->seq;
 __asm__ volatile("":::"memory");++c->count;c->cycles+=elapsed;
 __asm__ volatile("":::"memory");++c->seq;
}
static inline void ib_read(const ib_meter*m,ib_snapshot*s,uint32_t stamp){
 memset(s,0,sizeof(*s));s->stamp=stamp;
 for(unsigned i=0;i<IB_COUNT;++i)for(unsigned retry=0;retry<4;++retry){
  const ib_counter*c=&m->irq[i];uint32_t q=c->seq;
  __asm__ volatile("":::"memory");uint32_t n=c->count,t=c->cycles;
  __asm__ volatile("":::"memory");
  if(!(q&1U)&&q==c->seq){s->count[i]=n;s->cycles[i]=t;s->valid|=1U<<i;break;}
 }
}
static inline void ib_delta(const ib_meter*m,const ib_snapshot*begin,uint32_t now,uint32_t words[21]){
 uint32_t valid=begin->valid;
 for(unsigned i=0;i<IB_COUNT;++i){
  uint32_t n=0,t=0,ok=0;
  for(unsigned retry=0;retry<4;++retry){
   const ib_counter*c=&m->irq[i];uint32_t q=c->seq;
   __asm__ volatile("":::"memory");n=c->count;t=c->cycles;
   __asm__ volatile("":::"memory");
   if(!(q&1U)&&q==c->seq){ok=1;break;}
  }
  if(!ok)valid&=~(1U<<i);
  words[2*i]=(valid&(1U<<i))?n-begin->count[i]:0;
  words[2*i+1]=(valid&(1U<<i))?t-begin->cycles[i]:0;
 }
 words[18]=begin->stamp;words[19]=now;words[20]=valid;
}
#endif
