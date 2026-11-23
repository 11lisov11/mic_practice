/* Included by mc_tasks.c: use its scheduler and MCSDK motor handle. */
#include "uart_v3_transport.h"
#include "sd_live_status.h"

enum {
    AIR56_UNO_BUILD = 2026112314U,
    AIR56_UNO_RING = 512U,
    AIR56_UNO_MASK = AIR56_UNO_RING - 1U,
    AIR56_UNO_RING_DEADLINE = 680000U,
    AIR56_PROFILE_ID = 0x5F6C4A02U,
    AIR56_SOFTSTART_MS = 3500U
};

static UART_HandleTypeDef air56_uart;
static uint8_t air56_uart_ring[AIR56_UNO_RING];
static uint8_t air56_uart_reply[3U * UV3_FRAME];
static uv3_rx air56_rx;
static uint16_t air56_uart_tail, air56_good, air56_bad;
static uint32_t air56_uart_poll_cycles, air56_bus_since;
static bool air56_bus_stable, air56_bus_timing, air56_start_context;
static bool air56_off_seen, air56_clear_seen, air56_estopped, air56_uart_polled;
static uint16_t air56_page;

static void air56_uput(uint8_t *p, uint32_t v, unsigned n);
#include "air56_uart_startup.inc"

bool AIR56_UnoOwnsStart(void) { return air56_start_context; }

void AIR56_UnoInit(void)
{
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_USART1_CLK_ENABLE();
    __HAL_RCC_DMA1_CLK_ENABLE();
    GPIO_InitTypeDef pins = {
        .Pin = GPIO_PIN_6 | GPIO_PIN_7, .Mode = GPIO_MODE_AF_PP,
        .Pull = GPIO_PULLUP, .Speed = GPIO_SPEED_FREQ_LOW, .Alternate = GPIO_AF7_USART1
    };
    HAL_GPIO_Init(GPIOB, &pins);
    air56_uart.Instance = USART1;
    air56_uart.Init = (UART_InitTypeDef){
        .BaudRate = 921600, .WordLength = UART_WORDLENGTH_8B, .StopBits = UART_STOPBITS_1,
        .Parity = UART_PARITY_NONE, .Mode = UART_MODE_TX_RX, .HwFlowCtl = UART_HWCONTROL_NONE,
        .OverSampling = UART_OVERSAMPLING_16, .OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE,
        .ClockPrescaler = UART_PRESCALER_DIV1
    };
    if (HAL_UART_Init(&air56_uart) != HAL_OK || HAL_UARTEx_EnableFifoMode(&air56_uart) != HAL_OK)
    {
        Error_Handler();
    }
    uv3_init(&air56_rx, false);
    DMA1_Channel1->CCR = 0;
    DMA1_Channel2->CCR = 0;
    DMA1->IFCR = 0xFFU;
    DMAMUX1_Channel0->CCR = DMA_REQUEST_USART1_TX;
    DMAMUX1_Channel1->CCR = DMA_REQUEST_USART1_RX;
    DMA1_Channel1->CPAR = (uint32_t)(uintptr_t)&USART1->TDR;
    DMA1_Channel1->CMAR = (uint32_t)(uintptr_t)air56_uart_reply;
    DMA1_Channel2->CPAR = (uint32_t)(uintptr_t)&USART1->RDR;
    DMA1_Channel2->CMAR = (uint32_t)(uintptr_t)air56_uart_ring;
    DMA1_Channel2->CNDTR = AIR56_UNO_RING;
    DMA1_Channel2->CCR = DMA_CCR_MINC | DMA_CCR_CIRC | DMA_CCR_EN;
    USART1->ICR = USART_ICR_ORECF | USART_ICR_NECF | USART_ICR_FECF | USART_ICR_PECF;
    USART1->CR3 |= USART_CR3_DMAR | USART_CR3_DMAT;
    air56_uart_poll_cycles = DWT->CYCCNT;
}

