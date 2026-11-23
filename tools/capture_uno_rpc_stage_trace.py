"""Read the selected Uno release's RPC journal over USB or SSH, without reset."""
import argparse
import collections
import json
import shlex
import struct
import subprocess
import uuid
from pathlib import Path

from elftools.elf.elffile import ELFFile
from unoq_wifi_hmi_deploy import scp_base, ssh_base
from prepare_rpc_capture_pages import OUT as PAGES_RELEASE

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'artifacts/live_bench_20261120/rpc_stage_trace_r1/build/uno/UNOQ_MOTOR.ino.elf'
KERNEL = (Path.home() / 'AppData/Local/Arduino15/packages/arduino/hardware/zephyr/0.90.0'
          / 'firmwares/zephyr-arduino_uno_q_stm32u585xx.elf')
HOST = '192.168.1.138'


def read_entries(blob):
    magic, version, capacity, newest = struct.unpack_from('<4I', blob)
    if (magic, version, capacity) != (0x31545052, 1, 128) or len(blob) != 4112:
        raise ValueError('Unexpected RPC journal layout')
    entries = {}
    for sequence in range(max(1, newest - capacity + 1), newest + 1):
        row = struct.unpack_from('<8I', blob, 16 + ((sequence - 1) % capacity) * 32)
        guard = 0x91e6b72d
        for word in row[:-1]:
            guard ^= word
        if row[0] == sequence and row[-1] == guard:
            entries[sequence] = row
    return newest, entries


def symbol(path, name):
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        values = elf.get_section_by_name('.symtab').get_symbol_by_name(name)
        if len(values) != 1:
            raise ValueError(f'Ambiguous symbol {name}')
        value = values[0]
        return value['st_value'], value['st_size'], elf.get_section(value['st_shndx']).name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('outdir', type=Path)
    parser.add_argument('--wifi', action='store_true')
    parser.add_argument('--capture-pages', action='store_true', help='Use the installed 2013 ELF')
    args = parser.parse_args()
    args.outdir.mkdir(parents=True)
    app = PAGES_RELEASE / 'build/uno/UNOQ_MOTOR.ino.elf' if args.capture_pages else APP
    elf_offset, size, section = symbol(app, 'mic_rpc_trace')
    extension_list, _, _ = symbol(KERNEL, 'llext_list')
    assert section == '.data' and size == 4112
    remote = '/tmp/mic_rpc_stage_' + uuid.uuid4().hex
    config = f'''$_CHIPNAME.ap0 configure -event examine-end {{}}
$_TARGETNAME configure -event examine-end {{}}
init
set ext [lindex [read_memory {extension_list:#x} 32 1] 0]
if {{$ext < 0x20000000 || $ext >= 0x200c0000}} {{shutdown error}}
set base [lindex [read_memory [expr {{$ext + 24}}] 32 1] 0]
set trace [expr {{$base + {elf_offset}}}]
if {{$trace < 0x20000000 || $trace+{size} > 0x200c0000}} {{shutdown error}}
if {{[lindex [read_memory $trace 32 1] 0] != 0x31545052}} {{shutdown error}}
echo "TRACE_ADDRESS: $trace"
dump_image {remote}/trace.bin $trace {size}
dump_image {remote}/trace2.bin $trace {size}
echo "CORE_AFTER: [$_TARGETNAME curstate]"
shutdown
'''
    (args.outdir / 'read_trace.cfg').write_text(config, encoding='utf-8')
    adb = ['adb', '-s', '3880458060']
    if args.wifi:
        identity = (HOST, 2222, 'arduino', ROOT / '.unoq_ssh/id_ed25519', ROOT / '.unoq_ssh/known_hosts')
        shell = ssh_base(*identity)
        copy = scp_base(*identity)
    else:
        shell = adb + ['shell']
        copy = adb + ['pull']

    def run(command, name):
        result = subprocess.run(command, timeout=20, capture_output=True)
        (args.outdir / (name + '.log')).write_bytes(result.stdout + result.stderr)
        result.check_returncode()
        return result.stdout + result.stderr

    setup = f'import pathlib; p=pathlib.Path({remote!r}); p.mkdir(mode=0o700); (p/"read.cfg").write_text({config!r})'
    run(shell + ['python3 -c ' + shlex.quote(setup)], 'stage')
    log = run(shell + ['/opt/openocd/bin/openocd -s /opt/openocd '
                       '-s /opt/openocd/share/openocd/scripts -f /opt/openocd/openocd_gpiod.cfg '
                       f'-f {remote}/read.cfg'], 'SWD')
    if b'CORE_AFTER: running' not in log:
        raise RuntimeError('Could not verify Uno core state after passive read')
    snapshots = []
    for filename in ('trace.bin', 'trace2.bin'):
        source = (f'arduino@{HOST}:' if args.wifi else '') + f'{remote}/{filename}'
        local = args.outdir / filename
        run(copy + [source, str(local)], 'pull_' + filename)
        snapshots.append(read_entries(local.read_bytes()))
    (end1, first), (end2, second) = snapshots
    stable = [first[n] for n in sorted(first.keys() & second.keys()) if first[n] == second[n]]
    counts = collections.Counter(row[2] for row in stable)
    report = {'transport': 'wifi' if args.wifi else 'usb', 'newest_sequence': [end1, end2],
              'consistent_slots': len(stable), 'stage_events': dict(counts), 'START': 0,
              'CLEAR': 0, 'reset': 0}
    (args.outdir / 'decoded.json').write_text(json.dumps({'report': report, 'rows': stable}, indent=2),
                                             encoding='utf-8')
    print(json.dumps(report))
    return 0 if stable else 1


if __name__ == '__main__':
    raise SystemExit(main())
