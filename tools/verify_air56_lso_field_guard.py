"""Verify the slip guard, frozen E-stop export, and motor model on the PC."""
from hashlib import sha256
import json
import math
import shutil
import struct
import subprocess

from unicorn import UC_HOOK_CODE

import verify_air56_lso_start_record as startup
import verify_air56_lso_stationary_flux as flux
import verify_air56_lso_trip_capture as trip
import verify_air56_uart_startup as uart
from prepare_air56_lso_field_guard import BASE, NEW, OUT, ROOT
from read_air56_lso_capture import HEADER, decode_field_fault, page_data
from verify_air56_hmi_bounded_stop import load, replay_statuses, run_watchdog
from verify_air56_lso_timing_aspep import DWT, TIM1, Firmware, test_ccm_startup, test_uart
from verify_air56_lso_uno_capture import test_uno

ELF = OUT / 'image/ACIM-AIR56B2-LSO_FOC.elf'


def host_guard_cases():
    source = OUT / 'guard_cases.c'
    source.write_text(r'''
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdint.h>
typedef struct { int16_t q, d; } qd_t;
#include "drive_parameters.h"
#include "acim_motor_parameters.h"
#define TF_REGULATION_RATE (PWM_FREQUENCY / REGULATION_EXECUTION_RATE)
#include "air56_lso_field_guard.h"

static unsigned run(float field, float rotor, float ref, int iq, int command, int flux)
{
    air56_field_guard state = { .flux_counts = (float)flux };
    air56_field_fault fault = {0};
    const qd_t current = { .q = iq, .d = flux };
    for (unsigned i = 0; i < AIR56_FIELD_WINDOW - 1; ++i) {
        assert(!air56_field_check(&state, current, command, ref, field * AIR56_FIELD_RAD_PER_TURN,
                                  rotor * AIR56_FIELD_RAD_PER_TURN, &fault));
    }
    unsigned result = air56_field_check(&state, current, command, ref, field * AIR56_FIELD_RAD_PER_TURN,
                                        rotor * AIR56_FIELD_RAD_PER_TURN, &fault);
    assert(state.frames == 0);
    if (result) {
        assert(fault.reason == result && fault.samples == AIR56_FIELD_WINDOW);
        assert(fabsf(fault.field_hz - field) < 0.001f);
    }
    return result;
}

int main(void)
{
    const float slip = 500.0f / (TAU_R * AIR56_FIELD_RAD_PER_TURN * 843.0f);
    // The old check would reject both of the first two real-slip cases.
    assert(0 == run(.8f + slip, .8f, 1, 500, 600, 843));
    assert(0 == run(.8f + slip, .8f, 1, 600, 500, 843));
    assert(0 == run(.6f, .4f, 1, 0, 0, 843));
    assert(AIR56_FIELD_ROTOR_RATE == run(1, 2, 1, 0, 0, 843));
    assert(AIR56_FIELD_ROTOR_RATE == run(2 + slip, 2, 1, 500, 600, 843));
    assert(AIR56_FIELD_NO_SLIP_EVIDENCE == run(.8f + slip, .8f, 1, 500, 0, 843));
    assert(AIR56_FIELD_NO_SLIP_EVIDENCE == run(.8f + slip, .8f, 1, -500, 600, 843));
    assert(AIR56_FIELD_NO_SLIP_EVIDENCE == run(.8f + slip, .8f, 1, 500, IQMAX + 1, 843));
    assert(AIR56_FIELD_NO_SLIP_EVIDENCE == run(.8f + slip, .8f, 1, 500, 600, 589));
    assert(AIR56_FIELD_NO_SLIP_EVIDENCE == run(.8f + slip, .8f, 1, 500, 600, 1096));
    assert(AIR56_FIELD_NO_SLIP_EVIDENCE == run(-(.8f + slip), -.8f, 1, 500, 600, 843));
    assert(AIR56_FIELD_SLIP_DISAGREEMENT == run(1.7f + slip, .8f, 1, 500, 600, 843));
    assert(AIR56_FIELD_COMPENSATED_RATE == run(1.9f + slip, 1.6f, 1, 500, 600, 843));
    air56_field_guard state = {0};
    air56_field_fault fault = {0};
    assert(AIR56_FIELD_NONFINITE == air56_field_check(&state, (qd_t){0}, 0, 0, NAN, 0, &fault));
    assert(AIR56_FIELD_NONFINITE == air56_field_check(&state, (qd_t){0}, 0, 0, 0, INFINITY, &fault));
    assert(fault.samples == 1);
    puts("15 guard cases passed");
}
''', encoding='utf8')
    exe = OUT / 'guard_cases.exe'
    subprocess.run([shutil.which('gcc'), '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2',
                    '-I', str(OUT / 'Inc'), str(source), '-o', str(exe)], check=True, timeout=25)
    return subprocess.check_output([str(exe)], text=True, timeout=10).strip()


