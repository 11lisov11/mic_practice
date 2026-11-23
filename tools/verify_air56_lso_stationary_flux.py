"""Verify the compiled stationary-flux startup without commands to the bench."""
from hashlib import sha256
import json
import math
import struct
import sys

import verify_air56_lso_start_record as startup
import verify_air56_lso_trip_capture as trip
import verify_air56_uart_startup as uart
from prepare_air56_lso_stationary_flux import BASE, NEW, OUT, ROOT
from read_air56_lso_capture import AMP, decode, decode_start, page_data
from verify_air56_hmi_bounded_stop import load, replay_statuses, run_watchdog
from verify_air56_lso_timing_aspep import DWT, TIM1, Firmware, test_ccm_startup, test_uart
from verify_air56_lso_uno_capture import GPIOA, UnoExchange, test_uno

sys.path.insert(0, str(ROOT))
from motor_identification.model import MotorParameters, MotorState, _step

ELF = OUT / 'image/ACIM-AIR56B2-LSO_FOC.elf'
CAPTURE = OUT.parent / 'lso_2308_start_5hz_164125_579756/capture'


def recorded_low_current():
    record = json.loads((CAPTURE / 'start_diagnostic.json').read_text(encoding='utf8'))
    assert record['magnetization']['checks'] == 729 and not record['entered_run']
    _, rows = decode((CAPTURE / 'capture.bin').read_bytes())
    link, step, frozen = startup.startup_fixture(ELF)
    for ms in range(2, 5000, 2):
        row = rows[min(ms // 10, len(rows) - 1)]
        a, b = row[1:3]
        id_counts = round(-(a + 2 * b) / math.sqrt(3))
        step(ms, id_counts)
        assert link.fw.get(link.mc + 25, 'B') == 4
    step(5000, 0)
    assert not frozen()['entered_run']
    return record['magnetization']


def qualified_start():
    link, step, frozen = startup.startup_fixture(ELF)
    fw, s = link.fw, link.s
    for ms in range(2, 22, 2):
        step(ms, 843)
        assert fw.get(link.mc + 25, 'B') == 4
    assert fw.get(s['air56_start_flux_A'], 'f') < 590 * AMP
    step(22, 589)
    assert fw.get(s['bACIM_MagnValidCount'], 'B') == 0
    for ms in range(24, 5000, 2):
        step(ms, 843)
        if fw.get(link.mc + 25, 'B') == 6:
            entered = ms
            break
    else:
        raise AssertionError('Qualified current failed to enter RUN')
    lso = s['ACIM_LSO_Component_M1']
    actual = fw.get(s['air56_start_flux_A'], 'f')
    assert 590 * AMP <= actual <= 1095 * AMP
    assert math.isclose(actual, fw.get(lso + 68, 'f'), abs_tol=1e-7)
    for ms in range(entered + 2, 4998, 2):
        step(ms, 843)
    fw.put(lso + 88, 296.0, 'f')
    fw.put(s['air56_uart_poll_cycles'], link.now * 170000)
    reply = link.send(6, 1, struct.pack('<I', 5000))
    assert reply[0][11] == 0xa0 and int.from_bytes(reply[0][12:14], 'little') == 500
    assert reply[1][17] == 1 and struct.unpack_from('<f', reply[1], 27) == (296.0,)
    step(5000, 843)
    result = frozen()
    assert result['entered_run'] and result['magnetization']['max_streak'] == 10
    assert result['speed_target_hz'] == result['max_speed_ref_hz'] == 5
    assert result['iq_ref_max_counts'] > 0 and result['terminal_faults'] == 0
    return dict(handoff_ms=entered, handoff_flux_equivalent_A=actual, result=result)


def model_closed_loop():
    link, step, frozen = startup.startup_fixture(ELF)
    fw, s = link.fw, link.s
    fw.cpu.mem_map(0x50000000, 0x1000)
    pwm, foc, lso = s['PWM_Handle_M1'], s['FOCVars'], s['ACIM_LSO_Component_M1']
    fw.put(s['pwmcHandle'], pwm)
    for suffix in ('Iq', 'Id'):
        fw.call('PID_HandleInit', s[f'PID{suffix}Handle_M1'])
    for offset in (0x88, 0x8c, 0x90):
        fw.put(pwm + offset, 32768)
    fw.put(TIM1 + 0x2c, 5312)
    # A stale observer angle cannot steer the stationary current loop.
    fw.put(lso + 80, 8192, 'h')
    fw.put(foc + 28, -1, 'h')
    profile = json.loads((OUT / 'AIR56B2_profile.json').read_text(encoding='utf8'))['motor']
    plant = MotorParameters(profile['Rs'], profile['Rr'], profile['Lls'], 1.5 * profile['Lms'],
                            profile['inertia'] / 1e6, profile['friction'] / 1e6,
                            profile['polesPairs'], 1.35, .01)
    state = MotorState()
    alpha = beta = peak = 0.0
    vscale = 320 / (math.sqrt(3) * 32767)
    entered = None
    checkpoints = []
    for tick in range(1, 80001):
        # The board samples U and V at the carrier centre in this test. MCSDK's
        # Clarke transform uses the opposite beta sign to the plant coordinates.
        fw.put(pwm + 0x7a, 4, 'B')
        fw.put(0x50000080, 32768 - round(alpha / AMP))
        fw.put(0x50000180, 32768 - round((-.5 * alpha + math.sqrt(3) * .5 * beta) / AMP))
        fw.put(DWT, link.now * 170000 + tick * 10625 % 170000)
        fw.call('TSK_HighFrequencyTask')
        if tick == 1:
            assert fw.get(foc + 28, 'h') == 0 and fw.get(lso + 80, 'h') == 8192
            fw.put(lso + 80, 0, 'h')
        if entered is None:
            assert fw.get(foc + 28, 'h') == 0
        assert fw.get(TIM1 + 0x44) & 0x8000, tick
        va, vb = (fw.get(foc + offset, 'h') * vscale for offset in (22, 24))
        state, alpha, beta = _step(plant, state, va, -vb, 0.0, 1 / 16000, False)
        peak = max(peak, math.hypot(alpha, beta))
        if tick % 32 == 0:
            step(tick // 16, fw.get(foc + 10, 'h'))
            if entered is None and fw.get(link.mc + 25, 'B') == 6:
                entered = tick // 16
                flux = fw.get(s['air56_start_flux_A'], 'f')
            if tick % 16000 == 0:
                checkpoints.append(dict(time_ms=tick // 16, simulated_rpm=state.omega_m * 60 / math.tau,
                                        observer_rpm=fw.get(lso + 88, 'f')))
    assert entered is not None and 590 * AMP <= flux <= 1095 * AMP
    assert peak < .8 and all(285 <= value['simulated_rpm'] <= 315 for value in checkpoints[1:])
    assert not fw.get(TIM1 + 0x44) & 0x8000
    result = frozen()
    assert result['stop_reason'] == 1 and result['terminal_faults'] == 0
    return dict(handoff_ms=entered, simulated_peak_A=peak, handoff_flux_equivalent_A=flux,
                speed_checkpoints=checkpoints, stop_ms=5000, scope='calculated unloaded motor, averaged voltage')


def stop_causes():
    cases = ('sd_low', 'break_irq_disabled', 'break_flag', 'bus_out_of_range')
    for cause in cases:
        link = UnoExchange(ELF, NEW[1])
        link.qualify_link_and_bus()
        assert link.start()
        link.emulate_running()
        fw = link.fw
        if cause == 'sd_low':
            fw.put(GPIOA + 0x10, 0)
        if cause == 'break_irq_disabled':
            fw.put(TIM1 + 0x0c, 0)
        if cause == 'break_flag':
            fw.put(TIM1 + 0x10, 0x80)
        if cause == 'bus_out_of_range':
            link.set_vbus(240)
        link.poll()
        assert not fw.get(TIM1 + 0x44) & 0x8000
        address = link.s['air56_start_record']
        raw = bytes(fw.cpu.mem_read(address, 64))
        start = fw.get(link.trace + 12)
        end = fw.get(link.trace + 16)
        assert decode_start(raw, start, end, 4)['motor_guard_causes'] == [cause]
        parts = []
        for index in (259, 260):
            reply = link.send(8, 0, struct.pack('<BBIBB', 7, 0, index, 1, 0xa6))
            parts.append(page_data(reply[2], index, start & 0xffff)[1])
        assert b''.join(parts) == raw
    return cases


def main():
    startup.NEW = trip.NEW = uart.NEW = NEW
    replay = recorded_low_current()
    qualified = qualified_start()
    plant = model_closed_loop()
    causes = stop_causes()
    trip.verify_trip(ELF)
    uart.prearm_errors(ELF)
    uart.active_errors(ELF)
    guards, _ = test_uno(ELF, NEW[1])
    firmware = Firmware(ELF)
    dwt, _ = firmware.off_dwt_fixture()
    stack = firmware.sym['_estack'] - firmware.sym['_ebss']
    assert len(dwt) == 64 and max(dwt) < 4000 and stack >= 3072
    test_ccm_startup(ELF)
    test_uart(ELF)
    hmi_path = OUT / 'web_hmi/server.py'
    hmi = load('air56_stationary_flux_hmi', hmi_path)
    before, running, complete = (dict(frame, fw_build=NEW[0], mc_fw_build=NEW[1]) for frame in replay_statuses())
    commands, messages, state = run_watchdog(hmi, before, running, [complete], [True, False])
    assert not commands and state['hmi_hv_armed'] == 0
    assert any('WIFI_BOUNDED_COMPLETE' in message for message in messages)
    for header in ('air56_st_lso_limits.h', 'air56_lso_capture.h', 'uart_v3_transport.h', 'drive_parameters.h'):
        assert (OUT / 'Inc' / header).read_bytes() == (BASE / 'Inc' / header).read_bytes()
    preserved = json.loads((OUT / 'preserved_inputs_sha256.json').read_text(encoding='utf8'))
    for name, digest in preserved.items():
        assert sha256((ROOT / name).read_bytes()).hexdigest() == digest
    report = dict(passed=True, pair=NEW, hardware_commands=0, installed=False,
                  measured_rotation_verified=False, saved_run_magnetization=replay,
                  qualified_start=qualified, closed_loop_plant=plant, guard_causes=causes,
                  off_cases=len(dwt), off_max_emulator_instructions=max(dwt), actual_target_DWT_pending=True,
                  stack_headroom_bytes=stack, DWT_limit=4000, ADC_age_limit_us=2000, guards=guards,
                  preserved_files=len(preserved), web_hmi_sha256=sha256(hmi_path.read_bytes()).hexdigest(),
                  images_sha256={p.name: sha256(p.read_bytes()).hexdigest() for p in (OUT / 'image').iterdir()})
    (OUT / 'verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
