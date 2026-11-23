"""Run compiled Cortex-M4 LSO and Motor Pilot transport on the PC."""
import json
import math
import struct
from hashlib import sha256

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import UC_MODE_MCLASS, UC_MODE_THUMB
from unicorn import arm_const as arm

from install_air56_lso_off_dwt import crc4, header
from prepare_air56_lso_timing_aspep import BASE, OUT, ROOT


NAME = 'ACIM-AIR56B2-LSO_FOC'
DWT = 0xE0001004
TIM1 = 0x40012C00
CORDIC = 0x40020C00
DMA = 0x40020400
RX = DMA + 0x1C
TX = DMA + 0x30
UART = 0x40004400
END = 0x0801FFF0
MCTL_SYNC = 0xA


class Firmware:
    def __init__(self, elfpath):
        self.cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        self.cpu.ctl_set_cpu_model(arm.UC_CPU_ARM_CORTEX_M4)
        self.cpu.mem_map(0x08000000, 0x20000)
        self.cpu.mem_map(0x10000000, 0x3000)
        self.cpu.mem_map(0x20000000, 0x8000)
        self.cpu.mem_map(0x40000000, 0x25000)
        self.cpu.mem_map(0xE0000000, 0x20000)
        with elfpath.open('rb') as stream:
            elf = ELFFile(stream)
            symbols = elf.get_section_by_name('.symtab').iter_symbols()
            self.sym = {s.name: int(s['st_value']) for s in symbols}
            for seg in elf.iter_segments():
                if seg['p_type'] == 'PT_LOAD' and seg['p_filesz']:
                    self.cpu.mem_write(int(seg['p_vaddr']), seg.data())
                    self.cpu.mem_write(int(seg['p_paddr']), seg.data())
        self.cpu.reg_write(arm.UC_ARM_REG_C1_C0_2, 0xF00000)
        self.cpu.reg_write(arm.UC_ARM_REG_FPEXC, 1 << 30)
        self.cpu.reg_write(arm.UC_ARM_REG_XPSR, 0x01000000)
        self.instructions = 0
        self.calculate_dwt = False
        self.cpu.hook_add(UC_HOOK_CODE, self.count)
        self.cpu.hook_add(UC_HOOK_MEM_READ, self.read_cycle_count, begin=DWT, end=DWT)
        self.cpu.hook_add(UC_HOOK_MEM_WRITE, self.cordic_result, begin=CORDIC + 4, end=CORDIC + 4)
        self.cpu.hook_add(UC_HOOK_MEM_WRITE, self.clear_uart, begin=UART + 0x20, end=UART + 0x20)
        self.cpu.hook_add(UC_HOOK_MEM_WRITE, self.clear_dma, begin=DMA + 4, end=DMA + 4)

    def put(self, address, value, fmt='I'):
        self.cpu.mem_write(address, struct.pack('<' + fmt, value))

    def get(self, address, fmt='I'):
        return struct.unpack('<' + fmt, self.cpu.mem_read(address, struct.calcsize('<' + fmt)))[0]

    def count(self, cpu, address, size, _):
        if self.calculate_dwt:
            self.instructions += 1

    def read_cycle_count(self, cpu, access, address, size, value, _):
        if self.calculate_dwt:
            self.put(address, self.instructions)

    def cordic_result(self, cpu, access, address, size, value, _):
        angle = (value & 0xffff) * math.tau / 65536
        def q15(x):
            return round(32767 * x) & 0xffff
        self.put(CORDIC + 8, q15(math.cos(angle)) | q15(math.sin(angle)) << 16)

    def clear_uart(self, cpu, access, address, size, value, _):
        self.put(UART + 0x1c, self.get(UART + 0x1c) & ~value)

    def clear_dma(self, cpu, access, address, size, value, _):
        clear_mask = value | (0xF0 if value & 0x10 else 0)
        self.put(DMA, self.get(DMA) & ~clear_mask)

    def call(self, name, *args):
        self.cpu.reg_write(arm.UC_ARM_REG_SP, self.sym['_estack'])
        self.cpu.reg_write(arm.UC_ARM_REG_LR, END | 1)
        for reg, value in zip((arm.UC_ARM_REG_R0, arm.UC_ARM_REG_R1, arm.UC_ARM_REG_R2, arm.UC_ARM_REG_R3), args):
            self.cpu.reg_write(reg, value)
        self.cpu.emu_start(self.sym[name] | 1, END, count=500_000)
        assert self.cpu.reg_read(arm.UC_ARM_REG_PC) == END, name
        return self.cpu.reg_read(arm.UC_ARM_REG_R0)

    def words(self, address, n):
        return struct.unpack('<' + 'I' * n, self.cpu.mem_read(address, 4 * n))

    def off_dwt_fixture(self):
        s = self.sym
        self.put(s['pACIM_LSO'], s['ACIM_LSO_Component_M1'])
        self.put(s['ACIM_LSO_Component_M1'] + 36, s['FOCVars'])
        self.put(TIM1 + 0x44, 0x1000)
        self.call('ACIM_LSO_Init', s['ACIM_LSO_Component_M1'], s['BusVoltageSensor_M1'])
        self.calculate_dwt = True
        for i in range(1, 65):
            self.put(s['uwTick'], i)
            self.call('AIR56_OffDwtService')
        self.calculate_dwt = False
        result = self.words(s['air56_off_dwt'], 133)
        assert result[:2] == (0x414c5331, 64) and result[4] == 0, result[:5]
        return result[5:69], result[69:]


