#ifndef MIC_CURRENT_SNAPSHOT_H
#define MIC_CURRENT_SNAPSHOT_H
#include "current_core.h"
/* Single ADC-IRQ writer, foreground reader. No interrupt masks or unbounded
 * waits. An interrupted copy is NEVER sent; a busy reader skips this packet. */
#ifndef CM_SNAPSHOT_COPY
#define CM_SNAPSHOT_COPY(dst,src) (*(dst)=*(src))
#endif
#ifndef CM_SNAPSHOT_BARRIER
#define CM_SNAPSHOT_BARRIER() __DMB()
#endif
static inline uint8_t cm_snapshot_read(cm_core*out,const cm_core*source,
                                      const volatile uint32_t*sequence){
 for(unsigned attempt=0;attempt<3;++attempt){
  uint32_t before=*sequence;CM_SNAPSHOT_BARRIER();
  if(before&1U)continue;
  CM_SNAPSHOT_COPY(out,source);CM_SNAPSHOT_BARRIER();
  if(before==*sequence)return 1;
 }
 return 0;
}
#endif
