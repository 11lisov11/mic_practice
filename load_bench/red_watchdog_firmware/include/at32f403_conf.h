#ifndef MIC_AT32F403_CONF_H
#define MIC_AT32F403_CONF_H
#define HICK_VALUE ((uint32_t)8000000)
#define LEXT_VALUE ((uint32_t)32768)
#define HEXT_STARTUP_TIMEOUT ((uint16_t)0x3000)
#define CRM_MODULE_ENABLED
#define GPIO_MODULE_ENABLED
#define MISC_MODULE_ENABLED
#define USB_MODULE_ENABLED
#define WDT_MODULE_ENABLED
#include "at32f403_crm.h"
#include "at32f403_gpio.h"
#include "at32f403_misc.h"
#include "at32f403_usb.h"
#include "at32f403_wdt.h"
#endif
