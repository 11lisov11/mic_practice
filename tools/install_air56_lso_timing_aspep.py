"""Install and verify only the sealed AIR56 LSO timing and ASPEP candidate."""
import argparse
import json
import struct
import subprocess
import time

from serial.tools import list_ports

from install_air56_lso_off_dwt import (
    NAME, PROGRAMMER, STLINK_SERIAL, SWD, inspect_layout, parse_registers,
    probe_motor_pilot, programmed_hex_image, read_dwt, read_json, release, save, sha,
)
from prepare_air56_lso_timing_aspep import BASE, OUT, ROOT

FLASH = 0x08000000
RAM = 0x20000000


def images(folder):
    base = folder / 'image' / NAME
    return base.with_suffix('.elf'), base.with_suffix('.hex'), base.with_suffix('.bin')


def install():
    candidate = read_json(OUT / 'verification.json')
    offline = read_json(OUT / 'timing_aspep_PC.json')
    assert candidate['passed'] and offline['ccm_reset_copy']
    assert (offline['dwt_budget'], offline['adc_deadline_us']) == (4000, 2000)
    release.base.verify_inventory(candidate['images_sha256'], OUT / 'image')
    protected = read_json(OUT / 'preserved_inputs_sha256.json')
    protected.update(read_json(OUT / 'preserved_lso_captures_sha256.json'))
    release.base.verify_inventory(protected, ROOT)
    old_elf, old_hex, old_bin = images(BASE)
    new_elf, new_hex, new_bin = images(OUT)
    old, _ = programmed_hex_image(old_hex, old_bin.read_bytes())
    expected, holes = programmed_hex_image(new_hex, new_bin.read_bytes())
    vcp = [p.device for p in list_ports.comports()
           if (p.vid, p.pid, p.serial_number) == (0x0483, 0x374E, STLINK_SERIAL)]
    assert len(vcp) == 1, 'Expected the exact Nucleo ST-LINK COM port'
    attempts = sorted(OUT.glob('hardware_install_r[0-9]*'))
    assert not any((folder / 'programming_intent.json').exists() for folder in attempts), 'Image was already issued'
    out = OUT / f'hardware_install_r{len(attempts) + 1}'
    out.mkdir()
    report = dict(passed=False, port=vcp[0], programming_attempts=0, START=0, CLEAR=0, ARM=0)

    def run(args, name, timeout=30):
        proc = subprocess.run(args, capture_output=True, text=True, errors='replace', timeout=timeout)
        (out / (name + '.log')).write_text(proc.stdout + proc.stderr, encoding='utf8')
        proc.check_returncode()
        return proc.stdout

    def read(address, count, name):
        file = out / (name + '.bin')
        run(SWD + ['-u', hex(address), str(count), str(file)], name)
        data = file.read_bytes()
        assert len(data) == count, name
        return data

    def safety(elf, label):
        symbols, layout = inspect_layout(elf)
        base, tick = symbols['BusVoltageSensor_M1'], symbols['uwTick']
        reg = parse_registers(run(SWD + ['-r32', hex(base), '12', '-r32', hex(tick), '4',
            '-r32', '0x40012c0c', '12', '-r32', '0x40012c44', '4', '-r32', '0x48000010', '4'], label))
        raw = b''.join(struct.pack('<I', reg[base + idx]) for idx in (0, 4, 8))
        scale = struct.unpack_from('<H', raw, layout['ConversionFactor'])[0]
        digit = struct.unpack_from('<H', raw, layout['AvBusVoltage_d'])[0]
        volts = scale * digit / 65536
        bdtr = reg[0x40012C44]
        state = dict(bus_V=volts, tick=reg[tick], MOE=bool(bdtr & 0x8000),
                     AOE=bool(bdtr & 0x4000), BKE=bool(bdtr & 0x1000), BKF=(bdtr >> 16) & 15,
                     BIE=bool(reg[0x40012C0C] & 128), PA6_HIGH=bool(reg[0x48000010] & 64),
                     TIM1_SR=reg[0x40012C10])
        assert scale == 416 and 0 < volts < 20, state
        assert not state['MOE'] and not state['AOE'] and state['BKE'] and state['BKF'] == 9, state
        return state, symbols

    try:
        # Preserve both the known image and the volatile diagnostic records before reset.
        first, _ = safety(old_elf, 'before_1')
        original = read(FLASH, 128 * 1024, 'previous_LSO_full_flash')
        assert original[:len(old)] == old, 'Installed image is not the expected prior LSO'
        read(RAM, 32768, 'previous_LSO_full_RAM')
        report['old_flash_and_RAM_preserved'] = True
        second, _ = safety(old_elf, 'before_2')
        assert 100 < (second['tick'] - first['tick']) % (1 << 32) < 20000
        report['before'] = second
        report['programming_attempts'] = 1
        save(out / 'programming_intent.json', report)
        run([str(PROGRAMMER), '-c', 'port=SWD', 'mode=UR', 'sn=' + STLINK_SERIAL,
             '-w', str(new_hex), '-v', '-rst'], 'program_once', 75)
        result = read(FLASH, len(expected), 'new_LSO_flash_readback')
        assert result == expected, 'Flash differs on independent readback'
        report.update(readback_verified=True, readback_bytes=len(result),
                      readback_sha256=sha(out / 'new_LSO_flash_readback.bin'), hex_padding_offsets=holes)
        report['after'], symbols = safety(new_elf, 'after')
        ccm_start, ccm_end, ccm_flash = (symbols[name] for name in ('_sccmram', '_eccmram', '_siccmram'))
        resident = read(ccm_start, ccm_end - ccm_start, 'CCM_runtime_code')
        assert resident == expected[ccm_flash - FLASH:ccm_flash - FLASH + len(resident)], 'CCM startup copy differs'
        report['ccm_verified_bytes'] = len(resident)
        report['DWT'] = read_dwt(read, symbols)
        raw = next(path.read_bytes() for path in sorted(out.glob('DWT_*.bin'), reverse=True))
        cases = struct.unpack('<133I', raw)[5:69]
        report['DWT'].update(min_cycles=min(cases), cases_above_4000=sum(x > 4000 for x in cases))
        try:
            report['motor_pilot_protocol'] = probe_motor_pilot(vcp[0])
        except (AssertionError, OSError, RuntimeError, ValueError) as error:
            report['motor_pilot_protocol_error'] = repr(error)
        report['final'], _ = safety(new_elf, 'final')
        report['passed'] = report['DWT']['passed'] and 'motor_pilot_protocol' in report
    except Exception as error:
        report['error'] = repr(error)
    finally:
        release.base.verify_inventory(protected, ROOT)
        report['preserved_files_verified'] = len(protected)
        save(out / 'report.json', report)
        save(out / 'sha256.json', {path.name: sha(path) for path in out.iterdir() if path.is_file()})
    print(str(out))
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirmed-j1-off', required=True, action='store_true')
    parser.parse_args()
    raise SystemExit(install())
