#pragma once

#include <stdint.h>

#include "stm32f1xx_hal.h"

void uart_link_init(UART_HandleTypeDef *huart);
int uart_link_poll_frame(uint8_t *frame, uint8_t *fault_code);
bool uart_link_send(const uint8_t *frame, uint16_t len);
uint16_t uart_link_take_rx_error_count(void);
void uart_link_isr(void);