def test_ccm_startup(elf):
    fw = Firmware(elf)
    sym = fw.sym
    start, end = sym['_sccmram'], sym['_eccmram']
    assert start == 0x10000000 and start < end <= start + 10240
    assert sym['_ebss'] < sym['_estack'] == 0x20005800
    assert 0x20000000 <= sym['rx_ring'] < sym['_ebss'] <= 0x20005800
    for name in ('ACIM_LSO_CalcAngle', 'ADC1_2_IRQHandler', 'TIM1_UP_TIM16_IRQHandler',
                 'TSK_HighFrequencyTask', 'AIR56_OffDwtService', 'R3_2_GetPhaseCurrents'):
        assert start <= sym[name] < end, (name, hex(sym[name]))
    size = end - start
    expected = fw.cpu.mem_read(sym['_siccmram'], size)
    fw.cpu.mem_write(start, bytes(size))
    fw.cpu.emu_start(sym['Reset_Handler'] | 1, sym['__libc_init_array'] & ~1, count=100_000)
    assert fw.cpu.reg_read(arm.UC_ARM_REG_PC) == (sym['__libc_init_array'] & ~1)
    assert fw.cpu.mem_read(start, size) == expected
    return size


def test_observer_replay(old, new):
    builds = [Firmware(old), Firmware(new)]
    peak = dict(current_A=0., flux_equivalent_A=0., speed_rad_s=0., field_rad=0.)
    # Simulate slowly varying q/d inputs in both directions and at battery limits.
    # The comparison feeds identical quantized inputs to both compiled kernels.
    points = [(0., 250), (0.9, 325), (5., 350), (-5., 325), (20., 325), (-50., 350)]
    for hz, bus in points:
        for fw in builds:
            s = fw.sym
            state = s['ACIM_LSO_Component_M1']
            fw.put(state + 36, s['FOCVars'])
            fw.put(s['BusVoltageSensor_M1'] + 6, round(bus * 65536 / 416), 'H')
            fw.call('ACIM_LSO_Init', state, s['BusVoltageSensor_M1'])
            fw.call('ACIM_LSO_Clear', state)
            fw.put(state + 68, .5, 'f')
            fw.put(state + 76, math.copysign(6.282, hz), 'f')

        for i in range(4096):
            t = i / 16000
            iq = .04 * math.sin(math.tau * 2 * t)
            id_ = .5 + .015 * math.cos(math.tau * 3 * t)
            vq = (math.tau * hz) * .5 * .49 + iq * 12.23
            vd = id_ * 12.23
            outputs = []
            for fw in builds:
                fc, state = fw.sym['FOCVars'], fw.sym['ACIM_LSO_Component_M1']
                fw.put(fc + 8, round(iq * 65536 * .04 * 2.1 / 3.3), 'h')
                fw.put(fc + 10, round(id_ * 65536 * .04 * 2.1 / 3.3), 'h')
                fw.put(fc + 18, round(vq * 32767 * math.sqrt(3) / bus), 'h')
                fw.put(fc + 20, round(vd * 32767 * math.sqrt(3) / bus), 'h')
                fw.call('ACIM_LSO_CalcAngle', state)
                outputs.append(tuple(fw.get(state + offset, 'f') for offset in (56, 60, 68, 84, 76)))
            error = [v - r for r, v in zip(*outputs)]
            assert all(map(math.isfinite, error)), (hz, i, outputs)
            peak['current_A'] = max(peak['current_A'], abs(error[0]), abs(error[1]))
            peak['flux_equivalent_A'] = max(peak['flux_equivalent_A'], abs(error[2]))
            peak['speed_rad_s'] = max(peak['speed_rad_s'], abs(error[3]))
            peak['field_rad'] = max(peak['field_rad'], abs(math.remainder(error[4], math.tau)))

    for key, cap in dict(current_A=5e-5, flux_equivalent_A=5e-5,
                         speed_rad_s=5e-4, field_rad=5e-4).items():
        assert peak[key] < cap, peak
    return dict(steady_input_traces=len(points), observer_steps=4096 * len(points), max_abs_delta=peak)


