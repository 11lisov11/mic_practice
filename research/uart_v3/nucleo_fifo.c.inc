static uv3_rx uno_transport;
enum { UNO_RX_SIZE = 128U, UNO_RX_MASK = UNO_RX_SIZE - 1U };
static volatile uint8_t uno_rx_bytes[UNO_RX_SIZE];
static volatile uint8_t uno_rx_marks[UNO_RX_SIZE];
static volatile uint16_t uno_rx_head;
static volatile uint16_t uno_rx_tail;
static volatile uint8_t uno_rx_errors;
static volatile uint8_t uno_rx_overflow;

static bool uno_rx_push(uint8_t byte, uint8_t flags) {
  const uint16_t next = (uno_rx_head + 1U) & UNO_RX_MASK;
  if (next == uno_rx_tail) return false;
  uno_rx_bytes[uno_rx_head] = byte;
  uno_rx_marks[uno_rx_head] = flags;
  uno_rx_head = next;
  return true;
}

static bool uno_rx_pop(uint8_t *byte, uint8_t *flags) {
  if (uno_rx_tail == uno_rx_head) return false;
  *byte = uno_rx_bytes[uno_rx_tail];
  *flags = uno_rx_marks[uno_rx_tail];
  uno_rx_tail = (uno_rx_tail + 1U) & UNO_RX_MASK;
  return true;
}

/* Hardware FIFO is disabled: one ISR snapshot and one RDR read form a
   sample. An NE without an available byte is not eligible for tolerance. */
void USART1_IRQHandler(void) {
  for (;;) {
    const uint32_t status = huart1.Instance->ISR;
    const uint32_t errors = status & (UART_FLAG_ORE | UART_FLAG_NE | UART_FLAG_FE | UART_FLAG_PE);
    const uint8_t marks =
        ((errors & UART_FLAG_PE) != 0U ? (uint8_t)UV3_PE : 0U) |
        ((errors & UART_FLAG_FE) != 0U ? (uint8_t)UV3_FE : 0U) |
        ((errors & UART_FLAG_NE) != 0U ? (uint8_t)UV3_NE : 0U) |
        ((errors & UART_FLAG_ORE) != 0U ? (uint8_t)UV3_ORE : 0U);
    if ((errors & UART_FLAG_ORE) != 0U) __HAL_UART_CLEAR_OREFLAG(&huart1);
    if ((errors & UART_FLAG_NE) != 0U) __HAL_UART_CLEAR_NEFLAG(&huart1);
    if ((errors & UART_FLAG_FE) != 0U) __HAL_UART_CLEAR_FEFLAG(&huart1);
    if ((errors & UART_FLAG_PE) != 0U) __HAL_UART_CLEAR_PEFLAG(&huart1);
    if ((marks & (UV3_PE | UV3_FE | UV3_ORE)) != 0U) uno_rx_errors |= marks;
    if ((status & UART_FLAG_RXNE) == 0U) {
      if ((marks & UV3_NE) != 0U) uno_rx_errors |= marks;
      break;
    }
    const uint8_t byte = (uint8_t)huart1.Instance->RDR;
    if (uno_rx_errors == 0U && uno_rx_overflow == 0U && !uno_rx_push(byte, marks)) uno_rx_overflow = 1U;
  }
}
