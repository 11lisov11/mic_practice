"""Replay the captured aperture and current protection through compiled motor code."""
from hashlib import sha256
import json
import math
import struct
import sys

from unicorn import UC_HOOK_CODE

import verify_air56_lso_field_guard as field
import verify_air56_lso_start_record as startup
import verify_air56_lso_trip_capture as trip
import verify_air56_uart_startup as uart
from prepare_air56_lso_adc_window import BASE, NEW, OUT, ROOT
from read_air56_lso_capture import AMP, decode, decode_trip
from verify_air56_hmi_bounded_stop import load, replay_statuses, run_watchdog
from verify_air56_lso_timing_aspep import DWT, TIM1, Firmware, test_ccm_startup, test_uart
from verify_air56_lso_uno_capture import test_uno

sys.path.insert(0, str(ROOT))
from motor_identification.model import MotorParameters, MotorState, _step

ELF = OUT / 'image/ACIM-AIR56B2-LSO_FOC.elf'
CAPTURE = OUT.parent / 'lso_2314_5hz_235414_217876/capture'
TIMER_HALF, SETTLE, APERTURE = 5312, 771, 112
PHASE_PAIRS = ((1, 2), (0, 2), (0, 2), (0, 1), (0, 1), (1, 2))


def legal_window(duties, trigger, sector):
    return (0 < trigger <= TIMER_HALF - 128
            and all(duties[p] + SETTLE < trigger for p in PHASE_PAIRS[sector])
            and all(edge + SETTLE < trigger or edge > trigger + APERTURE for edge in duties))


def timer_cases(duties, old_trigger, sector):
    fw = Firmware(ELF)
    pwm = fw.sym['PWM_Handle_M1']
    assert fw.get(pwm + 148, 'H') == TIMER_HALF
    assert not legal_window(duties, old_trigger, sector)

    def program(phase_duties, expected_pair):
        for index, value in enumerate(phase_duties):
            fw.put(pwm + 80 + 2 * index, value, 'H')
        assert fw.call('R3_2_SetADCSampPointSectX', pwm) == 0
        plan = fw.words(TIM1 + 0x34, 4)
        picked = fw.get(pwm + 122, 'B')
        assert PHASE_PAIRS[picked] == expected_pair
        assert plan[:3] == phase_duties and legal_window(phase_duties, plan[3], picked)
        return plan[3]

    relocated = program(duties, (0, 1))
    assert relocated != old_trigger
    program((duties[2], duties[0], duties[1]), (1, 2))
    program((duties[0], duties[2], duties[1]), (0, 2))
    program((2700, 2656, 2500), (1, 2))
    unchanged = fw.words(TIM1 + 0x34, 4)
    for offset in (80, 82, 84):
        fw.put(pwm + offset, 5000, 'H')
    assert fw.call('R3_2_SetADCSampPointSectX', pwm) == 1  # MC_DURATION
    assert fw.words(TIM1 + 0x34, 4) == unchanged
    return dict(old_trigger_ticks=old_trigger, revised_trigger_ticks=relocated,
                before_w_ticks=duties[2]-old_trigger, revised_before_w_ticks=duties[2]-relocated,
                required_acquisition_ticks=APERTURE, no_window_publishes_no_duties=True)


def overcurrent_replay(snapshot):
    link, _, _ = startup.startup_fixture(ELF)
    fw, s = link.fw, link.s
    pwm = s['PWM_Handle_M1']
    fw.cpu.mem_map(0x50000000, 0x1000)
    fw.put(s['pwmcHandle'], pwm)
    fw.put(pwm + 0x7a, 4, 'B')
    for offset, value in zip((0x88, 0x8c, 0x90), snapshot['offset_counts']):
        fw.put(pwm + offset, value)
    fw.put(0x50000080, snapshot['jdr1'][0])
    fw.put(0x50000180, snapshot['jdr1'][1])
    fw.put(TIM1 + 0x24, 3800)
    fw.put(TIM1 + 0x2c, TIMER_HALF)
    fw.put(DWT, link.now * 170000)
    fw.call('TSK_HighFrequencyTask')
    assert not fw.get(TIM1 + 0x44) & 0x8000 and fw.get(link.trace + 28) == 0x40
    raw = bytes(fw.cpu.mem_read(s['air56_trip_record'], 64))
    recovered = decode_trip(raw, fw.get(link.trace + 12))
    assert list(recovered['phase_counts']) == snapshot['phase_counts']
    return dict(unchanged_trip_code=64, replay_counts=recovered['phase_counts'])