static bool air56_break_config(void)
{
    const uint32_t limits = TIM1->BDTR;
    return (limits & (TIM_BDTR_BKE | TIM_BDTR_BKF | TIM_BDTR_AOE)) ==
               (TIM_BDTR_BKE | (9U << TIM_BDTR_BKF_Pos)) &&
           (TIM1->AF1 & (TIM1_AF1_BKINE | TIM1_AF1_BKINP)) ==
               (TIM1_AF1_BKINE | TIM1_AF1_BKINP);
}

static bool air56_break_ready(void)
{
    return air56_break_config() && (GPIOA->IDR & GPIO_PIN_6) &&
           (TIM1->DIER & TIM_DIER_BIE) && !(TIM1->SR & TIM_SR_BIF);
}

static void air56_uput(uint8_t *p, uint32_t v, unsigned n)
{
    for (unsigned i = 0; i < n; ++i) { p[i] = (uint8_t)(v >> (8U * i)); }
}

static uint32_t air56_frequency(const uint8_t *p)
{
    return (uint32_t)p[6] | (uint32_t)p[7] << 8 |
           (uint32_t)p[8] << 16 | (uint32_t)p[9] << 24;
}

static bool air56_reply(uint8_t seq, uint8_t mode, uint16_t volts)
{
    if (DMA1_Channel1->CNDTR != 0U || (DMA1->ISR & DMA_ISR_TEIF1))
    {
        return false;
    }
    DMA1_Channel1->CCR = 0;
    DMA1->IFCR = 0x0FU;

    const uint16_t current = MCI_GetCurrentFaults(&Mci[M1]);
    const uint16_t occurred = MCI_GetOccurredFaults(&Mci[M1]);
    const bool fault = current || occurred || air56_rx.fault_latched || air56_estopped;
    const bool pwm = (TIM1->BDTR & TIM_BDTR_MOE) != 0U;
    uint8_t *p = air56_uart_reply;
    memset(p, 0, sizeof(air56_uart_reply));
    p[0] = 0x55;
    p[1] = 0xAA;
    p[2] = UV3_VERSION;
    p[3] = (air56_uart_qualified && air56_rx.link_seen ? 1 : 0) | (air56_lso_trace.active && !fault ? 2 : 0) |
           (air56_estopped ? 4 : 0) | (fault ? 8 : 0) |
           (air56_rx.fault == UV3_LINK_TIMEOUT ? 16 : 0) | (pwm ? 0x60 : 0);
    p[4] = seq;
    air56_uput(p + 5, air56_good, 2);
    air56_uput(p + 7, air56_bad, 2);
    p[9] = fault ? (air56_estopped ? 3 : air56_rx.fault_latched ? 2 : 5) : 0;
    p[10] = mode;
    p[11] = fault ? 0x91 : 0xA0;
    if (!fault && air56_lso_trace.active)
    {
        const int16_t ref = STC_GetMecSpeedRefUnit(pSTC[M1]);
        air56_uput(p + 12, ref > 0 ? (uint16_t)(ref * 10) : 0U, 2);
    }
    if (fault) { p[13] = (uint8_t)Mci[M1].State; }
    air56_uput(p + 15, current, 2);
    air56_uput(p + 17, volts * 10U, 2);
    air56_uput(p + 19, (uint16_t)(NTC_GetAvTemp_C(&TempSensor_M1) * 10), 2);
    p[21] = 1U | ((current & MC_OVER_TEMP) ? 2U : 0U) |
            sd_live_encode((GPIOA->IDR & GPIO_PIN_6) != 0U, (TIM1->DIER & TIM_DIER_BIE) != 0U,
                           false, false, air56_break_config());
    air56_uput(p + 23, AIR56_UNO_BUILD, 4);
    air56_uput(p + 27, occurred, 2);
    p[29] = 0xD0 | (air56_bus_stable ? 0x20 : 0);
    uv3_reply_diagnostics(p, &air56_rx);
    uv3_seal(p);

    p += UV3_FRAME;
    p[0] = 0x55;
    p[1] = 0xAA;
    p[2] = 0xE4;
    p[3] = 4;
    p[4] = 2; /* FOC only */
    p[5] = 2; /* LSO uses the existing bounded FOC route */
    air56_uput(p + 6, AIR56_UNO_BUILD, 4);
    air56_uput(p + 10, 16000, 4);
    p[14] = 128; /* calculated, not identified */
    p[15] = AIR56_OffDwtReady();
    p[16] = fault ? 1 : 0;
    p[18] = 1;
    const ACIM_LSO_Handle_t *observer = pACIM_LSO[M1];
    if (observer && pwm && !fault && Mci[M1].State == RUN)
    {
        const float rpm = observer->fRotorSpeed_RPM;
        uint32_t serialized;
        memcpy(&serialized, &rpm, sizeof(serialized));
        if ((serialized & 0x7f800000U) != 0x7f800000U)
        {
            p[17] = 1;
            air56_uput(p + 27, serialized, sizeof(serialized));
        }
    }
    air56_uput(p + 19, air56_lso_trace.fast_max && air56_lso_trace.magic ?
              air56_lso_trace.fast_max : air56_off_dwt.max_cycles, 4);
    air56_uput(p + 23, air56_off_dwt.max_lso_cycles, 4);
    p[31] = air56_lso_trace.active != 0U;
    air56_uput(p + 32, AIR56_PROFILE_ID, 4);
    p[36] = (AIR56_OffDwtReady() ? 1U : 0U) | (air56_lso_trace.active ? 2U : 0U) |
            (air56_lso_trace.magic && !air56_lso_trace.active ? 4U : 0U);
    p[37] = air56_off_dwt.failures || (air56_lso_trace.magic &&
            air56_lso_trace.fast_max > AIR56_LSO_FAST_CYCLES) ? 1U : 0U;
    p[38] = (uint8_t)air56_off_dwt.cases_done;
    uv3_seal(p);
    uint32_t size = 2U * UV3_FRAME;
    const bool trip_page = air56_trip_saved && (air56_page == 257U || air56_page == 258U);
    const bool start_page = air56_start_record.magic == AIR56_START_RECORD_MAGIC &&
                            (air56_page == 259U || air56_page == 260U);
    const bool start_q_page = air56_start_q.magic == AIR56_START_Q_MAGIC && air56_page == 262U;
    const bool field_page = air56_first_field_fault.magic == AIR56_FIELD_MAGIC && air56_page == 261U;
    if (!pwm && air56_lso_trace.magic && !air56_lso_trace.active &&
        air56_lso_trace.reason && (start_q_page || field_page || start_page || trip_page || air56_page <= (air56_lso_trace.rows + 1U) / 2U))
    {
        p += UV3_FRAME;
        p[0] = 0x55;
        p[1] = 0xAA;
        p[2] = 0xB6;
        air56_uput(p + 3, air56_page, 2);
        air56_uput(p + 5, air56_lso_trace.start_ms, 2);
        if (start_q_page)
        {
            memcpy(p + 7, &air56_start_q, sizeof(air56_start_q));
        }
        else if (field_page)
        {
            memcpy(p + 7, &air56_first_field_fault, sizeof(air56_first_field_fault));
        }
        else if (start_page)
        {
            const uint8_t *raw = (const uint8_t *)&air56_start_record;
            const unsigned offset = 32U * (air56_page - 259U);
            for (unsigned i = 0; i < 32U; ++i) { p[7 + i] = raw[offset + i]; }
        }
        else if (trip_page)
        {
            const unsigned first = 8U * (air56_page - 257U);
            for (unsigned i = 0; i < 8U; ++i) { air56_uput(p + 7 + 4 * i, air56_trip_record[first + i], 4); }
        }
        else if (!air56_page)
        {
            const uint32_t meta[8] = {air56_lso_trace.magic, air56_lso_trace.start_ms,
                air56_lso_trace.end_ms, air56_lso_trace.rows, air56_lso_trace.reason,
                air56_lso_trace.fast_max, air56_lso_trace.first_fault, air56_lso_trace.injected_samples};
            for (unsigned i = 0; i < 8; ++i) { air56_uput(p + 7 + 4 * i, meta[i], 4); }
        }
        else
        {
            const unsigned first = 2U * (air56_page - 1U);
            const volatile uint8_t *raw = (const volatile uint8_t *)&air56_lso_trace.windows[first];
            const unsigned bytes = first + 1U < air56_lso_trace.rows ? 32U : 16U;
            for (unsigned i = 0; i < bytes; ++i) { p[7 + i] = raw[i]; }
        }
        uv3_seal(p);
        size += UV3_FRAME;
    }
    else if (!pwm && !air56_lso_trace.active)
    {
        air56_uart_decorate(p + UV3_FRAME);
        size += UV3_FRAME;
    }
    __DMB();
    DMA1_Channel1->CNDTR = size;
    DMA1_Channel1->CCR = DMA_CCR_DIR | DMA_CCR_MINC | DMA_CCR_EN;
    return true;
}

