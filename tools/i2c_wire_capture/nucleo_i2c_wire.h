#ifndef MIC_NUCLEO_I2C_WIRE_H
#define MIC_NUCLEO_I2C_WIRE_H
#include <stdint.h>
#include <stdbool.h>
void mic_i2c_wire_init(void);
void mic_i2c_wire_freeze(const uint32_t*,uint32_t);
void mic_i2c_wire_service(bool);
bool mic_i2c_wire_packet(uint8_t*,unsigned);
/* Debugger-only OFF/low-bus qualification. Never a motor command. */
extern volatile uint32_t mic_i2c_wire_request;
#endif
