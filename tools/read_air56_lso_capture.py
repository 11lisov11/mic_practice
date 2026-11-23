"""Download a frozen AIR56 LSO capture through the Uno. Telemetry commands only."""
import argparse
import csv
import hashlib
import json
import math
import struct
import time
from pathlib import Path
from urllib.request import Request, ProxyHandler, build_opener

HEADER = struct.Struct('<8I')
ROW = struct.Struct('<IhhHHHH')
PAIR = (2026112301, 2026112302)
TRIP_PAIR = (2026112305, 2026112306)
START_PAIR = (2026112307, 2026112308)
FLUX_PAIR = (2026112309, 2026112310)
FIELD_PAIR = (2026112311, 2026112312)
HANDOFF_PAIR = (2026112313, 2026112314)
ADC_WINDOW_PAIR = (2026112315, 2026112316)
FLUX_VOLTAGE_PAIR = (2026112317, 2026112318)
START_PAIRS = (START_PAIR, FLUX_PAIR, FIELD_PAIR, HANDOFF_PAIR, ADC_WINDOW_PAIR, FLUX_VOLTAGE_PAIR)
SUPPORTED_PAIRS = (PAIR, (2026112303, 2026112304), TRIP_PAIR, *START_PAIRS)
AMP = 3.3 / (65536 * .04 * 2.1)
MAGIC = 0x324F534C


def crc32c(data):
    crc = 0xffffffff
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82f63b78 if crc & 1 else 0)
    return crc ^ 0xffffffff


def page_data(packet, index, run=None):
    if len(packet) != 43 or packet[:3] != b'\x55\xaa\xb6':
        raise ValueError('Invalid LSO page header')
    number, epoch = struct.unpack_from('<HH', packet, 3)
    if number != index or (run is not None and epoch != run):
        raise ValueError('Wrong page number or run')
    if struct.unpack_from('<I', packet, 39)[0] != crc32c(packet[:39]):
        raise ValueError('LSO page CRC32C mismatch')
    return epoch, packet[7:39]


def decode(raw):
    magic, start, end, size, reason, worst, first_fault, samples = HEADER.unpack_from(raw)
    if magic != MAGIC or size > 512 or not 1 <= reason <= 5 or len(raw) != HEADER.size + size * ROW.size:
        raise ValueError('Invalid frozen capture')
    rows = list(ROW.iter_unpack(raw[HEADER.size:]))
    assert all(b[0] >= a[0] for a, b in zip(rows, rows[1:]))
    assert not rows or max(row[-1] for row in rows) == min(worst, 65535)
    return dict(start_ms=start, end_ms=end, elapsed_ms=(end - start) % (1 << 32),
                rows=size, stop_reason=reason, max_cycles=worst, first_fault=first_fault,
                injected_samples=samples, dwt_budget_pass=worst <= 4000, sha256=hashlib.sha256(raw).hexdigest()), rows


def decode_trip(raw, start_ms):
    words = struct.unpack('<16I', raw)
    if words[:2] != (0x3150434C, start_ms) or words[10] >= 6 or not words[4]:
        raise ValueError('Invalid first-overcurrent record identity')

    def halves(word):
        return word & 0xffff, word >> 16

    ia, ib = struct.unpack('<hh', raw[36:40])
    phase_counts = (ia, ib, -ia - ib)
    phases = ('U', 'V', 'W')
    trip_phases = [phase for phase, value in zip(phases, phase_counts) if abs(value) > 2252]
    vector_trip = 4 * (ia * ia + ia * ib + ib * ib) > 3 * 2252 * 2252
    if not (trip_phases or vector_trip):
        raise ValueError('Captured current does not meet the first-overcurrent predicate')
    sector = words[10]
    pairs = (('V', 'W'), ('U', 'W'), ('U', 'W'), ('U', 'V'), ('U', 'V'), ('V', 'W'))
    cnt, arr = halves(words[11])
    cr1, sr = halves(words[12])
    return dict(start_ms=start_ms, tick_ms=words[2], cycles_since_start=words[3], sample_index=words[4],
                sampling_sector=sector + 1, adc_phases=pairs[sector], jdr1=halves(words[5]),
                offset_counts=words[6:9], phase_counts=phase_counts,
                phase_nominal_A=[count * AMP for count in phase_counts],
                phase_threshold_crossings=trip_phases, vector_threshold_crossed=vector_trip,
                timer_at_adc_read=dict(cnt=cnt, counting_down=bool(cr1 & 16), cr1=cr1),
                timer_at_fault_handler=dict(arr=arr, sr=sr, ccr=halves(words[13]) + halves(words[14])),
                adc_isr_at_fault_handler=halves(words[15]))