static void air56_transport_fault(uint32_t now)
{
    air56_off_seen = false;
    if (air56_lso_trace.active || (TIM1->BDTR & TIM_BDTR_MOE))
    {
        LL_TIM_DisableAllOutputs(TIM1);
        Mci[M1].DirectCommand = MCI_NO_COMMAND;
        if (air56_lso_trace.active) { air56_capture_finish(AIR56_END_LINK, now); }
        air56_run_started = false;
        MCI_FaultProcessing(&Mci[M1], MC_SW_ERROR, 0);
    }
}

static void air56_uno_message(uint32_t now, uint16_t bus)
{
    uint8_t *p = air56_rx.frame;
    const uint8_t flags = p[3], mode = p[4], seq = p[5];
    const bool off = mode == 0 && flags == 0;
    const bool clear = mode == 0 && flags == 8;
    const bool stop_now = (flags & 2U) != 0;
    const bool select = mode == 8 && flags == 0 && p[6] == 3 && p[7] == 2 &&
                        p[8] == 0 && p[9] == 0 && p[10] == 0 && p[11] == 0 &&
                        p[12] == 1 && p[13] == 0xA6;
    const unsigned page_index = p[8] | (unsigned)p[9] << 8;
    const bool page = mode == 8 && (flags == 0 || flags == 2U) && p[6] == 7 && p[7] == 0 &&
                      page_index <= 262U &&
                      p[10] == 0 && p[11] == 0 && p[12] == 1 && p[13] == 0xA6;
    const bool drive = flags == 1 && mode == 6 && air56_frequency(p) == 5000U;
    bool valid = off || clear || stop_now || select || drive || page;
    for (unsigned i = 14; i < UV3_PAYLOAD; ++i) { if (p[i]) { valid = false; } }
    if (stop_now)
    {
        air56_estopped = true;
        LL_TIM_DisableAllOutputs(TIM1);
        if (air56_lso_trace.active)
        {
            air56_capture_finish(AIR56_END_ESTOP, now);
            TSK_MF_StopProcessing(M1);
            air56_run_started = false;
        }
        air56_off_seen = false;
    }
    if (!valid)
    {
        if (air56_bad < UINT16_MAX) { ++air56_bad; }
        uv3_trip(&air56_rx, UV3_BAD_VERSION);
        air56_transport_fault(now);
        (void)air56_reply(seq, mode, bus);
        return;
    }
    air56_uart_qualify_off(off && !air56_rx.fault_latched && !air56_estopped, seq);
    const bool no_pwm = !(TIM1->BDTR & TIM_BDTR_MOE);
    if (page && no_pwm && !air56_lso_trace.active)
    {
        air56_page = (uint16_t)page_index;
    }
    const bool no_current = MCI_GetCurrentFaults(&Mci[M1]) == MC_NO_FAULTS;
    const bool without_fault = no_current && MCI_GetOccurredFaults(&Mci[M1]) == MC_NO_FAULTS;
    bool clear_transport = false;
    if (clear && !air56_clear_seen && no_pwm && no_current && air56_break_ready() &&
        (Mci[M1].State == IDLE || Mci[M1].State == FAULT_OVER) && !air56_lso_trace.active)
    {
        air56_estopped = false;
        clear_transport = true;
        if (Mci[M1].State == FAULT_OVER) { (void)MCI_FaultAcknowledged(&Mci[M1]); }
        air56_bad = 0;
    }
    air56_clear_seen = clear;
    if (off && air56_lso_trace.active)
    {
        LL_TIM_DisableAllOutputs(TIM1);
        air56_capture_finish(AIR56_END_OFF, now);
        TSK_MF_StopProcessing(M1);
        Mci[M1].DirectCommand = MCI_NO_COMMAND;
        air56_run_started = false;
    }
    if (drive && !air56_lso_trace.active && !air56_estopped &&
        air56_trial_allowed(AIR56_OffDwtReady() && no_pwm && without_fault && air56_bus_stable,
                           air56_break_ready(), air56_uart_qualified && air56_off_seen && air56_rx.link_seen &&
                           !air56_rx.fault_latched, air56_rx.clean_run_frames,
                           air56_frequency(p), &air56_lso_trace) &&
        Mci[M1].State == IDLE && Mci[M1].DirectCommand == MCI_NO_COMMAND)
    {
        MCI_ExecSpeedRamp(&Mci[M1], 50, 1000); /* 0.1 Hz mechanical units, one pole pair */
        air56_start_context = true;
        bool accepted = MCI_StartMotor(&Mci[M1]);
        air56_start_context = false;
        if (accepted) { air56_capture_begin(now); }
    }
    if (off || select) { air56_off_seen = true; }
    else if (drive || stop_now) { air56_off_seen = false; }
    uv3_commit(&air56_rx, now, air56_lso_trace.active != 0U, air56_estopped, clear_transport);
    if ((drive && air56_lso_trace.active) || off || select || clear)
    {
        air56_last_packet_ms = now;
    }
    if (air56_good < UINT16_MAX) { ++air56_good; }
    if (!air56_reply(seq, mode, bus))
    {
        const uint32_t dma = DMA1->ISR;
        air56_uart_record(AIR56_UART_TX_BUSY | (dma & DMA_ISR_TEIF1 ? AIR56_UART_DMA_TX : 0U),
                          now, 0, USART1->ISR, dma, 0, UV3_DROPPED, false);
        uv3_trip(&air56_rx, UV3_DROPPED);
        air56_transport_fault(now);
    }
}

