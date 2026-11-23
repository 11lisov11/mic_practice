#ifndef MIC_BOOT_RECORD_H
#define MIC_BOOT_RECORD_H
#include <stdbool.h>
#include <stdint.h>

/* Integer-only: safe before .data copy/.bss clear and before HAL_Init. */
enum { MB_MAGIC=0x31525442U, MB_BOR=1U<<27, MB_SOFTWARE=1U<<28,
       MB_RESET_MASK=0xFE000000U, MB_PREVIOUS_VALID=1U,
       MB_PREVIOUS_CLEARED=2U, MB_CURRENT_CLEARED=4U,
       MB_PENDING_SOFTWARE=8U, MB_MCP_RESET=0x4D435031U };
typedef struct {
  uint32_t magic,firmware,sequence,csr,previous_csr,flags,software_tag,crc;
} mb_record;
static inline uint32_t mb_crc(const mb_record *r) {
  const uint32_t w[7]={r->magic,r->firmware,r->sequence,r->csr,
                      r->previous_csr,r->flags,r->software_tag};
  uint32_t c=0xffffffffU;
  for(unsigned i=0;i<7U;++i)for(unsigned b=0;b<4U;++b){
    c^=(w[i]>>(8U*b))&255U;
    for(unsigned k=0;k<8U;++k)c=(c>>1)^((c&1U)?0x82f63b78U:0U);
  }
  return ~c;
}
static inline bool mb_valid(const mb_record *r,uint32_t firmware) {
  return r->magic==MB_MAGIC&&r->firmware==firmware&&r->sequence!=0U&&
         !(r->flags&~15U)&&r->crc==mb_crc(r);
}
static inline mb_record mb_next(const mb_record *old,uint32_t firmware,uint32_t csr) {
  const bool retained=mb_valid(old,firmware)&&!(csr&MB_BOR);
  mb_record r={MB_MAGIC,firmware,1U,csr,0U,0U,0U,0U};
  if(retained){
    r.sequence=old->sequence==0xffffffffU?1U:old->sequence+1U;
    r.previous_csr=old->csr;r.flags=MB_PREVIOUS_VALID;
    if(old->flags&MB_CURRENT_CLEARED)r.flags|=MB_PREVIOUS_CLEARED;
    if((csr&MB_SOFTWARE)&&(old->flags&MB_PENDING_SOFTWARE))r.software_tag=old->software_tag;
  }
  r.crc=mb_crc(&r);return r;
}
static inline void mb_confirm_clear(mb_record *r,uint32_t csr_after) {
  if(!(csr_after&MB_RESET_MASK))r->flags|=MB_CURRENT_CLEARED;
  r->crc=mb_crc(r);
}
static inline void mb_note_software(mb_record *r,uint32_t tag) {
  r->flags|=MB_PENDING_SOFTWARE;r->software_tag=tag;r->crc=mb_crc(r);
}
#endif
