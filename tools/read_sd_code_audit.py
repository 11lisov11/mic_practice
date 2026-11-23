"""Read-only audit of PA6/BKIN and installed instructions on an OFF bench.

Only HTTP GET and ST-LINK HOTPLUG memory reads are issued. No writes, halt,
reset, fault-clear or motor commands. Caller must have current J1/J4 OFF.
"""
import hashlib
import json
import re
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'artifacts/live_bench_20261030/observer_trace_r1'
OUT = ROOT / 'artifacts/live_bench_20261031/sd_code_audit_r1'
CLI = Path('C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe')


def main():
    token = (ROOT / '.unoq_ssh/control_token').read_text().strip()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get_status(label):
        request = urllib.request.Request('http://192.168.1.138:8080/api/status',
                                        headers={'X-UNOQ-Control-Token': token}, method='GET')
        with opener.open(request, timeout=6) as response:
            result = json.load(response)
        assert result.get('ok')
        data = result['data']
        assert data['state'] == 'SAFE' and data['pwm'] == 0
        assert (data['fw_build'], data['mc_fw_build']) == (2026103015, 2026103016)
        assert 0 <= data['mc_age_ms'] < 300
        (OUT / (label + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return data

    OUT.mkdir(parents=True, exist_ok=True)
    before = get_status('before_register_read')
    assert before['vdc'] < 20
    command = [str(CLI), '-c', 'port=SWD', 'mode=HOTPLUG', 'sn=003A002C3335510933383531',
               '-r32', '0x48000000', '40', '-r32', '0x40012c00', '104',
               '-r32', '0x40010300', '12', '-r32', '0xE000EDF0', '4',
               '-r32', '0x080064e0', '96']
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=20, check=True)
    (OUT / 'hotplug_register_read.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    words = {}
    for line in result.stdout.splitlines():
        match = re.fullmatch(r'\s*0x([0-9A-Fa-f]{8})\s*:\s*((?:[0-9A-Fa-f]{8}\s*)+)\s*', line)
        if match:
            for index, value in enumerate(match[2].split()):
                words[int(match[1], 16) + 4*index] = int(value, 16)

    gpio, timer = 0x48000000, 0x40012C00

    def pin(number):
        return dict(mode=(words[gpio] >> (2*number)) & 3,
                    open_drain=bool(words[gpio+4] & (1 << number)),
                    pull=(words[gpio+12] >> (2*number)) & 3,
                    high=bool(words[gpio+16] & (1 << number)),
                    output_latch=bool(words[gpio+20] & (1 << number)),
                    locked=bool(words[gpio+28] & (1 << number)),
                    af=(words[gpio+32+4*(number//8)] >> (4*(number % 8))) & 15)

    pa6, pa11 = pin(6), pin(11)
    break_config = dict(BKBID=bool(words[timer+0x44] & (1 << 28)),
                        BKE=bool(words[timer+0x44] & (1 << 12)),
                        MOE=bool(words[timer+0x44] & (1 << 15)),
                        AOE=bool(words[timer+0x44] & (1 << 14)),
                        BIE=bool(words[timer+12] & (1 << 7)),
                        BKINE=bool(words[timer+0x60] & 1),
                        BKINP=bool(words[timer+0x60] & 512))
    flash_start = 0x080064E0
    flash = b''.join(words[address].to_bytes(4, 'little') for address in range(flash_start, flash_start+96, 4))
    expected = (PACKAGE / 'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin').read_bytes()[0x64E0:0x6540]
    assert flash == expected, 'Live SD instruction bytes differ from sealed build'
    (OUT / 'live_sd_instruction_readback.bin').write_bytes(flash)
    after = get_status('after_register_read')
    assert before['linux_boot_id'] == after['linux_boot_id']
    for key in ('firmware', 'retained_sequence', 'csr_raw', 'early_record_crc'):
        assert before['native_boot'][key] == after['native_boot'][key]
    assert after['native_boot']['native_tick_ms'] >= before['native_boot']['native_tick_ms']
    assert before['native_boot']['early_record_crc'] == after['native_boot']['early_record_crc']

    manifest = json.loads((PACKAGE / 'source_hashes.json').read_text(encoding='utf-8-sig'))
    changed = [name for name, digest in manifest.items()
               if hashlib.sha256((PACKAGE/name).read_bytes()).hexdigest() != digest]
    assert not changed
    report = dict(memory_read_only=True, commands=dict(START=0, CLEAR=0, ARM=0, RESET=0,
                  flash=0, halt=0, register_writes=0), PA6=pa6, PA11=pa11,
                  break_config=break_config, OPAMP_enable_bits=[bool(words[0x40010300+4*i]&1) for i in range(3)],
                  core_halted_at_read=bool(words[0xE000EDF0] & (1 << 17)),
                  installed_live_SD_code_matches_sealed_binary=True,
                  source_files_checked=len(manifest), changed_source_files=changed,
                  before_SD=before['mc_sd_live'], after_SD=after['mc_sd_live'],
                  native_uptime_before_ms=before['native_boot']['native_tick_ms'],
                  native_uptime_after_ms=after['native_boot']['native_tick_ms'],
                  boot_continuity_during_read_confirmed=True,
                  registers={hex(address): hex(value) for address, value in words.items()})
    assert not report['core_halted_at_read']
    (OUT / 'direct_register_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ['PA6','PA11','break_config','OPAMP_enable_bits',
          'core_halted_at_read','installed_live_SD_code_matches_sealed_binary','source_files_checked',
          'boot_continuity_during_read_confirmed','commands']}))


if __name__ == '__main__':
    main()
