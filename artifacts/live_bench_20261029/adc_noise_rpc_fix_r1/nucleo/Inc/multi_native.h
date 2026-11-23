#ifndef MIC_MA_NATIVE_H
#define MIC_MA_NATIVE_H
#include <stdint.h>
/* Offset-corrected ADC COUNTS, not amperes or milliamperes. Reconstruction and
 * acceptance belong to the original ADC IRQ; scaling belongs to the consumer. */
typedef struct {uint32_t sequence,cycles,epoch;int16_t counts[3];uint8_t valid,zero;uint16_t ccr[3],arr,bus_v;} ma_current_sample;
int mic_current_fast(ma_current_sample*out);
void ma_native_service(void);
void ma_native_profile_tick(void);
uint16_t ma_native_fast(float reference_hz);
int ma_native_request(unsigned algorithm);
int ma_native_prepare(void);
int ma_native_config(const uint8_t*frame);
unsigned ma_native_selected(void);
int ma_native_complete(void);
void ma_id_status(uint8_t*,uint32_t);
int ma_id_page(uint8_t*,uint32_t,unsigned);
void ma_native_diag(uint8_t*packet,uint32_t build);
#endif
