#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "stm32g4xx_hal.h"

void uart_link_init(UART_HandleTypeDef *huart);
int uart_link_poll_frame(uint8_t *frame, uint8_t *fault_code);
bool uart_link_send(const uint8_t *data, uint16_t length);
uint16_t uart_link_take_rx_error_count(void);
