"""Prepare the cold-start UART update of the sealed LSO capture pair, offline."""
import json
import shutil

from prepare_air56_lso_uno_capture import OUT as BASE, ROOT, release, replace

OUT = BASE.with_name('air56_st_lso_uart_startup_r1')
OLD = (2026112301, 2026112302)
NEW = (2026112303, 2026112304)


def change(name, edit):
    source = (BASE/name).read_text(encoding='utf8')
    for old, new in zip(OLD, NEW):
        source = source.replace(str(old), str(new))
    (OUT/name).write_text(edit(source), encoding='utf8')


def nucleo(s):
    s = replace(s, 'bool AIR56_UnoOwnsStart(void)', '''static void air56_uput(uint8_t *p, uint32_t v, unsigned n);
#include "air56_uart_startup.inc"

bool AIR56_UnoOwnsStart(void)''')
    s = replace(s, '(air56_rx.link_seen ? 1 : 0)', '(air56_uart_qualified && air56_rx.link_seen ? 1 : 0)')
    s = replace(s, '    __DMB();\n    DMA1_Channel1->CNDTR = size;', '''    else if (!pwm && !air56_lso_trace.active)
    {
        air56_uart_decorate(p + UV3_FRAME);
        size += UV3_FRAME;
    }
    __DMB();
    DMA1_Channel1->CNDTR = size;''')
    s = replace(s, '    const bool no_pwm = !(TIM1->BDTR & TIM_BDTR_MOE);', '''    air56_uart_qualify_off(off && !air56_rx.fault_latched && !air56_estopped, seq);
    const bool no_pwm = !(TIM1->BDTR & TIM_BDTR_MOE);''')
    s = replace(s, 'air56_break_ready(), air56_off_seen && air56_rx.link_seen &&',
                'air56_break_ready(), air56_uart_qualified && air56_off_seen && air56_rx.link_seen &&')
    s = replace(s, '''static void air56_transport_fault(uint32_t now)
{
    air56_off_seen = false;
    if (air56_lso_trace.active)
    {
        LL_TIM_DisableAllOutputs(TIM1);
        Mci[M1].DirectCommand = MCI_NO_COMMAND;
        air56_capture_finish(AIR56_END_LINK, now);''', '''static void air56_transport_fault(uint32_t now)
{
    air56_off_seen = false;
    if (air56_lso_trace.active || (TIM1->BDTR & TIM_BDTR_MOE))
    {
        LL_TIM_DisableAllOutputs(TIM1);
        Mci[M1].DirectCommand = MCI_NO_COMMAND;
        if (air56_lso_trace.active) { air56_capture_finish(AIR56_END_LINK, now); }''')
    s = replace(s, '''        uv3_trip(&air56_rx, UV3_DROPPED);
        air56_transport_fault(now);''', '''        const uint32_t dma = DMA1->ISR;
        air56_uart_record(AIR56_UART_TX_BUSY | (dma & DMA_ISR_TEIF1 ? AIR56_UART_DMA_TX : 0U),
                          now, 0, USART1->ISR, dma, 0, UV3_DROPPED, false);
        uv3_trip(&air56_rx, UV3_DROPPED);
        air56_transport_fault(now);''')
    s = replace(s, '''        uv3_trip(&air56_rx, UV3_LINK_TIMEOUT);
        air56_transport_fault(now);''', '''        air56_uart_record(AIR56_UART_LEASE, now, elapsed, USART1->ISR,
                          DMA1->ISR, 0, UV3_LINK_TIMEOUT, false);
        uv3_trip(&air56_rx, UV3_LINK_TIMEOUT);
        air56_transport_fault(now);''')
    start = s.index('    const uint32_t errors = USART1->ISR', s.index('static void AIR56_UnoService(void)'))
    return s[:start] + '''    const uint32_t usart = USART1->ISR;
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
'''


def uno(s):
    s = replace(s, 'static bool g_lso_page_valid;', '''static bool g_lso_page_valid;
static uint8_t g_uart_startup[UV3_FRAME];
static uint32_t g_uart_startup_ms;
static bool g_uart_startup_seen;''')
    s = replace(s, '  s += " mc_lso_page_hex=";', '''  s += " mc_uart_startup_hex=";
  if (g_uart_startup_seen && g_bp_fw_build == 2026112304U &&
      (uint32_t)(millis()-g_bp_last_rsp_ms)<300U) {
    for (unsigned i=0;i<UV3_FRAME;++i) {
      s += break_hex[g_uart_startup[i]>>4];
      s += break_hex[g_uart_startup[i]&15];
    }
  } else s += "-";
  s += " mc_uart_startup_age_ms=";
  s += String((unsigned long)(g_uart_startup_seen ? millis()-g_uart_startup_ms : 999999U));
  s += " mc_lso_page_hex=";''')
    return replace(s, '      if (buf[2] == 0xB6) {', '''      if (buf[2] == 0xB7) {
        const uint32_t now = millis();
        if (g_bp_fw_build == 2026112304U && (uint32_t)(now-g_bp_last_rsp_ms)<300U &&
            buf[3] == 1 && xp_u32(buf+4)==g_bp_fw_build && uv3_crc_ok(buf)) {
          memcpy(g_uart_startup,buf,UV3_FRAME);
          g_uart_startup_ms=now;
          g_uart_startup_seen=true;
        }
        continue;
      }
      if (buf[2] == 0xB6) {''')