static void AIR56_UnoService(void)
{
    const uint32_t now = HAL_GetTick();
    const uint32_t cycles = DWT->CYCCNT;
    const uint16_t head = (uint16_t)((AIR56_UNO_RING - DMA1_Channel2->CNDTR) & AIR56_UNO_MASK);
    if (!air56_uart_polled)
    {
        air56_uart_poll_cycles = cycles;
        air56_uart_tail = head;
        air56_uart_polled = true;
        return;
    }
    const uint32_t elapsed = cycles - air56_uart_poll_cycles;
    air56_uart_poll_cycles = cycles;
    const uint16_t bus = VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super);
    const bool in_bus_range = bus >= 250U && bus <= 350U;
    if (!in_bus_range)
    {
        air56_bus_timing = air56_bus_stable = false;
    }
    else if (!air56_bus_timing)
    {
        air56_bus_since = now;
        air56_bus_timing = true;
    }
    else if (now - air56_bus_since >= AIR56_SOFTSTART_MS)
    {
        air56_bus_stable = true;
    }

    uint8_t stop_causes = 0;
    if (air56_lso_trace.active)
    {
        if (MCI_GetCurrentFaults(&Mci[M1])) { stop_causes |= 1U; }
        if (MCI_GetOccurredFaults(&Mci[M1])) { stop_causes |= 2U; }
        if (!air56_break_config()) { stop_causes |= 4U; }
        if (!(GPIOA->IDR & GPIO_PIN_6)) { stop_causes |= 8U; }
        if (!(TIM1->DIER & TIM_DIER_BIE)) { stop_causes |= 16U; }
        if (TIM1->SR & TIM_SR_BIF) { stop_causes |= 32U; }
        if (!in_bus_range) { stop_causes |= 64U; }
    }
    if (stop_causes)
    {
        LL_TIM_DisableAllOutputs(TIM1);
        Mci[M1].DirectCommand = MCI_NO_COMMAND;
        air56_start_record.reserved = stop_causes;
        air56_capture_finish(AIR56_END_FAULT, now);
        air56_run_started = false;
        if (MCI_GetCurrentFaults(&Mci[M1]) == MC_NO_FAULTS)
        {
            MCI_FaultProcessing(&Mci[M1], MC_SW_ERROR, 0);
        }
    }
    else if (air56_lso_trace.active && (Mci[M1].State == STOP ||
        (Mci[M1].State == IDLE && Mci[M1].DirectCommand != MCI_START)))
    {
        air56_capture_finish(AIR56_END_OFF, now);
        air56_run_started = false;
    }
    if (air56_lso_trace.active &&
        air56_lso_stale(now, air56_last_packet_ms, AIR56_LSO_LINK_MS))
    {
        air56_uart_record(AIR56_UART_LEASE, now, elapsed, USART1->ISR,
                          DMA1->ISR, 0, UV3_LINK_TIMEOUT, false);
        uv3_trip(&air56_rx, UV3_LINK_TIMEOUT);
        air56_transport_fault(now);
    }
    const uint32_t usart = USART1->ISR;
    const uint32_t dma = DMA1->ISR;
    const uint16_t count = (head - air56_uart_tail) & AIR56_UNO_MASK;
    const unsigned causes = air56_uart_causes(usart, dma, elapsed, count);
    bool cold = air56_cold_safe();
    if (causes)
    {
        USART1->ICR = usart & (USART_ISR_PE | USART_ISR_FE | USART_ISR_NE | USART_ISR_ORE);
        const bool recover = cold && !(causes & (AIR56_UART_DMA_RX | AIR56_UART_DMA_TX));
        air56_uart_record(causes, now, elapsed, usart, dma, count, UV3_HARD_UART, recover);
        air56_uart_tail = head;
        if (!recover)
        {
            uv3_trip(&air56_rx, UV3_HARD_UART);
            air56_transport_fault(now);
        }
        return;
    }
    if (air56_uart_seeking_quiet)
    {
        air56_uart_tail = head;
        if (count) { air56_quiet_since = cycles; }
        else if (cycles - air56_quiet_since >= AIR56_UART_QUIET_CYCLES)
        {
            air56_uart_seeking_quiet = false;
        }
        return;
    }
    const uv3_result deadline = uv3_tick(&air56_rx, now);
    if (deadline != UV3_WAIT)
    {
        air56_uart_record(deadline == UV3_LINK_TIMEOUT ? AIR56_UART_LEASE : AIR56_UART_PARSER,
                          now, elapsed, usart, dma, count, deadline, cold);
        if (!cold)
        {
            air56_uart_tail = head;
            air56_transport_fault(now);
        }
        return;
    }
    __DMB();
    for (uint16_t i = 0; i < count; ++i)
    {
        const uint8_t value = ((volatile uint8_t *)air56_uart_ring)[air56_uart_tail];
        air56_uart_tail = (air56_uart_tail + 1U) & AIR56_UNO_MASK;
        uv3_result parsed = uv3_byte(&air56_rx, value, 0, now);
        if (parsed == UV3_READY)
        {
            const uint32_t after_usart = USART1->ISR;
            const uint32_t after_dma = DMA1->ISR;
            const uint32_t spent = DWT->CYCCNT - cycles;
            const unsigned late = air56_uart_causes(after_usart, after_dma, spent, 0);
            if (late)
            {
                USART1->ICR = after_usart & (USART_ISR_PE | USART_ISR_FE | USART_ISR_NE | USART_ISR_ORE);
                const bool recover = cold && !(late & (AIR56_UART_DMA_RX | AIR56_UART_DMA_TX));
                air56_uart_record(late, now, spent, after_usart, after_dma, count, UV3_HARD_UART, recover);
                if (!recover)
                {
                    uv3_trip(&air56_rx, UV3_HARD_UART);
                    air56_transport_fault(now);
                }
                return;
            }
            air56_uno_message(now, bus);
            cold = air56_cold_safe();
        }
        else if (parsed != UV3_WAIT)
        {
            air56_uart_record(AIR56_UART_PARSER, now, elapsed, usart, dma, count, parsed, cold);
            if (!cold)
            {
                if (air56_bad < UINT16_MAX) { ++air56_bad; }
                air56_transport_fault(now);
            }
            return;
        }
    }
}
