#include "spi_link.h"

#include <string.h>

#include "config.h"
#include "proto.h"
#include "stm32f1xx_hal.h"

static SPI_HandleTypeDef *s_spi = nullptr;
static uint8_t s_rx_buf[FRAME_LEN];
static uint8_t s_tx_buf[FRAME_LEN];
static uint8_t s_frame_buf[FRAME_LEN];
static volatile bool s_frame_ready = false;
static volatile uint32_t s_txrx_cnt = 0;

static void spi_arm(void) {
  if (!s_spi) {
    return;
  }
  (void)HAL_SPI_TransmitReceive_IT(s_spi, s_tx_buf, s_rx_buf, FRAME_LEN);
}

void spi_link_init(SPI_HandleTypeDef *hspi) {
  s_spi = hspi;
  s_frame_ready = false;
  s_txrx_cnt = 0;
  memset(s_rx_buf, 0, sizeof(s_rx_buf));
  memset(s_tx_buf, 0, sizeof(s_tx_buf));
  memset(s_frame_buf, 0, sizeof(s_frame_buf));
  __HAL_SPI_ENABLE(s_spi);
  // With SSM enabled (SPI_NSS_SOFT), SSI becomes "internal NSS".
  // Keep it low so the slave always accepts clocks.
#if defined(SPI_CR1_SSI)
  CLEAR_BIT(s_spi->Instance->CR1, SPI_CR1_SSI);
#endif
  HAL_NVIC_SetPriority(SPI1_IRQn, 1, 0);
  HAL_NVIC_EnableIRQ(SPI1_IRQn);
  spi_arm();
}

int spi_link_poll_frame(uint8_t *frame, uint8_t *fault_code) {
  if (!s_frame_ready) {
    return 0;
  }
  __disable_irq();
  s_frame_ready = false;
  memcpy(frame, s_frame_buf, FRAME_LEN);
  __enable_irq();

  if (frame[CMD_OFF_HDR0] != CMD_HDR0 || frame[CMD_OFF_HDR1] != CMD_HDR1) {
    if (fault_code) *fault_code = FAULT_BAD_HDR;
    return -1;
  }
  if (!proto_cmd_crc_ok(frame)) {
    if (fault_code) *fault_code = FAULT_BAD_CRC;
    return -2;
  }
  return 1;
}

void spi_link_send(const uint8_t *frame, uint16_t len) {
  if (!frame || len == 0) {
    return;
  }
  if (len > FRAME_LEN) len = FRAME_LEN;
  __disable_irq();
  memcpy(s_tx_buf, frame, len);
  __enable_irq();
}

uint32_t spi_link_rx_count(void) {
  return s_txrx_cnt;
}

extern "C" void HAL_SPI_TxRxCpltCallback(SPI_HandleTypeDef *hspi) {
  if (hspi != s_spi) {
    return;
  }
  memcpy(s_frame_buf, s_rx_buf, FRAME_LEN);
  s_frame_ready = true;
  s_txrx_cnt++;
  spi_arm();
}

extern "C" void HAL_SPI_ErrorCallback(SPI_HandleTypeDef *hspi) {
  if (hspi != s_spi) {
    return;
  }
  spi_arm();
}
