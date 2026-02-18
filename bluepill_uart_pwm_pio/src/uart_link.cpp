#include "uart_link.h"

#include <string.h>

#include "config.h"
#include "proto.h"
#include "stm32f1xx_hal.h"

static UART_HandleTypeDef *s_uart = NULL;
static uint8_t s_rx_buf[UART_RX_BUF_SIZE];
static volatile uint16_t s_rx_head = 0;
static volatile uint16_t s_rx_tail = 0;

static uint8_t s_parser_state = 0;
static uint8_t s_parser_idx = 0;
static uint8_t s_frame_buf[FRAME_LEN];

static inline uint16_t rb_next(uint16_t v) {
  return (uint16_t)((v + 1U) % UART_RX_BUF_SIZE);
}

static inline bool rb_empty(void) {
  return s_rx_head == s_rx_tail;
}

static inline bool rb_full(void) {
  return rb_next(s_rx_head) == s_rx_tail;
}

static void rb_push(uint8_t b) {
  if (rb_full()) {
    return;
  }
  s_rx_buf[s_rx_head] = b;
  s_rx_head = rb_next(s_rx_head);
}

static bool rb_pop(uint8_t *b) {
  if (rb_empty()) {
    return false;
  }
  *b = s_rx_buf[s_rx_tail];
  s_rx_tail = rb_next(s_rx_tail);
  return true;
}

void uart_link_init(UART_HandleTypeDef *huart) {
  s_uart = huart;
  s_rx_head = 0;
  s_rx_tail = 0;
  s_parser_state = 0;
  s_parser_idx = 0;

  __HAL_UART_ENABLE(s_uart);

  // Force-enable TX/RX and re-apply BRR in case HAL init was bypassed or
  // MSP init didn't run as expected.
  uint32_t pclk = HAL_RCC_GetPCLK1Freq();
  if (pclk != 0U) {
    s_uart->Instance->BRR = (pclk + (UART_BAUD / 2U)) / UART_BAUD;
  }
  s_uart->Instance->CR1 |= USART_CR1_TE | USART_CR1_RE | USART_CR1_UE;

  HAL_NVIC_SetPriority(USART2_IRQn, 1, 0);
  HAL_NVIC_EnableIRQ(USART2_IRQn);

  s_uart->Instance->CR1 |= USART_CR1_RXNEIE;
}

void uart_link_isr(void) {
  if (!s_uart) {
    return;
  }

  uint32_t sr = s_uart->Instance->SR;
  if (sr & (UART_FLAG_ORE | UART_FLAG_FE | UART_FLAG_NE | UART_FLAG_PE)) {
    volatile uint32_t tmp = s_uart->Instance->SR;
    volatile uint32_t tmp2 = s_uart->Instance->DR;
    (void)tmp;
    (void)tmp2;
  }

  if (sr & UART_FLAG_RXNE) {
    uint8_t b = (uint8_t)(s_uart->Instance->DR & 0xFFU);
    rb_push(b);
  }
}

int uart_link_poll_frame(uint8_t *frame, uint8_t *fault_code) {
  uint8_t b = 0;
  while (rb_pop(&b)) {
    switch (s_parser_state) {
      case 0:
        if (b == CMD_HDR0) {
          s_frame_buf[0] = b;
          s_parser_state = 1;
        }
        break;
      case 1:
        if (b == CMD_HDR1) {
          s_frame_buf[1] = b;
          s_parser_idx = 2;
          s_parser_state = 2;
        } else if (b == CMD_HDR0) {
          s_frame_buf[0] = b;
          s_parser_state = 1;
        } else {
          if (fault_code) *fault_code = FAULT_BAD_HDR;
          s_parser_state = 0;
          return -1;
        }
        break;
      case 2:
        s_frame_buf[s_parser_idx++] = b;
        if (s_parser_idx >= FRAME_LEN) {
          memcpy(frame, s_frame_buf, FRAME_LEN);
          s_parser_state = 0;
          s_parser_idx = 0;
          if (!proto_cmd_crc_ok(frame)) {
            if (fault_code) *fault_code = FAULT_BAD_CRC;
            return -2; // full frame, bad CRC
          }
          return 1;
        }
        break;
      default:
        s_parser_state = 0;
        s_parser_idx = 0;
        break;
    }
  }
  return 0;
}

void uart_link_send(const uint8_t *frame, uint16_t len) {
  if (!s_uart) return;
  for (uint16_t i = 0; i < len; ++i) {
    while (!(s_uart->Instance->SR & UART_FLAG_TXE)) {
    }
    s_uart->Instance->DR = frame[i];
  }
  while (!(s_uart->Instance->SR & UART_FLAG_TC)) {
  }
}