def web(s):
    s = replace(s, '                "mc_lso_page_hex": kv.get("mc_lso_page_hex", "-"),',
        '''                "mc_uart_startup_hex": kv.get("mc_uart_startup_hex", "-"),
                "mc_uart_startup_age_ms": int(kv.get("mc_uart_startup_age_ms","999999")),
                "mc_lso_page_hex": kv.get("mc_lso_page_hex", "-"),''')
    s = replace(s, 'def with_research_suite(data):', '''def decode_lso_uart_startup(data):
    try:
        raw = bytes.fromhex(data.get('mc_uart_startup_hex', '-'))
        if (len(raw) != 43 or raw[:4] != bytes((0x55, 0xAA, 0xB7, 1)) or
            not 0 <= data.get('mc_uart_startup_age_ms', 999999) < 300 or
            int.from_bytes(raw[4:8], 'little') != data.get('mc_fw_build') or
            crc32c(raw[:39]) != int.from_bytes(raw[39:], 'little')):
            return {'available': False}
    except (ValueError, TypeError):
        return {'available': False}
    names = ('USART', 'DMA_RX', 'DMA_TX', 'POLL_GAP', 'RX_BATCH', 'PARSER', 'TX_BUSY', 'LEASE')
    causes = lambda mask: [name for bit, name in enumerate(names) if mask & (1 << bit)]
    u = lambda offset, width=4: int.from_bytes(raw[offset:offset+width], 'little')
    flags = raw[10]
    return dict(available=True, qualified=bool(flags&1), waiting_for_quiet=bool(flags&2),
                first_in_cold_start=bool(flags&4), fault_latched=bool(flags&8),
                first_causes=causes(raw[8]), first_latched_causes=causes(raw[9]),
                last_causes=causes(raw[38]), first_pending_bytes=u(11,2), clean_off_frames=raw[13],
                first_tick_ms=u(14), first_elapsed_cycles=u(18), first_usart_isr=u(22),
                first_dma_isr=u(26), first_dma_remaining=u(30,2), cold_resyncs=u(32),
                first_parser_index=raw[36], first_parser_result=raw[37])


def with_research_suite(data):''')
    return replace(s, "    data['research_algorithms']=research_catalog(data)",
                   "    data['mc_uart_startup']=decode_lso_uart_startup(data)\n    data['research_algorithms']=research_catalog(data)")


def main():
    approved = release.base.read_json(BASE/'uno_capture_PC.json')
    assert approved['passed'] and approved['pair']==list(OLD)
    release.base.verify_inventory(approved['images_sha256'],BASE/'image')
    protected = release.base.read_json(BASE/'preserved_inputs_sha256.json')
    for subdir in ('hardware_install_r1','autonomous_preflight_r1','pre_battery_lso_5hz_r1'):
        for file in (BASE/subdir).rglob('*'):
            if file.is_file(): protected[file.relative_to(ROOT).as_posix()] = release.base.sha(file)
    release.base.verify_inventory(protected,ROOT)
    OUT.mkdir()
    for name in ('Drivers','Inc','MCSDK_v6.4.2-Full','Src','STM32CubeIDE','UNOQ_MOTOR','libraries','web_hmi'):
        shutil.copytree(BASE/name,OUT/name,ignore=shutil.ignore_patterns(
            'Debug','Release','__pycache__','*.pyc'))
    for name in ('ACIM-AIR56B2-LSO_FOC.ioc','generation.log','AIR56B2_profile.json'):
        shutil.copyfile(BASE/name,OUT/name)
    shutil.copyfile(ROOT/'tools/air56_uart_startup.inc',OUT/'Inc/air56_uart_startup.inc')
    change('Inc/air56_lso_uno.inc',nucleo)
    change('UNOQ_MOTOR/UNOQ_MOTOR.ino',uno)
    change('web_hmi/server.py',web)
    (OUT/'preserved_inputs_sha256.json').write_text(json.dumps(protected,indent=2)+'\n',encoding='utf8')
    print(OUT)


if __name__ == '__main__':
    main()
