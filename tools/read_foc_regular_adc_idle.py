"""Read-only RAM/BDTR snapshot; never read ADC DR or change conversion flags."""
import hashlib
import argparse
import json
import struct
import subprocess
import time
import urllib.request
from pathlib import Path
from elftools.elf.elffile import ELFFile
import prepare_foc_regular_adc_fix as p
from install_bkin_boot_armed_pair import PROGRAMMER, STLINK_SERIAL
from probe_native_programming_state import inspect_layout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True)
    out = parser.parse_args().outdir.resolve()
    assert p.OUT in out.parents
    out.mkdir(exist_ok=False)
    elf = p.OUT / 'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
    syms, bus_layout = inspect_layout(elf)
    layouts = []
    with elf.open('rb') as stream:
        e = ELFFile(stream)
        for cu in e.get_dwarf_info().iter_CUs():
            for die in cu.iter_DIEs():
                a = die.attributes.get('DW_AT_name')
                if die.tag == 'DW_TAG_typedef' and a and a.value == b'RegConv_t':
                    t = die.get_DIE_from_attribute('DW_AT_type')
                    layouts.append({m.attributes['DW_AT_name'].value.decode():
                                    int(m.attributes['DW_AT_data_member_location'].value)
                                    for m in t.iter_children() if m.tag == 'DW_TAG_member'})
    assert layouts and all(x == layouts[0] for x in layouts)
    layout = layouts[0]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def live():
        with opener.open('http://192.168.1.138:8080/api/status', timeout=8) as response:
            obj = json.load(response)
        assert obj['ok']
        s = obj['data']
        assert (s['fw_build'], s['mc_fw_build']) == p.NEW
        assert s['state'] == 'SAFE' and s['pwm'] == 0 and s['vdc'] <= 20
        assert s['run_id'] == 0 and s['hmi_hv_armed'] == 0
        return obj

    def save(name, obj):
        p.write(out/name, json.dumps(obj, ensure_ascii=False, indent=2)+'\n')

    def read(addr, size, name):
        path = out / (name+'.bin')
        cmd = [str(PROGRAMMER), '-c', 'port=SWD', 'mode=HotPlug', 'sn='+STLINK_SERIAL,
               '-u', hex(addr), str(size), str(path)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        p.write(out/(name+'.log'), r.stdout+r.stderr)
        r.check_returncode()
        data = path.read_bytes()
        assert len(data) == size
        return data

    before = live()
    save('before.json', before)
    rows = []
    for i in range(2):
        bdtr = struct.unpack('<I', read(0x40012c44, 4, f'bdtr_{i}'))[0]
        assert not (bdtr & 0x8000)
        ram = read(0x20000000, 32768, f'SRAM_{i}')

        def value(symbol, fmt, offset=0):
            return struct.unpack_from(fmt, ram, syms[symbol]-0x20000000+offset)[0]

        conversions = {}
        for name in ('VbusRegConv_M1', 'TempRegConv_M1'):
            conversions[name] = {
                key: value(name, fmt, layout[key])
                for key,fmt in (('regADC','<I'),('samplingTime','<I'),
                                ('channel','<B'),('data','<H'),('id','<B'))}
            conversions[name]['right_aligned_12bit'] = conversions[name]['data'] >> 4
        n = value('RCM_conversion_nb', '<B')
        row = dict(tick=value('uwTick','<I'), MOE=False,
                   registered=n, fault=value('rcm_fault','<H'),
                   pending=value('rcm_pending','<I'),
                   valid=[value('rcm_valid','<B',j) for j in range(n)],
                   stamps=[value('rcm_stamp','<I',4*j) for j in range(n)],
                   conversions=conversions)
        assert n == 2 and row['fault'] == 0 and row['pending'] == 0
        assert row['valid'] == [1,1]
        assert conversions['VbusRegConv_M1']['channel'] == 2
        assert conversions['TempRegConv_M1']['channel'] == 8
        # The application uses ADC_DATAALIGN_LEFT. RCM keeps the original
        # 16-bit representation used by the bus/temperature MCSDK consumers.
        assert p.read(p.OUT/'nucleo/Src/main.c').count('Init.DataAlign = ADC_DATAALIGN_LEFT;') == 2
        assert all(c['regADC'] == 0x50000000 and 0 <= c['data'] <= 65520 and c['data']&15 == 0
                   for c in conversions.values())
        rows.append(row)
        time.sleep(.25)
    assert rows[1]['tick'] > rows[0]['tick']
    assert all(a != b for a,b in zip(rows[0]['stamps'], rows[1]['stamps']))
    after = live()
    save('after.json', after)
    report = dict(passed=True, pair=list(p.NEW), rows=rows, layout_from_DWARF=layout,
                  regular_data_alignment='12bit LEFT in 16bit, unchanged MCSDK representation',
                  RAM_snapshot_not_atomic=True, exact_conversion_latency_not_measured=True,
                  new_RUN_schedule_not_exercised=True, read_ADC_DR=False,
                  source='ST-Link HotPlug RAM and TIM1 BDTR reads, plus HTTP GET',
                  START=0, CLEAR=0, ARM=0, RESET=0, flash=0, halt=0)
    save('report.json', report)
    save('files_sha256.json', {f.name:hashlib.sha256(f.read_bytes()).hexdigest()
                             for f in out.iterdir() if f.is_file()})
    print(json.dumps(report))


if __name__ == '__main__':
    main()