def mcp_frame(*words):
    payload = struct.pack('<' + 'H' * len(words), *words)
    return header(9 | len(payload) << 4) + payload


class Wire:
    def __init__(self, fw):
        self.fw = fw
        self.protocol = fw.sym['aspepOverUartA']
        self.mcp = fw.sym['MCP_Over_UartA']
        self.cycles = 0
        fw.put(fw.sym['SystemCoreClock'], 170_000_000)
        fw.call('ASPEP_start', self.protocol)
        assert fw.get(RX + 4) == 1024 and fw.get(RX) & 0x21 == 0x21
        assert fw.get(RX + 8) == UART + 0x24
        self.frames = []

    def inject(self, stream):
        fw = self.fw
        assert fw.get(RX) & 0x21 == 0x21
        left = fw.get(RX + 4)
        ring = fw.get(RX + 12)
        for b in stream:
            fw.put(ring + 1024 - left, b, 'B')
            left = left - 1 or 1024
        fw.put(RX + 4, left)

    def poll(self, elapsed=85_000):
        self.cycles = (self.cycles + elapsed) & 0xffffffff
        fw = self.fw
        fw.put(DWT, self.cycles)
        fw.call('UASPEP_Poll', self.protocol)
        length_ptr = self.mcp + 12
        received = fw.call('ASPEP_RXframeProcess', self.protocol, length_ptr)
        if received:
            assert fw.get(length_ptr, 'H') >= 2
            fw.put(self.mcp + 4, received)
            assert fw.call('ASPEP_getBuffer', self.protocol, self.mcp + 8, MCTL_SYNC) == 1
            fw.call('MCP_ReceivedPacket', self.mcp)
            response = fw.get(self.mcp + 8)
            size = fw.get(self.mcp + 14, 'H')
            assert fw.call('ASPEP_sendPacket', self.protocol, response, size, MCTL_SYNC) == 0
        if not fw.get(TX) & 1:
            return None
        packet = bytes(fw.cpu.mem_read(fw.get(TX + 12), fw.get(TX + 4)))
        fw.put(TX, fw.get(TX) & ~1)
        fw.call('ASPEP_HWDataTransmittedIT', self.protocol)
        word, = struct.unpack_from('<I', packet)
        assert crc4(word, 8) == 0
        self.frames.append(packet.hex())
        return word & 0xf, packet[4:], word & 0x0fffffff

    def send(self, packet):
        self.inject(packet)
        return self.poll()

    def version(self):
        result = self.send(mcp_frame(0x01))
        assert result is not None and result[0] == 10 and result[1] == b'\x01\x00\x00\x00\x00', result


