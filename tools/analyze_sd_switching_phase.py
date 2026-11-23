"""Offline evidence and decision plan for the 25-Hz SD event. No hardware I/O."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'artifacts/live_bench_20261020/sd_break_filter_to_50_r1'
OUT = ROOT / 'artifacts/live_bench_20261020/sd_root_cause_investigation_r1'


def main():
    OUT.mkdir(exist_ok=True)
    wave = json.loads((RUN / 'after_bkin_trace.json').read_text())['data']
    snapshot = json.loads((RUN / 'after_break_snapshot.json').read_text())['data']['mc_break_snapshots'][0]['raw']
    period_us = 2 * snapshot['tim_arr'] / 170000000 * 1e6
    lows = [x for x in wave['runs'] if x['level'] == 0]
    anchor = lows[-1]['from_us']
    edges = []
    for low in lows:
        delta = low['from_us'] - anchor
        cycles = round(delta / period_us)
        residual = delta - cycles * period_us
        edges.append(dict(edge_us=low['from_us'], samples=low['samples'],
            nearest_pwm_cycles=cycles, residual_us=residual, within_600ns=abs(residual) <= .6))
    result = dict(
        physical_root_cause_proven=False, hardware_commands=0, motor_commands=0,
        source_run=str(RUN), event_tick_ms=wave['event_tick_ms'],
        leading_hypothesis='Switching-related disturbance on SD or its reference/route; not yet localized.',
        nominal_pwm_period_us=period_us, configured_timer_kernel_hz=170000000,
        matching_edges=sum(x['within_600ns'] for x in edges), total_low_edges=len(edges), edges=edges,
        phase_comparison_limitations=[
            'Grid anchored to the last recorded LOW; this is a descriptive comparison, not a statistical significance test.',
            'A current-sense switching spike can also be PWM synchronous.',
            'Nominal DMA sampling timing has not been independently calibrated under power.',
        ],
        confirmed_facts=['Actual BKF9 at Break; software filter update was installed.',
                         'CRC/sequence/transport counters remained zero; Uno NOISE advisory reached18.',
                         'The nearest LOW was3 nominal200ns samples; exact analog width is unknown.',
                         '5/10/15/20Hz held;25Hz event,30..50Hz not commanded.',
                         'A different startup event was18.4618ms with MOE0; it must not be merged with this event.'],
        module_datasheet=dict(oc_hold_typ_us=24, uvlo_hold_typ_us=70,
            hold_values_are_guaranteed_minima=False, cin_threshold_min_typ_max_v=[.460,.510,.560],
            vccl_uvlo_off_min_typ_max_v=[9.0,10.3,11.0]),
        newly_identified_hardware_uncertainty=dict(
            source='UM2014 Rev3 Figure7 page7 vs BOM page25 item28',
            reference_designators=['R25','R26','R27'], schematic_shunt_ohm=.04,
            bom_shunt_ohm=.08, configured_firmware_shunt_ohm=.04, actual_board_value_known=False,
            operator_question_sent=True, operator_answer_received=False,
            interpretation='Verify markings R040/0R04 versus R080/0R08 before treating current scaling or OC threshold as qualified.'),
        immediate_static_check=dict(
            action='Read actual R25/R26/R27 markings; no MCU flashing or PC connection required.',
            state_before_handling='J1 and J4 off; independently measured DC bus below20V; motor may remain connected.',
            note='Ordinary two-wire resistance measurement cannot reliably establish40 versus80milliohms.'),
        next_powered_measurement=dict(
            design_only_not_implemented=True,
            aim='Localize the SD disturbance with simultaneous source/receiver observation.',
            proposed_probe_input='PA4 / Nucleo CN7-32 (also A2/CN8-3)',
            connection_after_deenergization='STEVAL TP23 SD to a high-impedance PA4 input; existing PA6/BKIN route preserved.',
            existing_input='PA6 / CN10-13',
            board_level='UM2014 shows3.3V pullup R28=10k and C20=330pF; verify actual level/load before wiring.',
            firmware_audit='PA4 not configured in installed application; same GPIOA IDR DMA word already contains PA4 and PA6 bits.',
            adapter_audit='IHM09M2 labels PA4 as DAC; connector loading must be checked before actual wiring. No prepared firmware claimed.',
            sampler='Joint two-bit recording from one GPIOA IDR read; no extra DMA traffic is inherently required.',
            acceptance='Do not issue another powered motor test until the diagnostic build and off-bus comparison are verified.',
            outcomes=[
                'PA6 LOW but direct TP23 observation HIGH: investigate receiver/route/reference/probe influence; verify by swapping measurement paths.',
                'Both LOW: event reaches both observation points; does not uniquely identify internal IPM fault versus common reference disturbance.',
                'Independent observations HIGH while TIM1 BIF sets: investigate other Break sources and recorder timing.',
            ]),
        analog_branch=dict(
            required_if_shared_sd_event_remains_unclassified=True,
            points={'SD':'TP23', 'CIN':'TP17', 'driver_VCC':'TP8', 'local_reference':'TP21 or TP22'},
            interpretations=[
                'CIN crossing the actual comparator threshold before SD: qualify phase current and CIN RC/shunt circuit to distinguish real OC from a spike.',
                'VCC_LS crossing UVLO before SD: inspect supply at the module, C12/C13 decoupling and its return path.',
                'VCC and CIN quiet but SD glitches: inspect SD pullup/filter/routing and local reference; validate analog bandwidth and thresholds.',
            ],
            current_tool_limit='Existing Saleae is digital-only,24MS/s. It cannot measure0.5V CIN or15V driver supply and must not be directly tied to the energized nonisolated bridge/PC.',
            needed_instrument='Qualified isolated analog inputs or suitable differential probes for this mains-referenced circuit; no ordinary earth-referenced ground clip.'),
        saleae_auxiliary_only=dict(
            ready_helper='tools/capture_sd_endpoints_aux.py', supported_pair=[2026102001,2026102002],
            mapping={'CH6':'PA6/CN10-13','CH7':'TP23','GND':'CN7-19'},
            power='J1 physically unplugged, bus below2V before probes, J4 off before wiring then auxiliary-only capture.',
            sample_rate_hz=24000000, no_digital_glitch_filter=True,
            limitation='Validates auxiliary signal path/recorder only. No event here does not qualify25Hz powered operation.'),
        do_not_infer=['A 600ns nominal record proves a600ns physical pulse.',
                      'Typical24/70us internal timing guarantees every internal fault pulse is longer.',
                      'A51C sensor reading excludes all internal thermal mechanisms.',
                      'Increasing BKF alone fixes the physical SD source.',
                      'Same waveform at two MCU inputs proves an intrinsic IPM fault.'],
        sources=[
            dict(title='Exact module DS10424 Rev10 Tables8/10/11',url='https://www.st.com/resource/en/datasheet/stgib15ch60ts-l.pdf'),
            dict(title='ST AN4694 section5 item5: driver/controller reference inductance',url='https://www.st.com/resource/en/application_note/an4694-emc-design-guides-for-motor-control-applications-stmicroelectronics.pdf'),
            dict(title='UM2014 Rev3 pages7/23/25',local_path=str(ROOT/'um2014-1500-w-motor-control-power-board-based-on-stgib15ch60tsl-sllimm-2nd-series-ipm-stmicroelectronics.pdf')),
            dict(title='UM2505 Rev7 connector mapping',url='https://www.st.com/resource/en/user_manual/um2505-stm32g4-nucleo64-boards-mb1367-stmicroelectronics.pdf'),
            dict(title='IHM09M2 schematic, PA4 DAC routing',url='https://www.st.com/resource/en/schematic_pack/x-nucleo-ihm09m2_schematic.pdf'),
        ])
    assert result['matching_edges'] == 6 and result['total_low_edges'] == 9
    (OUT / 'findings.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('physical_root_cause_proven','nominal_pwm_period_us','matching_edges','total_low_edges','hardware_commands')}))


if __name__ == '__main__':
    main()