def decode_start(raw, start_ms, end_ms, stop_reason):
    (magic, start, first_check, run_enter, checks, in_band,
     id_min, id_max, id_last, iq_last, id_ref, iq_ref, id_low, id_high,
     speed_ref, speed_target, max_speed_ref, iq_ref_max, last_streak, max_streak,
     terminal_state, ramp_command, run_checks, stages, reserved,
     end, last_run_id, last_run_iq, faults, reason) = struct.unpack('<4I2H12h4BH2BI2h2H', raw)
    if ((magic, start, end, reason) != (0x3154534C, start_ms, end_ms, stop_reason)
        or reserved & ~0x7f or (reserved and reason != 4)
        or stages & ~3 or bool(stages & 1) != bool(checks)
        or in_band > checks or last_streak > max_streak or max_streak > min(in_band, 10)
        or (bool(stages & 2) and max_streak != 10) or (run_checks and not stages & 2)
        or (checks and not id_min <= id_last <= id_max)):
        raise ValueError('Invalid LSO start record')
    magnetization = None
    if checks:
        magnetization = dict(first_check_ms=first_check, checks=checks, in_band=in_band,
            id_counts=dict(min=id_min,max=id_max,last=id_last,reference=id_ref,low=id_low,high=id_high),
            last_iq_counts=iq_last, iq_ref_counts=iq_ref, final_streak=last_streak, max_streak=max_streak)
    report = dict(start_ms=start, end_ms=end, magnetization=magnetization, entered_run=bool(stages & 2),
        run_enter_ms=run_enter if stages & 2 else None, run_checks=run_checks, ramp_command_state=ramp_command,
        speed_target_hz=speed_target / 10, speed_ref_hz=speed_ref / 10, max_speed_ref_hz=max_speed_ref / 10,
        iq_ref_max_counts=iq_ref_max, last_run_id_counts=last_run_id, last_run_iq_counts=last_run_iq,
        terminal_state=terminal_state, terminal_faults=faults, stop_reason=reason)
    if reserved:
        causes = ('current_fault', 'occurred_fault', 'break_configuration', 'sd_low',
                  'break_irq_disabled', 'break_flag', 'bus_out_of_range')
        report['motor_guard_causes'] = [name for i, name in enumerate(causes) if reserved & (1 << i)]
    return report


def decode_field_fault(raw, start_ms):
    magic, start, reason, samples, field, rotor, reference, slip, flux = struct.unpack('<IIHH5f', raw)
    reasons = ('nonfinite', 'rotor_rate', 'no_slip_evidence', 'slip_disagreement', 'compensated_rate')
    if ((magic, start) != (0x3144464c, start_ms) or not 1 <= reason <= len(reasons)
            or not 1 <= samples <= 256 or (reason != 1 and samples != 256)):
        raise ValueError('Invalid first field fault record')
    values = [x if math.isfinite(x) else None for x in (field, rotor, reference, slip, flux)]
    return dict(start_ms=start, reason=reasons[reason - 1], samples=samples,
                field_hz=values[0], rotor_hz=values[1], reference_hz=values[2],
                measured_slip_hz=values[3], current_equivalent_flux_counts=values[4])


def decode_start_q(raw, start_ms, checks):
    magic, start, tick, adc, blocks, limit, sector, samples, iq, id_, vq, vd = struct.unpack('<4I4H4h', raw)
    if ((magic, start, samples) != (0x3151534c, start_ms, checks) or not 0 < limit or
            not 0 < samples or blocks > samples or sector >= 6):
        raise ValueError('Invalid START quadrature record')
    return dict(start_ms=start, peak_time_ms=tick, samples=samples, iq_blocked_checks=blocks,
                iq_limit_counts=limit, iq_peak_counts=iq, id_at_peak_counts=id_,
                adc_jdr_pair=[adc & 0xffff, adc >> 16], adc_sampling_sector=sector + 1,
                vq_at_peak_command_counts=vq, vd_at_peak_command_counts=vd)


def decode_flux_voltage(raw, start_ms):
    magic, start, *values = struct.unpack('<II10hBBH', raw)
    steps, result, loss_mv = values[10:]
    if ((magic, start) != (0x3156464c, start_ms) or
            not 0 <= steps <= 5 or result not in (0, 1, 2) or loss_mv > 14000):
        raise ValueError('Invalid stationary voltage record')
    return dict(start_ms=start, observer_pole_loss_V=loss_mv / 1000,
                result=('interrupted', 'qualified', 'timeout')[result],
                steps=[dict(limit_at_350_V_DC=14 + i * 2, mean_id_A=values[i] * AMP,
                            mean_iq_A=values[i + 5] * AMP) for i in range(steps)])


