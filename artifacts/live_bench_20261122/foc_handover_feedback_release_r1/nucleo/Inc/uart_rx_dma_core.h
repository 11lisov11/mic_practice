#ifndef MIC_UART_RX_DMA_CORE_H
#define MIC_UART_RX_DMA_CORE_H
#include <stdint.h>
enum {URD_BYTES=128U,URD_HALF=1U,URD_FULL=2U,URD_ERROR=4U,
 URD_OK=0,URD_WAIT=1,URD_GAP=2,URD_FAILED=3};
typedef struct {uint32_t calls,max_batch,gaps,dma_errors,retries;uint16_t cursor,reserved;} urd_state;
typedef struct {unsigned first,count,result;} urd_batch;
/* Caller provides a stable flags/CNDTR/flags snapshot, and acknowledges ONLY
 * those flags. Both boundaries pending means delay is ambiguous: never accept
 * wrapped/stale bytes as commands. No modulo arithmetic can hide that loss.
 */
static inline urd_batch urd_plan(urd_state*s,unsigned remaining,unsigned flags){
 urd_batch b={s->cursor,0,URD_OK};++s->calls;
 if(!remaining&&!(flags&URD_ERROR)){++s->retries;b.result=URD_WAIT;return b;}
 if(remaining>URD_BYTES||(flags&URD_ERROR)){
  ++s->dma_errors;b.result=URD_FAILED;
 }else if((flags&(URD_HALF|URD_FULL))==(URD_HALF|URD_FULL)){
  ++s->gaps;b.result=URD_GAP;
 }
 unsigned pos=(URD_BYTES-remaining)&(URD_BYTES-1U);
 if(b.result==URD_OK)b.count=(pos-s->cursor)&(URD_BYTES-1U);
 s->cursor=(uint16_t)pos;if(b.count>s->max_batch)s->max_batch=b.count;
 return b;
}
#endif
