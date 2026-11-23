#ifndef MIC_BOOT_DIAG_H
#define MIC_BOOT_DIAG_H
#include <stdint.h>
void mic_boot_capture_early(void);
void mic_boot_note_software_reset(uint32_t tag);
void mic_boot_packet(uint8_t *packet,uint32_t now_ms);
#endif