def model_from_timer():
    link, step, frozen = startup.startup_fixture(ELF)
    fw, s = link.fw, link.s
    pwm, foc = s['PWM_Handle_M1'], s['FOCVars']
    lso = s['ACIM_LSO_Component_M1']
    fw.cpu.mem_map(0x50000000, 0x1000)
    fw.put(s['pwmcHandle'], pwm)
    for suffix in ('Iq', 'Id'):
        fw.call('PID_HandleInit', s[f'PID{suffix}Handle_M1'])

    def switch_on(cpu, address, size, _):
        fw.put(TIM1 + 0x44, fw.get(TIM1 + 0x44) | 0x8000)
        link.stub(cpu, address, size, 'PWM register fixture')

    switch_address = s['R3_2_SwitchOnPWM'] & ~1
    fw.cpu.hook_add(UC_HOOK_CODE, switch_on, begin=switch_address, end=switch_address)
    fw.put(link.mc + 25, 16, 'B')  # The actual CHARGE_BOOT_CAP-to-START code installs the caps.
    fw.call('TSK_MediumFrequencyTaskM1')
    assert fw.get(link.mc + 25, 'B') == 4 and fw.get(TIM1 + 0x44) & 0x8000
    for offset in (0x88, 0x8c, 0x90):
        fw.put(pwm + offset, 32768)
    for index, value in enumerate((2656, 2656, 2656, 5184)):
        fw.put(TIM1 + 0x34 + 4 * index, value)
    fw.put(TIM1 + 0x2c, TIMER_HALF)
    fw.put(pwm + 0x7a, 4, 'B')
    m = json.loads((OUT / 'AIR56B2_profile.json').read_text())['motor']
    plant = MotorParameters(m['Rs'], m['Rr'], m['Lls'], 1.5*m['Lms'], m['inertia']/1e6,
                            m['friction']/1e6, m['polesPairs'], 1.35, .01)
    state = MotorState()
    alpha = beta = 0.0
    root3 = math.sqrt(3)
    start_peak_v = peak_a = 0.0
    entered = None
    used_pairs = set()
    checkpoints = []
    for tick in range(1,80001):
        currents=(alpha,(-alpha+root3*beta)/2,(-alpha-root3*beta)/2)
        picked=PHASE_PAIRS[fw.get(pwm + 0x7a,'B')]
        used_pairs.add(picked)
        for offset, phase in zip((0x80,0x180), picked):
            fw.put(0x50000000 + offset,32768-16*round(currents[phase]/(16*AMP)))
        fw.put(DWT, link.now * 170000 + tick * 10625 % 170000)
        fw.call('TSK_HighFrequencyTask')
        assert fw.get(TIM1 + 0x44) & 0x8000, (tick, fw.get(link.trace + 28))
        a,b,c,trigger = fw.words(TIM1 + 0x34,4)
        assert legal_window((a,b,c),trigger,fw.get(pwm + 0x7a,'B'))
        va = (2*a-b-c)*320/(3*TIMER_HALF)
        vb = (b-c)*320/(root3*TIMER_HALF)
        if entered is None:
            start_peak_v=max(start_peak_v,math.hypot(va,vb))
        state,alpha,beta = _step(plant,state,va,vb,0.0,1/16000,False)
        peak_a=max(peak_a,math.hypot(alpha,beta))
        if tick%32==0:
            step(tick//16,fw.get(foc+10,'h'))
            if entered is None and fw.get(link.mc+25,'B')==6:
                entered=tick//16
            if tick%16000==0:
                checkpoints.append({'time_ms':tick//16,'rpm':state.omega_m*60/math.tau,'observer_rpm':fw.get(lso+88,'f')})
    summary=frozen()
    assert entered is not None and entered>=78
    assert start_peak_v<=20.05 and peak_a<.8
    assert all(285<=s['rpm']<=315 for s in checkpoints[1:])
    assert summary['stop_reason']==1 and summary['terminal_faults']==0 and not fw.get(TIM1 + 0x44)&0x8000
    return dict(first_run_ms=entered,start_phase_voltage_vector_peak_V=start_peak_v,current_vector_peak_A=peak_a,
                selected_adc_pairs=sorted(used_pairs), checkpoints=checkpoints, stop_ms=5000,
                scope='quantized ADC, averaged PWM1 voltage reconstructed from compiled CCR, nominal calculated motor')


def main():
    startup.NEW = trip.NEW = uart.NEW = NEW
    field.ELF,field.OUT,field.NEW=ELF,OUT,NEW
    q=json.loads((CAPTURE/'start_quadrature.json').read_text())
    trip_summary=json.loads((CAPTURE/'first_overcurrent.json').read_text())
    capture,rows=decode((CAPTURE/'capture.bin').read_bytes())
    assert capture['first_fault']==64 and capture['elapsed_ms']==155 and q['iq_peak_counts']==1997
    ccr=trip_summary['timer_at_fault_handler']['ccr']
    assert ccr==[1119,182,5131,5090] and not trip_summary['timer_at_adc_read']['counting_down']
    plan=timer_cases(tuple(ccr[:3]),ccr[3],trip_summary['sampling_sector']-1)
    overcurrent=overcurrent_replay(trip_summary)
    plateau=[(tick/170000,ia*AMP) for tick,ia,*_ in rows if 60<tick/170000<155]
    assert len(plateau)==10 and all(i>.9 for _,i in plateau)
    model=model_from_timer()
    guards,_=test_uno(ELF,NEW[1])
    field.firmware_fault_and_export()
    trip.verify_trip(ELF)
    uart.prearm_errors(ELF)
    uart.active_errors(ELF)
    test_uart(ELF)
    fw=Firmware(ELF)
    dwt,_=fw.off_dwt_fixture()
    stack=fw.sym['_estack']-fw.sym['_ebss']
    assert len(dwt)==64 and max(dwt)<4000 and stack>=3072
    test_ccm_startup(ELF)
    hmi_path=OUT/'web_hmi/server.py'
    hmi=load('air56_adc_window_hmi',hmi_path)
    before,running,complete=(dict(s,fw_build=NEW[0],mc_fw_build=NEW[1]) for s in replay_statuses())
    commands,messages,state=run_watchdog(hmi,before,running,[complete],[True,False])
    assert not commands and state['hmi_hv_armed']==0
    assert any('WIFI_BOUNDED_COMPLETE' in msg for msg in messages)
    for name in ('air56_st_lso_limits.h','air56_lso_capture.h','air56_lso_field_guard.h',
                 'uart_v3_transport.h','drive_parameters.h'):
        assert (OUT/'Inc'/name).read_bytes()==(BASE/'Inc'/name).read_bytes()
    preserved=json.loads((OUT/'preserved_inputs_sha256.json').read_text())
    for name,digest in preserved.items():
        assert sha256((ROOT/name).read_bytes()).hexdigest()==digest
    report=dict(passed=True,pair=NEW,hardware_commands=0,installed=False,
                bench_snapshot=trip_summary, bench_current_peak_cause_proven=False,
                benchmark_start_iq_peak_A=q['iq_peak_counts']*AMP, benchmark_fixed_axis_iq_samples=plateau,
                replayed_timer_plan=plan,raw_overcurrent_replay=overcurrent,closed_loop_plant=model,
                off_cases=len(dwt),off_max_emulator_instructions=max(dwt),actual_target_DWT_pending=True,
                stack_headroom_bytes=stack,DWT_limit=4000,ADC_age_limit_us=2000,guards=guards,
                preserved_files=len(preserved),web_hmi_sha256=sha256(hmi_path.read_bytes()).hexdigest(),
                images_sha256={p.name:sha256(p.read_bytes()).hexdigest() for p in (OUT/'image').iterdir()})
    (OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:report[k] for k in ('passed','replayed_timer_plan','raw_overcurrent_replay',
                                           'closed_loop_plant','off_max_emulator_instructions','preserved_files')}))


if __name__=='__main__':
    main()
