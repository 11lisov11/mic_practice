
/* Retained only when SRAM survives reset; never claim persistence over BOR. */
volatile mb_record mic_boot_retained __attribute__((section(".noinit.mic_boot"),aligned(4)));
static mb_record mic_boot_read(void){
 mb_record r;
 r.magic=mic_boot_retained.magic;r.firmware=mic_boot_retained.firmware;
 r.sequence=mic_boot_retained.sequence;r.csr=mic_boot_retained.csr;
 r.previous_csr=mic_boot_retained.previous_csr;r.flags=mic_boot_retained.flags;
 r.software_tag=mic_boot_retained.software_tag;r.crc=mic_boot_retained.crc;return r;
}
static void mic_boot_store(const mb_record*r){
 mic_boot_retained.crc=0U;__DMB();
 mic_boot_retained.magic=r->magic;mic_boot_retained.firmware=r->firmware;
 mic_boot_retained.sequence=r->sequence;mic_boot_retained.csr=r->csr;
 mic_boot_retained.previous_csr=r->previous_csr;mic_boot_retained.flags=r->flags;
 mic_boot_retained.software_tag=r->software_tag;
 __DMB();mic_boot_retained.crc=r->crc;__DMB();
}
void mic_boot_capture_early(void){
 const uint32_t csr=RCC->CSR;
 const mb_record old=mic_boot_read();
 mb_record r=mb_next(&old,MIC_NUCLEO_FW_BUILD_ID,csr);
 mic_boot_store(&r); /* Store evidence BEFORE removing sticky hardware flags. */
 RCC->CSR|=RCC_CSR_RMVF;__DSB();
 mb_confirm_clear(&r,RCC->CSR);mic_boot_store(&r);
}
void mic_boot_note_software_reset(uint32_t tag){
 mb_record r=mic_boot_read();
 if(mb_valid(&r,MIC_NUCLEO_FW_BUILD_ID)){mb_note_software(&r,tag);mic_boot_store(&r);}
}
void mic_boot_packet(uint8_t*packet,uint32_t now_ms){
 const mb_record r=mic_boot_read();mb_packet(packet,&r,now_ms);
}