def download(url, token_path, out):
    token = token_path.read_text(encoding='utf-8').strip()
    opener = build_opener(ProxyHandler({}))

    def rpc(path, body=None):
        request = Request(url.rstrip('/') + path, data=None if body is None else json.dumps(body).encode(),
                          headers={'Content-Type':'application/json', 'X-UNOQ-Control-Token':token})
        with opener.open(request, timeout=5) as handle:
            reply = json.load(handle)
        if reply.get('ok') is not True:
            raise RuntimeError('Uno rejected LSO telemetry')
        return reply.get('data')

    initial = rpc('/api/status')
    pair = (initial.get('fw_build'), initial.get('mc_fw_build'))
    if pair not in SUPPORTED_PAIRS:
        raise RuntimeError('Unsupported firmware pair')

    def assert_off(s):
        if ((s.get('fw_build'), s.get('mc_fw_build')) != pair or s.get('state') != 'SAFE' or
            s.get('pwm') != 0 or s.get('bp_status', 0x22) & 0x22 or not 0 <= s.get('mc_age_ms', 9999) < 300):
            raise RuntimeError('Wrong peer or fresh PWM-OFF evidence unavailable')

    def read_page(index, run=None):
        assert_off(rpc('/api/status'))
        rpc('/api/cmd', {'cmd':f'LSO PAGE {index}'})
        end = time.monotonic() + 4
        while time.monotonic() < end:
            s = rpc('/api/status')
            assert_off(s)
            try:
                packet = bytes.fromhex(s.get('mc_lso_page_hex', '-'))
                page = page_data(packet, index, run)
            except ValueError:
                time.sleep(.05)
                continue
            (out / f'page_{index:03}.bin').write_bytes(packet)
            return page
        raise RuntimeError(f'LSO page {index} unavailable')

    assert_off(initial)
    epoch, header = read_page(0)
    magic, start, end, count, reason, _, first_fault, _ = HEADER.unpack(header)
    if magic != MAGIC or start & 0xffff != epoch or count > 512 or not 1 <= reason <= 5:
        raise ValueError('No matching completed LSO record')
    if pair in START_PAIRS:
        diagnostic = b''.join(read_page(index, epoch)[1] for index in (259, 260))
        (out / 'start_diagnostic.bin').write_bytes(diagnostic)
        startup = decode_start(diagnostic, start, end, reason)
        (out / 'start_diagnostic.json').write_text(
            json.dumps(startup, indent=2) + '\n', encoding='utf8')
        if pair in (HANDOFF_PAIR, ADC_WINDOW_PAIR, FLUX_VOLTAGE_PAIR) and startup['magnetization']:
            start_q = read_page(262, epoch)[1]
            (out / 'start_quadrature.bin').write_bytes(start_q)
            (out / 'start_quadrature.json').write_text(json.dumps(decode_start_q(start_q, start,
                startup['magnetization']['checks']), indent=2) + '\n', encoding='utf8')
            if pair == FLUX_VOLTAGE_PAIR:
                voltage = read_page(263, epoch)[1]
                (out / 'start_voltage.bin').write_bytes(voltage)
                (out / 'start_voltage.json').write_text(json.dumps(decode_flux_voltage(voltage, start),
                    indent=2) + '\n', encoding='utf8')
    if pair in (TRIP_PAIR, *START_PAIRS) and first_fault & 0x40:
        trip = b''.join(read_page(index, epoch)[1] for index in (257, 258))
        (out / 'first_overcurrent.bin').write_bytes(trip)
        (out / 'first_overcurrent.json').write_text(json.dumps(decode_trip(trip, start), indent=2) + '\n',
                                                    encoding='utf8')
    if pair in (FIELD_PAIR, HANDOFF_PAIR, ADC_WINDOW_PAIR, FLUX_VOLTAGE_PAIR) and first_fault & 0x20:
        field = read_page(261, epoch)[1]
        (out / 'field_fault.bin').write_bytes(field)
        (out / 'field_fault.json').write_text(json.dumps(decode_field_fault(field, start), indent=2) + '\n',
                                              encoding='utf8')
    samples = b''.join(read_page(i, epoch)[1] for i in range(1, (count + 1) // 2 + 1))
    return header + samples[:count * ROW.size]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', required=True)
    p.add_argument('--token-file', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    a.output.mkdir()
    raw = download(a.url, a.token_file, a.output)
    report, rows = decode(raw)
    (a.output/'capture.bin').write_bytes(raw)
    with (a.output/'currents_dwt.csv').open('w', newline='', encoding='utf8') as handle:
        writer = csv.writer(handle)
        writer.writerow(('time_ms','ia_A','ib_A','ic_A','peak_ia_A','peak_ib_A','peak_ic_A','max_dwt_cycles'))
        for tick, ia, ib, pa, pb, pc, dwt in rows:
            writer.writerow((tick/170000,ia*AMP,ib*AMP,(-ia-ib)*AMP,pa*AMP,pb*AMP,pc*AMP,dwt))
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')


if __name__ == '__main__':
    main()
