#include "uart_link.h"

#include <string.h>

#include "config.h"
#include "proto.h"

static UART_HandleTypeDef *s_uart = nullptr;
static uint8_t s_rx_byte = 0;
static uint8_t s_rx_buffer[UART_RX_BUF_SIZE];
static volatile uint16_t s_rx_head = 0;
static volatile uint16_t s_rx_tail = 0;
static volatile uint16_t s_rx_error_count = 0;
static volatile bool s_resync_required = false;

static uint8_t s_parser_state = 0;
static uint8_t s_parser_index = 0;
static uint8_t s_frame[FRAME_LEN];

static uint16_t next_index(uint16_t value) {
  return (uint16_t)((value + 1U) % UART_RX_BUF_SIZE);
}

static void note_rx_error(void) {
  if (s_rx_error_count != UINT16_MAX) {
    ++s_rx_error_count;
  }
}
static void push_byte(uint8_t value) {
  const uint16_t next = next_index(s_rx_head);
  if (next == s_rx_tail) {
    s_rx_tail = s_rx_head;
    s_resync_required = true;
    note_rx_error();
    return;
  }
  s_rx_buffer[s_rx_head] = value;
  s_rx_head = next;
}

static bool pop_byte(uint8_t *value) {
  if (s_rx_head == s_rx_tail) {
    return false;
  }
  *value = s_rx_buffer[s_rx_tail];
  s_rx_tail = next_index(s_rx_tail);
  return true;
}

static void reset_parser(void) {
  s_parser_state = 0;
  s_parser_index = 0;
}

static void restart_receive(void) {
  if (s_uart != nullptr) {
    (void)HAL_UART_Receive_IT(s_uart, &s_rx_byte, 1U);
  }
}

void uart_link_init(UART_HandleTypeDef *huart) {
  s_uart = huart;
  s_rx_head = 0;
  s_rx_tail = 0;
  s_rx_error_count = 0;
  s_resync_required = false;
  reset_parser();
  restart_receive();
}

int uart_link_poll_frame(uint8_t *frame, uint8_t *fault_code) {
  if (s_resync_required) {
    const uint32_t primask = __get_PRIMASK();
    __disable_irq();
    s_rx_tail = s_rx_head;
    s_resync_required = false;
    if (primask == 0U) __enable_irq();
    reset_parser();
  }

  uint8_t byte = 0;
  while (pop_byte(&byte)) {
    if (s_parser_state == 0U) {
      if (byte == CMD_HDR0) {
        s_frame[0] = byte;
        s_parser_state = 1U;
      }
      continue;
    }

    if (s_parser_state == 1U) {
      if (byte == CMD_HDR1) {
        s_frame[1] = byte;
        s_parser_index = 2U;
        s_parser_state = 2U;
      } else if (byte == CMD_HDR0) {
        s_frame[0] = byte;
      } else {
        reset_parser();
        if (fault_code != nullptr) *fault_code = FAULT_BAD_HDR;
        return -1;
      }
      continue;
    }

    s_frame[s_parser_index++] = byte;
    if (s_parser_index >= FRAME_LEN) {
      memcpy(frame, s_frame, FRAME_LEN);
      reset_parser();
      if (!proto_cmd_crc_ok(frame)) {
        if (fault_code != nullptr) *fault_code = FAULT_BAD_CRC;
        return -2;
      }
      return 1;
    }
  }
  return 0;
}

bool uart_link_send(const uint8_t *data, uint16_t length) {
  return s_uart != nullptr && data != nullptr &&
         HAL_UART_Transmit(s_uart, const_cast<uint8_t *>(data), length, UART_TX_TIMEOUT_MS) == HAL_OK;
}

uint16_t uart_link_take_rx_error_count(void) {
  const uint32_t primask = __get_PRIMASK();
  __disable_irq();
  const uint16_t count = s_rx_error_count;
  s_rx_error_count = 0;
  if (primask == 0U) __enable_irq();
  return count;
}

extern "C" void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart) {
  if (huart == s_uart) {
    push_byte(s_rx_byte);
    restart_receive();
  }
}

extern "C" void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart) {
  if (huart == s_uart) {
    s_rx_tail = s_rx_head;
    s_resync_required = true;
    note_rx_error();
    restart_receive();
  }
}
