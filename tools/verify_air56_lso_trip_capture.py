"""Verify the first-overcurrent record on the compiled Cortex-M4 image."""
import json
import struct
from hashlib import sha256

from unicorn import UC_HOOK_MEM_WRITE

import verify_air56_uart_startup as uart
from prepare_air56_lso_trip_capture import BASE, NEW, OUT, ROOT
from read_air56_lso_capture import decode_trip, page_data
from verify_air56_lso_timing_aspep import DWT, TIM1, Firmware, test_ccm_startup, test_uart
from verify_air56_lso_uno_capture import UnoExchange, test_uno


def verify_trip(elf):
    link = UnoExchange(elf, NEW[1])
    link.qualify_link_and_bus()
    assert link.start()
    link.emulate_running()
    fw, symbols = link.fw, link.s
    fw.cpu.mem_map(0x50000000, 0x1000)
    pwm = symbols['PWM_Handle_M1']
    fw.put(symbols['pwmcHandle'], pwm)
    fw.put(symbols['pACIM_LSO'], symbols['ACIM_LSO_Component_M1'])
    fw.put(symbols['ACIM_LSO_Component_M1'] + 36, symbols['FOCVars'])
    fw.call('ACIM_LSO_Init', symbols['ACIM_LSO_Component_M1'], symbols['BusVoltageSensor_M1'])
    fw.put(link.mc + 25, 4, 'B')  # START, avoiding unrelated speed-supervisor state.
    fw.put(pwm + 0x7a, 4, 'B')  # R3_2 reads phases U/V in sampling sector 5.
    for offset in (0x88, 0x8c, 0x90):
        fw.put(pwm + offset, 32768)
    fw.put(0x50000080, 32768 - 1582)
    fw.put(0x50000180, 32768 - 722)
    fw.put(TIM1 + 0x24, 4000)
    fw.put(TIM1 + 0x2c, 5312)
    for offset, value in zip((0x34, 0x38, 0x3c, 0x40), (2510, 2700, 2400, 5311)):
        fw.put(TIM1 + offset, value)
    seen = []

    def check_outputs(cpu, access, address, size, value, unused):
        seen.append(fw.get(TIM1 + 0x44) & 0x8000)

    address = symbols['air56_trip_record']
    fw.cpu.hook_add(UC_HOOK_MEM_WRITE, check_outputs, begin=address, end=address)
    fw.put(DWT, link.now * 170000 + 10625)
    fw.call('TSK_HighFrequencyTask')
    assert seen == [0] and fw.get(link.trace + 28) == 64
    raw = bytes(fw.cpu.mem_read(address, 64))
    start_ms = fw.get(link.trace + 12)
    snapshot = decode_trip(raw, start_ms)
    assert snapshot['jdr1'] == (31186, 32046)
    assert snapshot['phase_counts'] == (1582, 722, -2304)
    assert snapshot['phase_threshold_crossings'] == ['W']
    assert snapshot['timer_at_adc_read']['cnt'] == 4000
    assert snapshot['timer_at_fault_handler']['ccr'] == (2510, 2700, 2400, 5311)
    assert snapshot['sample_index'] == 1

    fw.put(0x50000080, 32768 - 1650)
    fw.call('TSK_HighFrequencyTask')
    assert bytes(fw.cpu.mem_read(address, 64)) == raw and seen == [0]
    link.send()
    assert fw.get(link.trace + 4) == 0 and fw.get(link.trace + 20) == 4
    fw.put(link.mc + 0x20, 0, 'H')  # The source is no longer active.
    fw.put(link.mc + 25, 11, 'B')  # FAULT_OVER allows the normal acknowledgement.
    assert link.send(0, 8)
    assert bytes(fw.cpu.mem_read(address, 64)) == raw
    parts = []
    for page in (257, 258):
        response = link.send(8, 0, struct.pack('<BBIBB', 7, 0, page, 1, 0xa6))
        parts.append(page_data(response[2], page, start_ms & 0xffff)[1])
    assert b''.join(parts) == raw
    return snapshot


def main():
    image = OUT / 'image'
    elf = image / 'ACIM-AIR56B2-LSO_FOC.elf'
    snapshot = verify_trip(elf)
    uart.NEW = NEW
    uart.prearm_errors(elf)
    uart.active_errors(elf)
    regression, _ = test_uno(elf, NEW[1])
    firmware = Firmware(elf)
    dwt, lso = firmware.off_dwt_fixture()
    assert len(dwt) == 64 and max(dwt) < 4000
    assert firmware.sym['_estack'] - firmware.sym['_ebss'] >= 3072
    ccm_size = test_ccm_startup(elf)
    aspep = test_uart(elf)
    for header in ('air56_st_lso_limits.h', 'uart_v3_transport.h', 'air56_lso_capture.h'):
        assert (OUT / 'Inc' / header).read_bytes() == (BASE / 'Inc' / header).read_bytes()
    preserved = json.loads((OUT / 'preserved_inputs_sha256.json').read_text(encoding='utf8'))
    for name, digest in preserved.items():
        assert sha256((ROOT / name).read_bytes()).hexdigest() == digest
    report = dict(passed=True, pair=NEW, hardware_commands=0, installed=False, trip_snapshot=snapshot,
                  regressions=regression, aspep=aspep, ccm_bytes=ccm_size, off_cases=len(dwt),
                  off_max_emulator_instructions=max(dwt), lso_max_emulator_instructions=max(lso),
                  clear_preserves_first_trip=True, actual_target_DWT_pending=True, preserved_files=len(preserved),
                  DWT_limit=4000, ADC_age_limit_us=2000,
                  web_hmi_sha256=sha256((OUT / 'web_hmi/server.py').read_bytes()).hexdigest(),
                  images_sha256={p.name: sha256(p.read_bytes()).hexdigest() for p in image.iterdir() if p.is_file()})
    (OUT / 'verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
