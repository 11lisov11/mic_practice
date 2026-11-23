"""Install the LSO reference on the existing Nucleo with J1 off. No motor commands."""

import argparse
import json
import struct
import subprocess
import time
from pathlib import Path

import serial
from serial.tools import list_ports
from elftools.elf.elffile import ELFFile

from install_bkin_boot_armed_pair import PROGRAMMER, STLINK_SERIAL
from install_foc_handover_feedback_release import OUT as INSTALLED, NEW as INSTALLED_PAIR
from install_foc_handover_feedback_release import read_json, save, sha, release
from prepare_air56_lso_off_dwt import OUT, BASE
from prepare_air56_st_lso_reference import NAME, ROOT
from probe_native_programming_state import inspect_layout, programmed_hex_image
from run_foc_handover_feedback_trial import verify_release as verify_previous
from wifi_stop_tail_probe import parse_registers


SWD = [str(PROGRAMMER),'-c','port=SWD','mode=HotPlug','sn='+STLINK_SERIAL]
CRC4 = (0,7,14,9,11,12,5,2,1,6,15,8,10,13,4,3)


def crc4(word, nibbles):
    crc = 0
    for shift in range(0,4*nibbles,4):
        crc = CRC4[crc ^ ((word>>shift)&15)]
    return crc


def header(word):
    assert word >> 28 == 0
    return struct.pack('<I',word | crc4(word,7)<<28)


def probe_motor_pilot(port, *, split_payload=False):
    """Standard ASPEP beacon and ping, followed only by MCP identity/GET."""
    recorded = []
    with serial.Serial(port,1843200,timeout=1.5,write_timeout=1.5) as conn:
        conn.reset_input_buffer()

        def exchange(word, payload=b''):
            wire = header(word)+payload
            if split_payload and payload:
                conn.write(wire[:4])
                conn.flush()
                time.sleep(.004)
                conn.write(payload)
            else:
                conn.write(wire)
            conn.flush()
            data = conn.read(4)
            if len(data)!=4:
                raise RuntimeError(f'No complete ASPEP reply to {wire.hex()}')
            response, = struct.unpack('<I',data)
            if crc4(response,8):
                raise RuntimeError(f'ASPEP header CRC error: {data.hex()}')
            if response&15 == 10:
                length = (response>>4)&0x1fff
                assert 0<length<=64, length
                body = conn.read(length)
                assert len(body)==length,'Truncated MCP reply'
            else:
                body = b''
            recorded.append(dict(tx=wire.hex(),rx=(data+body).hex()))
            return response&0x0fffffff,body

        beacon = 5 | (1<<8) | (1<<14)  # Controller offers two 32-byte sync blocks.
        reply,_ = exchange(beacon)
        assert reply&15 == 5 and not reply&0x80,'Unexpected beacon or data CRC'
        assert exchange(reply)[0]==reply,'ASPEP negotiation did not settle'
        ping,_ = exchange(6 | (1<<12))
        assert ping&15==6 and (ping>>12)&0xffff==1 and ping&0x30==0x30

        def mcp_read(*payload):
            command = struct.pack('<'+'H'*len(payload),*payload)
            kind,body = exchange(9|(len(command)<<4),command)
            assert kind&15==10 and body[-1]==0,(kind,body.hex())
            return body[:-1]

        # Motor ID 1. MCP GET_DATA_ELEMENT is 0x10, not a set or start.
        version = mcp_read(0x01)
        assert len(version)==4 and version[0]==1, version.hex()
        state, = mcp_read(0x11, (1<<6)|(1<<3)|1)
        volts, = struct.unpack('<H',mcp_read(0x11,(22<<6)|(2<<3)|1))
        status, = struct.unpack('<I',mcp_read(0x11,(3<<3)|1))
        motor = mcp_read(0x11,(3<<6)|(4<<3)|1).rstrip(b'\x00').decode('ascii')
        assert volts<20 and 'AIR56B2' in motor and state in (0,10,11),(volts,state,motor)
    return dict(port=port,baud=1843200,ASPEP_established=True,MCP_version=1,motor=motor,
                state=state,bus_V=volts,fault_word=status,wire=recorded,
                split_payload=split_payload,only_read_commands=True)


def package_check():
    _,protected = verify_previous()
    for out in (BASE,OUT):
        package = read_json(out/'verification.json')
        assert package['passed'] and not package['installed'] and package['hardware_commands']==0
        release.base.verify_inventory(package['images_sha256'],out/'image')
    recorded = read_json(OUT/'preserved_inputs_sha256.json')
    release.base.verify_inventory(recorded,ROOT)
    protected.update(recorded)
    elf = OUT/'image'/f'{NAME}.elf'
    with elf.open('rb') as stream:
        sym = {x.name:x for x in ELFFile(stream).get_section_by_name('.symtab').iter_symbols()}
        assert sym['air56_off_dwt']['st_size']==4*(5+128)
        assert 'AIR56_OffDwtService' in sym and 'AIR56_OffDwtReady' in sym
    for payload in (5, 0x880005, 6, 0x1009, 0xA):
        assert crc4(int.from_bytes(header(payload),'little'),8)==0
    return protected


