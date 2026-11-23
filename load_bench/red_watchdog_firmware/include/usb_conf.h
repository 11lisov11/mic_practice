#ifndef MIC_RNR_USB_CONF_H
#define MIC_RNR_USB_CONF_H
#include "at32f403.h"
#include <stdint.h>
#include <stddef.h>
#define USB_EPT_MAX_NUM 8
#define EPT0_TX_ADDR 0x40
#define EPT0_RX_ADDR 0x80
#define EPT1_TX_ADDR 0xC0
#define EPT1_RX_ADDR 0x100
#define EPT2_TX_ADDR 0x140
#define EPT2_RX_ADDR 0x180
#define EPT3_TX_ADDR 0
#define EPT3_RX_ADDR 0
#define EPT4_TX_ADDR 0
#define EPT4_RX_ADDR 0
#define EPT5_TX_ADDR 0
#define EPT5_RX_ADDR 0
#define EPT6_TX_ADDR 0
#define EPT6_RX_ADDR 0
#define EPT7_TX_ADDR 0
#define EPT7_RX_ADDR 0
#ifdef __cplusplus
extern "C" {
#endif
void usb_delay_ms(uint32_t ms);
void usb_delay_us(uint32_t us);
#ifdef __cplusplus
}
#endif
#endif