def test_uart(elf):
    fw = Firmware(elf)
    wire = Wire(fw)
    first = wire.send(header(5 | (1 << 8) | (1 << 14)))
    assert first[0] == 5
    assert wire.send(header(first[2])) == first
    assert wire.send(header(6 | (1 << 12)))[0] == 6
    for _ in range(360):
        wire.version()
    identity = wire.send(mcp_frame(0x11, (3 << 6) | (4 << 3) | 1))
    assert identity[0] == 10 and b'AIR56B2' in identity[1] and identity[1][-1] == 0

    # Negotiated 64-byte ceiling. MCP GET of one register is itself enough, and
    # repeated valid registers let the request exercise the full receive span.
    reply = wire.send(mcp_frame(0x11, *([(1 << 6) | (1 << 3) | 1] * 31)))
    assert reply[0] == 10 and len(reply[1]) == 32 and reply[1][-1] == 0, reply

    # Live MCP version was originally received only this way.
    split = mcp_frame(0x01)
    assert wire.send(split[:4]) is None
    for _ in range(8):
        assert wire.poll() is None
    assert wire.send(split[4:])[0] == 10

    for malformed in (bytes([split[0] ^ 0x40]) + split[1:],
                      header(9 | (1 << 4)) + b'\x01', header(9 | (200 << 4))):
        nack = wire.send(malformed)
        assert nack and nack[0] not in (5, 6, 10), nack
        assert wire.poll() is None
        wire.version()

    assert wire.send(split[:5]) is None
    for _ in range(52):
        assert wire.poll() is None
    wire.version()

    # A wire error during an incomplete packet must not complete an old command.
    assert wire.send(split[:5]) is None
    fw.put(UART + 0x1c, 1 << 3)
    assert wire.send(split[5:]) is None
    assert wire.poll() is None
    wire.version()

    # A delayed consumer can no longer infer the true position modulo the ring.
    wire.inject(split * 180)
    assert wire.poll(1_000_000) is None
    assert wire.poll() is None
    wire.version()

    # DMA transfer fault restarts the channel, waits for the next clean boundary.
    fw.put(DMA, 1 << 7)
    assert wire.poll() is None and fw.get(RX + 4) == 1024
    assert wire.poll() is None
    wire.version()
    assert fw.get(TIM1 + 0x44) & 0x8000 == 0
    return dict(baud=1843200, consecutive_version_roundtrips=360, wire_frames=len(wire.frames),
                motor=identity[1].split(b',')[0].decode('ascii'), wrap_test=True, max_negotiated_payload=64,
                invalid_header_length_and_crc=True, partial_timeout=True, uart_overrun_recovery=True,
                dma_transfer_error_recovery=True, late_scheduler_recovery=True,
                physically_tested=False, pin_output_enabled=False)


def main():
    old = BASE / 'image' / (NAME + '.elf')
    new = OUT / 'image' / (NAME + '.elf')
    old_all, old_lso = Firmware(old).off_dwt_fixture()
    new_all, new_lso = Firmware(new).off_dwt_fixture()
    ccm_bytes = test_ccm_startup(new)
    observer_replay = test_observer_replay(old, new)
    baseline = BASE / 'hardware_install_r2/DWT_0.bin'
    measured = struct.unpack('<133I', baseline.read_bytes())
    assert measured[:2] == (0x414c5331, 64)
    assert all(old_n > new_n for old_n, new_n in zip(old_all, new_all))
    uart = test_uart(new)
    preserved = {}
    for folder in ('hardware_install_r1', 'hardware_install_r2',
                   'motor_pilot_protocol_off_r1', 'motor_pilot_protocol_off_r2', 'image'):
        for path in sorted((BASE / folder).rglob('*')):
            if path.is_file():
                preserved[path.relative_to(ROOT).as_posix()] = sha256(path.read_bytes()).hexdigest()
    report = dict(test_mode='compiled Cortex-M4 on PC; instruction counts, no target cycle claim',
                  dwt_budget=4000, adc_deadline_us=2000, cases=64, iterations_per_case=8,
                  previous_board_DWT_max=measured[2],
                  previous_observer_DWT_max=measured[3],
                  previous_compiled_full_max=max(old_all), candidate_compiled_full_max=max(new_all),
                  previous_compiled_LSO_max=max(old_lso), candidate_compiled_LSO_max=max(new_lso),
                  full_instruction_reduction_min=min(a - b for a, b in zip(old_all, new_all)),
                  ccm_bytes=ccm_bytes, ccm_reset_copy=True, observer_replay=observer_replay,
                  per_case=list(zip(measured[5:69], old_all, new_all, old_lso, new_lso)),
                  Motor_Pilot=uart, installed=False, hardware_commands=0)
    (OUT / 'timing_aspep_PC.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    (OUT / 'preserved_lso_captures_sha256.json').write_text(json.dumps(preserved, indent=2) + '\n', encoding='utf8')
    verification = OUT / 'verification.json'
    engineering = json.loads(verification.read_text(encoding='utf8'))
    engineering['serial'] = 'Motor Pilot ASPEP over circular DMA on USART2 at 1843200, verified in CPU emulator'
    engineering['old_NIS_policy'] = 'Archived experimental EKF has threshold 25. ST LSO does not compute NIS.'
    engineering['offline_candidate'] = 'timing_aspep_PC.json'
    verification.write_text(json.dumps(engineering, indent=2) + '\n', encoding='utf8')
    report.pop('per_case')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
