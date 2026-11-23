"""Verify the sealed LSO run package on the PC and on compiled Cortex-M4 code."""
import json
import importlib.util
import shutil
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
from pathlib import Path

from prepare_air56_lso_uno_capture import LSO, NEW, OUT, ROOT, release
from read_air56_lso_capture import MAGIC, ROW, crc32c, decode, page_data
from verify_air56_lso_timing_aspep import DWT, TIM1, Firmware, test_ccm_startup, test_uart
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as arm

DMA1 = 0x40020000
RX = DMA1 + 0x1c
TX = DMA1 + 8
GPIOA = 0x48000000
USART1 = 0x40013800


class UnoExchange:
    def __init__(self, elf, peer_build=None):
        fw = self.fw = Firmware(elf)
        self.s = fw.sym
        self.mc = self.s['Mci']
        self.trace = self.s['air56_lso_trace']
        self.seq = 0
        self.now = 0
        self.peer_build = NEW[1] if peer_build is None else peer_build
        fw.cpu.mem_map(GPIOA, 0x1000)
        fw.put(GPIOA + 0x10, 0x40)
        fw.put(TIM1 + 0x44, 0x91000)
        fw.put(TIM1 + 0x0c, 128)
        fw.put(TIM1 + 0x60, 0x201)
        fw.put(RX + 4, 512)
        fw.put(self.s['bMCBootCompleted'], 1, 'B')
        fw.put(self.mc, self.s['SpeednTorqCtrlM1'])
        self.set_vbus(320)
        for name in ('PQD_CalcElMotorPower', 'R3_2_SwitchOffPWM', 'FOC_Clear', 'PQD_Clear'):
            address = self.s[name] & ~1
            fw.cpu.hook_add(UC_HOOK_CODE, self.stub, user_data=name, begin=address, end=address)
        self.poll()

    def stub(self, cpu, address, size, name):
        if name == 'R3_2_SwitchOffPWM':
            self.fw.put(TIM1 + 0x44, self.fw.get(TIM1 + 0x44) & ~0x8000)
        cpu.reg_write(arm.UC_ARM_REG_PC, cpu.reg_read(arm.UC_ARM_REG_LR))

    def set_vbus(self, volts):
        self.fw.put(self.s['BusVoltageSensor_M1'] + 6, (volts*65536+415)//416, 'H')

    def poll(self, advance=1):
        fw = self.fw
        self.now += advance
        fw.put(self.s['uwTick'], self.now)
        fw.put(DWT, self.now*170000)
        fw.put(self.s['hMFTaskCounterM1'], 1, 'H')
        fw.call('MC_Scheduler')

    def inject(self, packet):
        fw = self.fw
        left = fw.get(RX+4)
        for b in packet:
            fw.put(self.s['air56_uart_ring'] + 512 - left, b, 'B')
            left = left - 1 or 512
        fw.put(RX+4, left)

    def send(self, mode=0, flags=0, params=b'', damaged=False):
        fw = self.fw
        packet = bytearray(43)
        packet[:6] = bytes((0xaa, 0x55, 3, flags, mode, self.seq))
        self.seq = (self.seq + 1) & 255
        packet[6:6+len(params)] = params
        struct.pack_into('<I', packet, 39, crc32c(packet[:39]) ^ bool(damaged))
        self.inject(packet)
        self.poll()
        length = fw.get(TX+4)
        if not length:
            return []
        assert length in (86,129), length
        response = bytes(fw.cpu.mem_read(self.s['air56_uart_reply'], length))
        fw.put(TX+4, 0)
        frames = [response[i:i+43] for i in range(0,length,43)]
        assert frames[0][4] == packet[5]
        assert all(crc32c(frame[:39]) == int.from_bytes(frame[39:], 'little') for frame in frames)
        assert int.from_bytes(frames[0][23:27], 'little') == self.peer_build
        assert frames[1][2:6] == b'\xe4\x04\x02\x02'
        return frames

    def seed_qualification(self):
        self.fw.put(self.s['air56_off_dwt'] + 4, 64)
        self.fw.put(self.s['air56_off_dwt'] + 8, 2360)

    def qualify_link_and_bus(self):
        self.seed_qualification()
        for i in range(3511):
            if i % 50 == 0:
                reply = self.send()
                assert reply[0][29] & 0xD0 == 0xD0
            else:
                self.poll()
        assert reply[1][36] & 1 and reply[1][38] == 64
        final = self.send()
        assert final[0][29] & 32
        return final[1]

    def start(self):
        reply = self.send(6, 1, struct.pack('<I', 5000))
        return reply and int.from_bytes(reply[1][31:32], 'little') == 1

    def emulate_running(self):
        fw = self.fw
        fw.put(self.mc+25, 6, 'B')  # RUN
        fw.put(TIM1+0x44, fw.get(TIM1+0x44)|0x8000)
        fw.put(self.s['air56_run_started'], 1, 'B')
        fw.put(self.s['air56_start_ms'], self.now)

    def seed_rows(self):
        fw = self.fw
        fw.put(self.trace+8, 2)
        fw.put(self.trace+24, 3100)
        fw.put(self.trace+36, 320)
        raw = ROW.pack(1700000, 300, -200, 340, 220, 160, 3040) + \
              ROW.pack(3400000, -200, 250, 320, 300, 200, 3100)
        fw.cpu.mem_write(self.trace+56, raw)
        return raw


def test_uno(elf, peer_build=None):
    link = UnoExchange(elf, peer_build)
    for _ in range(3):
        assert link.send()
    assert not link.start()
    assert not link.fw.get(link.trace)
    capabilities = link.qualify_link_and_bus()
    assert link.fw.call('MCI_StartMotor',link.mc) == 0  # no MCP / button start

    link.fw.put(GPIOA+0x10, 0)
    assert not link.start()
    assert not link.fw.get(link.trace)
    link.fw.put(GPIOA+0x10, 0x40)
    assert link.send()
    assert link.start()
    assert link.fw.get(link.trace) == MAGIC
    assert link.fw.get(link.mc+14,'h') == 50
    link.emulate_running()
    raw = link.seed_rows()
    assert len(link.send(6,1,struct.pack('<I',5000)))==2  # never export during PWM

    # Run the actual firmware hard deadline and stop path; emulate ADC outputs
    # only as register state, no peripheral calls on the bench.
    fw = link.fw
    start = fw.get(link.trace+12)
    while link.now < start+4998:
        if (link.now-start) % 50 == 0:
            assert link.send(6,1,struct.pack('<I',5000))[0][3]&1
        else:
            link.poll()
    fw.put(link.s['uwTick'], start+4999)
    fw.put(link.s['air56_last_packet_ms'], start+4999)
    fw.put(link.mc+25, 20, 'B')  # WAIT_STOP_MOTOR has no additional vendor work
    fw.call('TSK_MediumFrequencyTaskM1')
    assert fw.get(link.trace+4) == 1 and fw.get(TIM1+0x44)&0x8000
    fw.put(link.s['uwTick'], start+5000)
    fw.call('TSK_MediumFrequencyTaskM1')
    assert fw.get(link.trace+4) == 0 and fw.get(link.trace+20) == 1
    assert fw.get(TIM1+0x44)&0x8000 == 0
    link.now=start+5000
    fw.put(link.s['air56_uart_poll_cycles'],link.now*170000)
    meta_reply=link.send()
    epoch,meta=page_data(meta_reply[2],0)
    data_reply=link.send(8,0,struct.pack('<BBIBB',7,0,1,1,0xa6))
    _,page=page_data(data_reply[2],1,epoch)
    assert page==raw
    report,_=decode(meta+page)
    assert report['elapsed_ms']==5000 and report['max_cycles']==3100
    frozen=bytes(fw.cpu.mem_read(link.trace,56+2*16))
    fw.put(link.mc+25,0,'B')
    assert not link.start()
    assert bytes(fw.cpu.mem_read(link.trace,len(frozen)))==frozen

    cable=UnoExchange(elf, peer_build)
    cable.qualify_link_and_bus()
    assert cable.start()
    cable.emulate_running()
    for _ in range(299): cable.poll()
    assert cable.fw.get(TIM1+0x44)&0x8000
    cable.poll()
    assert cable.fw.get(cable.trace+20)==3
    assert not (cable.fw.get(TIM1+0x44)&0x8000)

    damage=UnoExchange(elf, peer_build)
    damage.qualify_link_and_bus()
    assert damage.start()
    damage.emulate_running()
    assert not damage.send(6,1,struct.pack('<I',5000),damaged=True)
    assert damage.fw.get(damage.trace+20)==3
    assert not (damage.fw.get(TIM1+0x44)&0x8000)

    adc=UnoExchange(elf, peer_build)
    adc.qualify_link_and_bus()
    assert adc.start()
    adc.emulate_running()
    adc.fw.put(adc.s['air56_adc_stamp'], 100)
    adc.fw.put(DWT, 340099)
    adc.fw.call('AIR56_LsoWatchAdc')
    assert adc.fw.get(TIM1+0x44)&0x8000
    adc.fw.put(DWT, 340100)
    adc.fw.call('AIR56_LsoWatchAdc')
    assert not (adc.fw.get(TIM1+0x44)&0x8000)

    estop=UnoExchange(elf, peer_build)
    estop.qualify_link_and_bus()
    assert estop.start()
    estop.emulate_running()
    estop.send(0,2)
    assert estop.fw.get(estop.trace+20)==5
    assert not (estop.fw.get(TIM1+0x44)&0x8000)
    return dict(Uno_UART3=True, frequency_millihz=5000, power_ready_held_ms=3500,
                SD_LOW_blocks_start=True, other_MCP_start_rejected=True, native_auto_stop_ms=5000,
                link_loss_cuts_PWM=True, corrupt_frame_cuts_PWM=True, estop_cuts_PWM=True,
                adc_2ms_guard_verified=True,
                read_during_pwm_blocked=True, captured_pages_verified=True, one_shot_preserved=True), capabilities


def test_ui(scratch, caps):
    raw = ','.join(str(byte) for byte in caps)
    source = scratch/'wire.cpp'
    exe = scratch/'wire.exe'
    source.write_text('''#include <cassert>
#include "research_wire.h"
#include "multi_command.h"
int main() {
    uint8_t frame[UV3_FRAME] = {''' + raw + '''};
    xp_receiver rx = {};
    assert(xp_receive(&rx,frame,2026112302U,true,1));
    assert(rx.caps==2 && rx.selected==2 && rx.timing_cases==64);
    assert(ma_wire_mode(rx.selected)==6);
    frame[4]=15; uv3_seal(frame);
    assert(!xp_receive(&rx,frame,2026112302U,true,2));
}
''',encoding='utf8')
    subprocess.run(['g++','-std=c++17','-O2','-I',str(OUT/'UNOQ_MOTOR'),str(source),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)

    path = OUT/'web_hmi/server.py'
    spec = importlib.util.spec_from_file_location('air56_lso_web_check', path)
    web = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = web
    spec.loader.exec_module(web)
    view = web.with_research_suite(dict(zip(('fw_build','mc_fw_build'),NEW)) |
             dict(research_native_valid=1,research_native_caps=2,algorithm_selected=2,
                  algorithm_qualification=128,foc_experiment_flags=1,foc_timing_fault=0))
    assert [a['id'] for a in view['research_algorithms'] if a['hardware_ready']] == ['FOC_FIXED']
    assert web.AppState.trial_command_check(None,'LSO PAGE 256')[0]
    assert not web.AppState.trial_command_check(None,'LSO PAGE 257')[0]
    return True


def main():
    image = OUT/'image/ACIM-AIR56B2-LSO_FOC.elf'
    old = LSO/'image/ACIM-AIR56B2-LSO_FOC.elf'
    new = Firmware(image)
    old_all,_ = Firmware(old).off_dwt_fixture()
    case_counts,lso_counts = new.off_dwt_fixture()
    ccm = test_ccm_startup(image)
    memory = new.sym['_estack']-new.sym['_ebss']
    assert memory >= 3072
    uno, caps = test_uno(image)
    pilot = test_uart(image)
    uno_dir = OUT/'build/uno'
    built = release.base.read_json(uno_dir/'unoq_mcsdk_scalar.build-manifest.json')
    assert built['firmware_build_id']==NEW[0]
    assert release.base.read_json(uno_dir/'llext-check.json')['pass']
    release.base.verify_inventory({it['file']:it['sha256'].lower() for it in built['artifacts']}, uno_dir)
    protected = release.base.read_json(OUT/'preserved_inputs_sha256.json')
    release.base.verify_inventory(protected, ROOT)
    assert (OUT/'Inc/air56_st_lso_limits.h').read_bytes()==(LSO/'Inc/air56_st_lso_limits.h').read_bytes()
    with TemporaryDirectory() as scratch:
        scratch = Path(scratch)
        exe = scratch/'capture.exe'
        subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I',str(OUT/'Inc'),
                        str(ROOT/'tools/air56_lso_capture_selftest.c'),'-o',str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
        gui = test_ui(scratch, caps)
    shutil.copyfile(uno_dir/'UNOQ_MOTOR.ino.elf-zsk.bin',OUT/'image/UNOQ-LSO_CAPTURE.elf-zsk.bin')
    report = dict(passed=True, pair=NEW, installed=False, hardware_commands=0,
                  DWT_limit=4000, ADC_age_limit_us=2000, preserved_files=len(protected),
                  OFF_emulated_cases=len(case_counts), OFF_instructions_baseline_max=max(old_all),
                  OFF_instructions_capture_max=max(case_counts), OFF_LSO_max_instructions=max(lso_counts),
                  actual_target_DWT_pending=True, ccm_bytes=ccm, remaining_ram_before_stack=memory,
                  host_capture_samples=80000, host_capture_windows=500,
                  Uno_capabilities_and_HMI_verified=gui,
                  web_hmi_sha256=release.base.sha(OUT/'web_hmi/server.py'),
                  wire_921600_simulation=uno, Motor_Pilot_UART2_simulation=pilot,
                  images_sha256={p.name:release.base.sha(p) for p in (OUT/'image').iterdir() if p.is_file()})
    (OUT/'uno_capture_PC.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
