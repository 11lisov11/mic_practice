#pragma once

#include <stdint.h>

#include "stm32f1xx_hal.h"

void uart_link_init(UART_HandleTypeDef *huart);
int uart_link_poll_frame(uint8_t *frame, uint8_t *fault_code);
void uart_link_send(const uint8_t *frame, uint16_t len);
void uart_link_isr(void);
