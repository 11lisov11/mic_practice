"""Verify the compiled startup path and replay bounds from the stationary run."""
from hashlib import sha256
import json
import math
import struct

import verify_air56_lso_trip_capture as trip
import verify_air56_uart_startup as uart
from verify_air56_hmi_bounded_stop import load, replay_statuses, run_watchdog
from prepare_air56_lso_start_record import BASE, NEW, OUT, ROOT
from read_air56_lso_capture import HEADER, decode, decode_start, page_data
from verify_air56_lso_timing_aspep import DWT, Firmware, test_ccm_startup, test_uart
from verify_air56_lso_uno_capture import UnoExchange, test_uno

CAPTURE = ROOT / 'artifacts/live_bench_20261123/lso_2306_hmi_autostop_161006_230004/capture/capture.bin'


def startup_fixture(elf):
    link = UnoExchange(elf, NEW[1])
    link.qualify_link_and_bus()
    assert link.start()
    link.emulate_running()
    fw, s = link.fw, link.s
    foc, lso = s['FOCVars'], s['ACIM_LSO_Component_M1']
    fw.put(s['pACIM_LSO'], lso)
    fw.put(lso + 36, foc)
    fw.put(s['pSTC'], s['SpeednTorqCtrlM1'])
    fw.put(link.mc + 4, foc)
    fw.call('ACIM_LSO_Init', lso, s['BusVoltageSensor_M1'])
    fw.call('PID_HandleInit', s['PIDSpeedHandle_M1'])
    fw.call('STC_Init', s['SpeednTorqCtrlM1'], s['PIDSpeedHandle_M1'], lso)
    fw.put(link.mc + 25, 4, 'B')
    base = link.now

    def step(at_ms, id_counts):
        link.now = base + at_ms
        fw.put(s['uwTick'], link.now)
        fw.put(s['air56_last_packet_ms'], link.now)
        fw.put(DWT, link.now * 170000)
        fw.put(foc + 10, id_counts, 'h')
        fw.call('TSK_MediumFrequencyTaskM1')
        if at_ms % 40 == 0 and at_ms < 5000:
            fw.put(s['air56_uart_poll_cycles'], link.now * 170000)
            assert link.send(6, 1, struct.pack('<I', 5000))

    def frozen():
        fw.put(s['air56_uart_poll_cycles'], link.now * 170000)
        f = link.send()
        epoch, meta = page_data(f[2], 0)
        _, start, end, _, reason, *_ = HEADER.unpack(meta)
        pages = []
        for i in (259, 260):
            frame = link.send(8, 0, struct.pack('<BBIBB', 7, 0, i, 1, 0xa6))
            pages.append(page_data(frame[2], i, epoch)[1])
        return decode_start(b''.join(pages), start, end, reason)

    return link, step, frozen


def verify_start(elf, projected):
    link, step, frozen = startup_fixture(elf)
    for at_ms in range(2, 5000, 2):
        step(at_ms, projected[min(at_ms // 10, len(projected) - 1)])
        assert link.fw.get(link.mc + 25, 'B') == 4
    step(5000, 0)
    blocked = frozen()
    assert not blocked['entered_run'] and blocked['speed_target_hz'] == 5
    assert blocked['max_speed_ref_hz'] == 0 and blocked['magnetization']['max_streak'] == 0
    assert blocked['magnetization']['checks'] == 2499

    link, step, frozen = startup_fixture(elf)
    for index in range(9):
        step(2 * index + 2, 843)
    step(20, 589)
    for at_ms in range(22, 42, 2):
        step(at_ms, 843)
        assert link.fw.get(link.mc + 25, 'B') == 4
    step(42, 843)
    assert link.fw.get(link.mc + 25, 'B') == 6
    for at_ms in range(44, 5000, 2):
        step(at_ms, 843)
    step(5000, 843)
    reached = frozen()
    assert reached['entered_run'] and reached['magnetization']['max_streak'] == 10
    assert reached['speed_target_hz'] == reached['max_speed_ref_hz'] == 5
    assert reached['iq_ref_max_counts'] > 0 and reached['terminal_faults'] == 0
    return blocked, reached


def main():
    elf = OUT / 'image/ACIM-AIR56B2-LSO_FOC.elf'
    _, rows = decode(CAPTURE.read_bytes())
    projected = [math.isqrt((4 * (a*a + a*b + b*b)) // 3) for _, a, b, *_ in rows]
    blocked, reached = verify_start(elf, projected)
    trip.NEW = NEW
    trip.verify_trip(elf)
    uart.NEW = NEW
    uart.prearm_errors(elf)
    uart.active_errors(elf)
    guards, _ = test_uno(elf, NEW[1])
    firmware = Firmware(elf)
    dwt, _ = firmware.off_dwt_fixture()
    assert len(dwt) == 64 and max(dwt) < 4000
    stack_headroom = firmware.sym['_estack'] - firmware.sym['_ebss']
    assert stack_headroom >= 3072
    assert firmware.sym['_sccmram'] <= firmware.sym['air56_start_record']
    assert firmware.sym['air56_start_record'] + 64 <= firmware.sym['_eccmram']
    test_ccm_startup(elf)
    test_uart(elf)
    hmi = load('air56_start_record_hmi', OUT / 'web_hmi/server.py')
    before, running, complete = (dict(frame, fw_build=NEW[0], mc_fw_build=NEW[1]) for frame in replay_statuses())
    commands, messages, state = run_watchdog(hmi, before, running, [complete], [True, False])
    assert not commands and state['hmi_hv_armed'] == 0
    assert any('WIFI_BOUNDED_COMPLETE' in message for message in messages)
    for name in ('air56_st_lso_limits.h', 'air56_lso_capture.h', 'uart_v3_transport.h'):
        assert (OUT / 'Inc' / name).read_bytes() == (BASE / 'Inc' / name).read_bytes()
    preserved = json.loads((OUT / 'preserved_inputs_sha256.json').read_text(encoding='utf8'))
    for name, digest in preserved.items():
        assert sha256((ROOT / name).read_bytes()).hexdigest() == digest
    report = dict(passed=True,pair=NEW,hardware_commands=0,installed=False,
        measured_rotation_verified=False, replay_scope='ideal Clarke magnitude of 499 saved samples in integer current units',
        replay_max_possible_id_counts=max(projected), replay_below_band=blocked, commanded_run=reached,
        off_cases=len(dwt), off_max_emulator_instructions=max(dwt), actual_target_DWT_pending=True,
        stack_headroom_bytes=stack_headroom, hmi_bounded_stop_replayed=True,
        DWT_limit=4000,ADC_age_limit_us=2000,guards=guards,preserved_files=len(preserved),
        web_hmi_sha256=sha256((OUT/'web_hmi/server.py').read_bytes()).hexdigest(),
        images_sha256={p.name:sha256(p.read_bytes()).hexdigest() for p in (OUT/'image').iterdir()})
    (OUT / 'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
