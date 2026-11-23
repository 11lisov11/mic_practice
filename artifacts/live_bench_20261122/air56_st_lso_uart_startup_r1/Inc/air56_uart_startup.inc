/* Keep boot recovery separate from the operational UART and motor guards. */
enum {
    AIR56_UART_USART = 1U, AIR56_UART_DMA_RX = 2U, AIR56_UART_DMA_TX = 4U,
    AIR56_UART_POLL_GAP = 8U, AIR56_UART_BATCH = 16U, AIR56_UART_PARSER = 32U,
    AIR56_UART_TX_BUSY = 64U, AIR56_UART_LEASE = 128U,
    AIR56_UART_QUIET_CYCLES = 170000U,
    AIR56_UART_WIRE = 0xB7U
};

typedef struct {
    uint32_t kind, tick_ms, elapsed_cycles, usart_isr, dma_isr;
    uint16_t pending, dma_remaining;
    uint8_t rx_index, parser_result, cold, reserved;
} air56_uart_event;

static struct {
    air56_uart_event first, first_fatal;
    uint32_t cold_resyncs;
    uint8_t last_kind;
} air56_uart_diag;
static uint32_t air56_quiet_since;
static uint8_t air56_clean_off, air56_off_seq;
static bool air56_uart_qualified, air56_uart_seeking_quiet;

static bool air56_cold_safe(void)
{
    return !air56_uart_qualified && !air56_uart_diag.first_fatal.kind &&
           !air56_rx.fault_latched &&
           !air56_estopped && !air56_lso_trace.active && !air56_run_started &&
           !(TIM1->BDTR & TIM_BDTR_MOE) && Mci[M1].DirectCommand != MCI_START &&
           Mci[M1].State != START && Mci[M1].State != RUN;
}

static unsigned air56_uart_causes(uint32_t usart, uint32_t dma,
                                 uint32_t elapsed, uint16_t count)
{
    unsigned causes = 0;
    if (usart & (USART_ISR_PE | USART_ISR_FE | USART_ISR_NE | USART_ISR_ORE))
    {
        causes |= AIR56_UART_USART;
    }
    if (dma & DMA_ISR_TEIF2) { causes |= AIR56_UART_DMA_RX; }
    if (dma & DMA_ISR_TEIF1) { causes |= AIR56_UART_DMA_TX; }
    if (elapsed >= AIR56_UNO_RING_DEADLINE) { causes |= AIR56_UART_POLL_GAP; }
    if (count > UV3_FRAME) { causes |= AIR56_UART_BATCH; }
    return causes;
}

static void air56_uart_record(unsigned kind, uint32_t now, uint32_t elapsed,
                              uint32_t usart, uint32_t dma, uint16_t count,
                              uv3_result result, bool recover)
{
    const air56_uart_event event = {
        .kind = kind, .tick_ms = now, .elapsed_cycles = elapsed, .usart_isr = usart,
        .dma_isr = dma, .pending = count, .dma_remaining = (uint16_t)DMA1_Channel2->CNDTR,
        .rx_index = air56_rx.index, .parser_result = result, .cold = !air56_uart_qualified
    };
    if (!air56_uart_diag.first.kind) { air56_uart_diag.first = event; }
    if (!recover && !air56_uart_diag.first_fatal.kind) { air56_uart_diag.first_fatal = event; }
    air56_uart_diag.last_kind = (uint8_t)kind;
    if (!recover) { return; }

    if (air56_uart_diag.cold_resyncs != UINT32_MAX) { ++air56_uart_diag.cold_resyncs; }
    // Discard the entire ambiguous burst, including any partial parser state.
    // UART/DMA continue to receive but provide no command before the quiet gap.
    uv3_init(&air56_rx, false);
    air56_clean_off = 0;
    air56_off_seen = false;
    air56_uart_seeking_quiet = true;
    air56_quiet_since = DWT->CYCCNT;
    air56_uart_tail = (uint16_t)((AIR56_UNO_RING - DMA1_Channel2->CNDTR) & AIR56_UNO_MASK);
}

static void air56_uart_qualify_off(bool off, uint8_t seq)
{
    if (air56_uart_qualified) { return; }
    if (!off) { air56_clean_off = 0; return; }
    if (air56_clean_off && seq != (uint8_t)(air56_off_seq + 1U))
    {
        air56_clean_off = 0;
    }
    air56_off_seq = seq;
    if (++air56_clean_off == UV3_CLEAN_REQUIRED) { air56_uart_qualified = true; }
}

static void air56_uart_decorate(uint8_t *p)
{
    const air56_uart_event *event = &air56_uart_diag.first;
    p[0] = 0x55;
    p[1] = 0xAA;
    p[2] = AIR56_UART_WIRE;
    p[3] = 1;
    air56_uput(p + 4, AIR56_UNO_BUILD, 4);
    p[8] = (uint8_t)event->kind;
    p[9] = (uint8_t)air56_uart_diag.first_fatal.kind;
    p[10] = (air56_uart_qualified ? 1U : 0U) | (air56_uart_seeking_quiet ? 2U : 0U) |
            (event->cold ? 4U : 0U) | (air56_rx.fault_latched ? 8U : 0U);
    air56_uput(p + 11, event->pending, 2);
    p[13] = air56_clean_off;
    air56_uput(p + 14, event->tick_ms, 4);
    air56_uput(p + 18, event->elapsed_cycles, 4);
    air56_uput(p + 22, event->usart_isr, 4);
    air56_uput(p + 26, event->dma_isr, 4);
    air56_uput(p + 30, event->dma_remaining, 2);
    air56_uput(p + 32, air56_uart_diag.cold_resyncs, 4);
    p[36] = event->rx_index;
    p[37] = event->parser_result;
    p[38] = air56_uart_diag.last_kind;
    uv3_seal(p);
}