def firmware_fault_and_export():
    link, _, _ = startup.startup_fixture(ELF)
    fw, s = link.fw, link.s
    fw.cpu.mem_map(0x50000000, 0x1000)
    pwm = s['PWM_Handle_M1']
    fw.put(s['pwmcHandle'], pwm)
    for suffix in ('Iq', 'Id'):
        fw.call('PID_HandleInit', s[f'PID{suffix}Handle_M1'])
    for offset in (0x88, 0x8c, 0x90):
        fw.put(pwm + offset, 32768)
    fw.put(TIM1 + 0x2c, 5312)
    fw.put(link.mc + 25, 6, 'B')  # MCSDK RUN
    lso = s['ACIM_LSO_Component_M1']
    # Hold an impossible estimated rotor speed while feeding valid current ADC frames.
    angle_fn = s['ACIM_LSO_CalcAngle'] & ~1
    fw.cpu.hook_add(UC_HOOK_CODE, link.stub, user_data='hold observer input', begin=angle_fn, end=angle_fn)
    fw.put(lso + 72, 2 * math.tau, 'f')
    fw.put(lso + 84, 2 * math.tau, 'f')
    fw.put(s['air56_start_flux_A'], .5, 'f')
    for tick in range(1, 257):
        fw.put(pwm + 0x7a, 4, 'B')
        fw.put(0x50000080, 32768)
        fw.put(0x50000180, 32768 + 730)
        fw.put(DWT, link.now * 170000 + tick * 10625)
        fw.call('TSK_HighFrequencyTask')
        assert bool(fw.get(TIM1 + 0x44) & 0x8000) == (tick < 256)
    assert fw.get(link.trace + 28) == 0x20
    link.send()
    assert fw.get(link.trace + 20) == 4 and not fw.get(link.trace + 4)
    start_ms = fw.get(link.trace + 12)
    results = {}
    for page in (261, 259, 260, 0):
        answer = link.send(8, 2, struct.pack('<BBIBB', 7, 0, page, 1, 0xa6))
        assert answer[0][3] & 4 and answer[0][3] & 0x62 == 0
        assert fw.get(s['air56_estopped'], 'B') and not fw.get(TIM1 + 0x44) & 0x8000
        _, results[page] = page_data(answer[2], page, start_ms & 0xffff)
    diagnostic = decode_field_fault(results[261], start_ms)
    assert diagnostic['reason'] == 'rotor_rate' and diagnostic['samples'] == 256
    assert abs(diagnostic['rotor_hz'] - 2) < .001
    assert HEADER.unpack(results[0])[6] == 0x20 and not link.start()
    assert fw.get(s['air56_estopped'], 'B') and not fw.get(TIM1 + 0x44) & 0x8000
    return diagnostic


def main():
    startup.NEW = trip.NEW = uart.NEW = NEW
    flux.ELF, flux.OUT, flux.NEW = ELF, OUT, NEW
    cases = host_guard_cases()
    recorded = OUT.parent / 'lso_2310_5hz_213725_234139/reported_pages/page_000.bin'
    _, old_header = page_data(recorded.read_bytes(), 0)
    _, start, end, rows, _, dwt_cycles, fault, _ = HEADER.unpack(old_header)
    assert (end - start, rows, dwt_cycles, fault) == (206, 20, 1392, 0x20)
    guards, _ = test_uno(ELF, NEW[1])
    diagnostic = firmware_fault_and_export()
    trip.verify_trip(ELF)
    uart.prearm_errors(ELF)
    uart.active_errors(ELF)
    test_uart(ELF)
    firmware = Firmware(ELF)
    dwt, _ = firmware.off_dwt_fixture()
    stack = firmware.sym['_estack'] - firmware.sym['_ebss']
    assert len(dwt) == 64 and max(dwt) < 4000 and stack >= 3072
    test_ccm_startup(ELF)
    closed_loop = flux.model_closed_loop()
    hmi_path = OUT / 'web_hmi/server.py'
    hmi = load('air56_guard_hmi', hmi_path)
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
                  saved_fault_header=dict(duration_ms=end-start, current_rows=rows, dwt_cycles=dwt_cycles,
                                          fault=fault, raw_rows_available=False),
                  host_cases=cases, first_fault_export_with_estop=diagnostic,
                  closed_loop_plant=closed_loop, off_cases=len(dwt), off_max_emulator_instructions=max(dwt),
                  actual_target_DWT_pending=True, stack_headroom_bytes=stack,
                  DWT_limit=4000, ADC_age_limit_us=2000, guards=guards, preserved_files=len(preserved),
                  web_hmi_sha256=sha256(hmi_path.read_bytes()).hexdigest(),
                  images_sha256={p.name: sha256(p.read_bytes()).hexdigest() for p in (OUT / 'image').iterdir()})
    (OUT / 'verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k: report[k] for k in ('passed', 'host_cases', 'closed_loop_plant',
                                             'off_max_emulator_instructions', 'preserved_files')}))


if __name__ == '__main__':
    main()