def install():
    protected = package_check()
    vcp = [p.device for p in list_ports.comports()
           if p.vid==0x0483 and p.pid==0x374e and p.serial_number==STLINK_SERIAL]
    assert len(vcp)==1,'Expected the exact Nucleo ST-LINK virtual COM port'
    previous = sorted(OUT.glob('hardware_install_r[0-9]*'))
    for attempt in previous:
        assert not (attempt/'programming_intent.json').exists()
        assert read_json(attempt/'report.json')['programming_attempts']==0
    out = OUT/f'hardware_install_r{len(previous)+1}'
    out.mkdir()
    report = dict(passed=False,programming_attempts=0,START=0,CLEAR=0,ARM=0)

    def run(command, name, timeout=25):
        proc = subprocess.run(command,capture_output=True,text=True,errors='replace',timeout=timeout)
        (out/(name+'.log')).write_text(proc.stdout+proc.stderr,encoding='utf8')
        proc.check_returncode()
        return proc.stdout

    def read(address, count, name):
        file = out/(name+'.bin')
        run(SWD+['-u',hex(address),str(count),str(file)],name)
        raw=file.read_bytes()
        assert len(raw)==count
        return raw

    def safe(elf, tag):
        symbols, layout = inspect_layout(elf)
        base, tick = symbols['BusVoltageSensor_M1'], symbols['uwTick']
        reg = parse_registers(run(SWD+['-r32',hex(base),'12','-r32',hex(tick),'4',
                                       '-r32','0x40012c0c','8','-r32','0x40012c44','4',
                                       '-r32','0x48000010','4'],tag))
        raw = b''.join(struct.pack('<I',reg[base+idx]) for idx in (0,4,8))
        scale, = struct.unpack_from('<H',raw,layout['ConversionFactor'])
        digit, = struct.unpack_from('<H',raw,layout['AvBusVoltage_d'])
        volts=scale*digit/65536
        bdtr=reg[0x40012c44]
        assert scale==416 and 0<=volts<20 and bdtr&0x1000 and not bdtr&0xc000
        return dict(bus_V=volts,tick=reg[tick],MOE=False,AOE=False,BKE=True,BKF=(bdtr>>16)&15,
                    BIE=bool(reg[0x40012c0c]&128),PA6_HIGH=bool(reg[0x48000010]&64),
                    TIM1_SR=reg[0x40012c10]), symbols

    try:
        old = INSTALLED/'release'/f'nucleo_{INSTALLED_PAIR[1]}_if_foc.elf'
        expected_old = INSTALLED/'release'/f'nucleo_{INSTALLED_PAIR[1]}_expected_readback.bin'
        original = read(0x08000000,128*1024,'2202_full_flash_before')
        assert original[:expected_old.stat().st_size]==expected_old.read_bytes()
        read(0x20000000,32768,'2202_RAM_before')
        report['old_flash_preserved']=True
        report['old_ram_preserved']=True
        first,_ = safe(old,'before_safety_1')
        time.sleep(.15)
        second,_ = safe(old,'before_safety_2')
        assert 100<=((second['tick']-first['tick'])&0xffffffff)<5000
        report['before']=second
        image = OUT/'image'/NAME
        hex_file=image.with_suffix('.hex')
        expected,holes=programmed_hex_image(hex_file,image.with_suffix('.bin').read_bytes())
        assert 0<len(expected)<=128*1024
        report['programming_attempts']=1
        save(out/'programming_intent.json',report)
        run([str(PROGRAMMER),'-c','port=SWD','mode=UR','sn='+STLINK_SERIAL,
             '-w',str(hex_file),'-v','-rst'],'program_once',75)
        actual=read(0x08000000,len(expected),'LSO_flash_readback')
        assert actual==expected,'LSO Flash readback differs'
        report.update(readback_verified=True,readback_sha256=sha(out/'LSO_flash_readback.bin'),
                      readback_bytes=len(actual),erased_padding_offsets=holes)
        status,symbols=safe(image.with_suffix('.elf'),'after_safety')
        assert status['BKF']==9
        report['after']=status
        report['DWT'] = read_dwt(read,symbols)
        try:
            report['motor_pilot_protocol']=probe_motor_pilot(vcp[0])
        except (AssertionError,OSError,RuntimeError,ValueError,serial.SerialException) as error:
            report['motor_pilot_protocol_error']=repr(error)
        report['final'],_=safe(image.with_suffix('.elf'),'final_safety')
        report.update(passed=report['DWT']['passed'] and 'motor_pilot_protocol' in report)
    except Exception as error:
        report['error']=repr(error)
    finally:
        release.base.verify_inventory(protected,ROOT)
        report['preserved_files_verified']=len(protected)
        save(out/'report.json',report)
        save(out/'sha256.json',{p.name:sha(p) for p in out.iterdir() if p.is_file()})
    print(json.dumps({k:v for k,v in report.items() if k!='erased_padding_offsets'}))
    return 0 if report['passed'] else 1


def read_dwt(read, symbols):
    for attempt in range(5):
        raw=read(symbols['air56_off_dwt'],4*(5+128),f'DWT_{attempt}')
        identity,cases,maximum,lso,failures,*steps=struct.unpack('<133I',raw)
        assert identity==0x414c5331
        if cases==64:
            assert maximum==max(steps[:64]) and lso==max(steps[64:]) and min(steps)>0
            return dict(cases=cases,iterations_per_case=8,max_cycles=maximum,max_lso_cycles=lso,
                        failures=failures,passed=failures==0 and maximum<=4000)
        time.sleep(.2)
    raise RuntimeError(f'OFF DWT incomplete: {cases}/64')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirmed-j1-off',action='store_true')
    if parser.parse_args().confirmed_j1_off:
        raise SystemExit(install())
    print(json.dumps(dict(package_verified=True,preserved=len(package_check()),hardware_commands=0)))
