"""Replay the recorded START transition and validate the compiled LSO images."""
from hashlib import sha256
import json
import math
import struct

import verify_air56_lso_field_guard as field
import verify_air56_lso_start_record as startup
import verify_air56_lso_stationary_flux as flux
import verify_air56_lso_trip_capture as trip
import verify_air56_uart_startup as uart
from prepare_air56_lso_run_handoff import BASE, NEW, OLD, OUT, ROOT
from read_air56_lso_capture import AMP, decode, decode_start_q, page_data
from verify_air56_hmi_bounded_stop import load, replay_statuses, run_watchdog
from verify_air56_lso_timing_aspep import DWT, TIM1, Firmware, test_ccm_startup, test_uart
from verify_air56_lso_uno_capture import test_uno

NAME = 'ACIM-AIR56B2-LSO_FOC.elf'
ELF = OUT / 'image' / NAME
OLD_ELF = BASE / 'image' / NAME
CAPTURE = OUT.parent / 'lso_2312_5hz_221818_172581/capture'


def q_controller(issued_error):
    def output(elf):
        fw = Firmware(elf)
        reg = fw.sym['PIDIqHandle_M1']
        fw.call('PID_HandleInit', reg)
        raw = fw.call('PI_Controller', reg, issued_error & 0xffffffff)
        return struct.unpack('<h', struct.pack('<H', raw & 0xffff))[0]

    before, after = output(OLD_ELF), output(ELF)
    expected_integral = 1048 * issued_error >> 15
    assert before == (22328 * issued_error >> 11) + expected_integral
    assert after == (22328 * issued_error >> 13) + expected_integral
    return dict(error_counts=issued_error, old_output_counts=before, corrected_output_counts=after,
                old_kp_divisor=2048, corrected_kp_divisor=8192)


def replay_handoff(record, rows):
    magnetization = record['magnetization']
    end_iq = magnetization['last_iq_counts']
    end_id = magnetization['id_counts']['last']
    assert end_iq == 1816 and end_id == 701 and magnetization['iq_ref_counts'] == 0
    assert record['run_enter_ms'] - record['start_ms'] == 116
    samples = [(tick / 170000, ia, round(-(ia + 2 * ib) / math.sqrt(3)))
               for tick, ia, ib, *_ in rows if tick / 170000 < 116]
    samples.append((116, end_iq, end_id))
    assert len(samples) == 11

    def run_fixture(elf, pair, new):
        startup.NEW = pair
        link, step, frozen = startup.startup_fixture(elf)
        fw, s = link.fw, link.s
        foc = s['FOCVars']
        if new:
            fw.put(s['air56_start_q'], 0x3151534c)
            fw.put(s['air56_start_q'] + 4, fw.get(link.trace + 12))
        entered = None
        for ms in range(2, 202, 2):
            _, iq, id_ = next((point for point in reversed(samples) if point[0] <= ms), (0, 0, 0))
            fw.put(foc + 8, iq, 'h')
            if new:
                raw = struct.pack('<4hIHxx', iq, id_, -3000, 1050, 0x88997788, 4)
                fw.cpu.mem_write(s['air56_start_latest'], raw)
            step(ms, id_)
            if fw.get(link.mc + 25, 'B') == 6:
                entered = ms
                break
        return entered, link, step, frozen

    before, *_ = run_fixture(OLD_ELF, OLD, False)
    assert before is not None
    after, link, step, frozen = run_fixture(ELF, NEW, True)
    assert after is None
    fw = link.fw
    sym = link.s
    # A 134-count Q sample still blocks the handoff even with valid Id and flux.
    for ms in range(202, 222, 2):
        fw.put(sym['air56_start_latest'], 134, 'h')
        fw.put(sym['air56_start_latest'] + 2, 843, 'h')
        step(ms, 843)
        assert fw.get(link.mc + 25, 'B') == 4
    # Ten consecutive samples on the safe side of the limit then qualify.
    fw.put(sym['air56_start_latest'], 133, 'h')
    for ms in range(222, 240, 2):
        step(ms, 843)
        assert fw.get(link.mc + 25, 'B') == 4
    step(240, 843)
    assert fw.get(link.mc + 25, 'B') == 6
    estimator = sym['ACIM_LSO_Component_M1']
    assert math.isclose(fw.get(estimator + 56, 'f'), 133 * AMP, abs_tol=1e-6)
    for ms in range(242, 5002, 2):
        step(ms, 843)
    report = frozen()
    assert report['entered_run'] and report['max_speed_ref_hz'] == 5
    assert report['stop_reason'] == 1 and report['terminal_faults'] == 0
    start = fw.get(link.trace + 12)
    fw.put(sym['air56_uart_poll_cycles'], link.now * 170000)
    frame = link.send(8, 2, struct.pack('<BBIBB', 7, 0, 262, 1, 0xa6))
    assert frame[0][3] & 4 and not fw.get(TIM1 + 0x44) & 0x8000
    record_q = decode_start_q(page_data(frame[2], 262, start & 0xffff)[1],
                              start, report['magnetization']['checks'])
    assert record_q['iq_limit_counts'] == 133 and record_q['iq_peak_counts'] >= 1816
    assert record_q['iq_blocked_checks'] > 10
    assert record_q['adc_jdr_pair'] == [0x7788, 0x8899]
    assert record_q['vq_at_peak_command_counts'] == -3000
    return dict(old_replay_entered_run_at_ms=before, new_replay_blocked=True,
                qualified_after_recovery_ms=240, record=record_q)


