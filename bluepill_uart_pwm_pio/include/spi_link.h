#pragma once

#include <stdint.h>

#include "stm32f1xx_hal.h"

void spi_link_init(SPI_HandleTypeDef *hspi);
int spi_link_poll_frame(uint8_t *frame, uint8_t *fault_code);
void spi_link_send(const uint8_t *frame, uint16_t len);
uint32_t spi_link_rx_count(void);