def main():
    record = json.loads((CAPTURE / 'start_diagnostic.json').read_text(encoding='utf8'))
    previous_fault = json.loads((CAPTURE / 'field_fault.json').read_text(encoding='utf8'))
    assert previous_fault['reason'] == 'rotor_rate' and previous_fault['reference_hz'] == 0
    saved, rows = decode((CAPTURE / 'capture.bin').read_bytes())
    assert saved['elapsed_ms'] == 132 and saved['first_fault'] == 0x20
    transfer = replay_handoff(record, rows)
    pi = q_controller(-record['magnetization']['last_iq_counts'])
    flux.ELF, flux.OUT, flux.NEW = ELF, OUT, NEW
    field.ELF, field.OUT, field.NEW = ELF, OUT, NEW
    startup.NEW = trip.NEW = uart.NEW = NEW
    closed_loop = flux.model_closed_loop()
    field_cases = field.host_guard_cases()
    field_export = field.firmware_fault_and_export()
    guards, _ = test_uno(ELF, NEW[1])
    trip.verify_trip(ELF)
    uart.prearm_errors(ELF)
    uart.active_errors(ELF)
    test_uart(ELF)
    firmware = Firmware(ELF)
    dwt, _ = firmware.off_dwt_fixture()
    stack = firmware.sym['_estack'] - firmware.sym['_ebss']
    assert len(dwt) == 64 and max(dwt) < 4000 and stack >= 3072
    test_ccm_startup(ELF)
    hmi_path = OUT / 'web_hmi/server.py'
    hmi = load('air56_handoff_hmi', hmi_path)
    before, running, complete = (dict(frame, fw_build=NEW[0], mc_fw_build=NEW[1]) for frame in replay_statuses())
    commands, messages, state = run_watchdog(hmi, before, running, [complete], [True, False])
    assert not commands and state['hmi_hv_armed'] == 0
    assert any('WIFI_BOUNDED_COMPLETE' in message for message in messages)
    for name in ('air56_st_lso_limits.h', 'air56_lso_capture.h', 'air56_lso_field_guard.h',
                 'uart_v3_transport.h', 'drive_parameters.h'):
        assert (OUT / 'Inc' / name).read_bytes() == (BASE / 'Inc' / name).read_bytes()
    preserved = json.loads((OUT / 'preserved_inputs_sha256.json').read_text(encoding='utf8'))
    for name, digest in preserved.items():
        assert sha256((ROOT / name).read_bytes()).hexdigest() == digest
    report = dict(passed=True, pair=NEW, hardware_commands=0, installed=False,
                  replay_scope='saved 10 ms current samples held to the next row, plus exact START handoff sample',
                  first_fault_on_bench=previous_fault, torque_pi=pi, run_handoff=transfer,
                  closed_loop_plant=closed_loop, field_cases=field_cases, first_fault_export_with_estop=field_export,
                  off_cases=len(dwt), off_max_emulator_instructions=max(dwt), actual_target_DWT_pending=True,
                  stack_headroom_bytes=stack, DWT_limit=4000, ADC_age_limit_us=2000, guards=guards,
                  preserved_files=len(preserved), web_hmi_sha256=sha256(hmi_path.read_bytes()).hexdigest(),
                  images_sha256={p.name: sha256(p.read_bytes()).hexdigest() for p in (OUT / 'image').iterdir()})
    (OUT / 'verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: report[key] for key in ('passed','torque_pi','run_handoff','closed_loop_plant',
                                                   'off_max_emulator_instructions','preserved_files')}))


if __name__ == '__main__':
    main()
