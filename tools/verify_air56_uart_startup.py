"""Run the 2302 reproducer and 2304 regressions on compiled Cortex-M4 images."""
import importlib.util
import json
import shutil
import struct
import sys

from unicorn import UC_HOOK_MEM_WRITE

from prepare_air56_uart_startup import BASE, NEW, OUT, ROOT, release
from verify_air56_lso_uno_capture import DMA1, RX, USART1, UnoExchange, test_uno
from verify_air56_lso_timing_aspep import TIM1, Firmware, test_ccm_startup, test_uart


USART, DMA_RX, DMA_TX, POLL_GAP, RX_BATCH, PARSER = (1 << index for index in range(6))
TRACE = 'air56_uart_diag'


def start_fixture(elf):
    link = UnoExchange(elf, NEW[1])
    link.set_vbus(9)

    def clear_usart(cpu, access, address, size, value, _):
        link.fw.put(USART1 + 0x1c, link.fw.get(USART1 + 0x1c) & ~value)

    link.fw.cpu.hook_add(UC_HOOK_MEM_WRITE, clear_usart, begin=USART1+0x20, end=USART1+0x20)
    return link


def status(frame):
    return bool(frame[0][3]&1), frame[0][38], frame[-1]


def event(link):
    addr=link.s[TRACE]
    return link.fw.words(addr, 5), link.fw.words(addr+28, 5)


def cold_gap(old, new):
    before=UnoExchange(old)
    before.set_vbus(9)
    before.poll(4)
    reply=before.send()
    assert reply[0][38]==4 and reply[0][9]==2 and not reply[0][3]&1

    corrected=start_fixture(new)
    corrected.poll(4)  # 680000 cycles, empty ring before the first valid UART frame.
    first, fatal=event(corrected)
    assert first[0]==POLL_GAP and first[2]==680000
    assert fatal[0]==0
    assert not corrected.send()  # No command accepted during re-synchronization.
    corrected.poll()
    for i in range(2):
        active, fault, diag=status(corrected.send())
        assert not active and not fault and diag[13]==i+1
    corrected.seq=(corrected.seq+1)&255   # A skipped sequence restarts OFF qualification.
    active, fault, diag=status(corrected.send())
    assert not active and not fault and diag[13]==1
    assert not corrected.start()
    # A non-OFF frame must not grant authority even if it had a valid CRC.
    _, fault, diag=status(corrected.send())
    assert fault==0 and diag[13]==1
    assert not status(corrected.send())[0]
    active, fault, diag=status(corrected.send())
    assert active and not fault and diag[13]==3
    assert diag[2]==0xB7 and diag[8]==POLL_GAP and diag[9]==0 and diag[10]&5==5
    assert struct.unpack_from('<I',diag,32)[0]==1
    assert corrected.fw.get(corrected.trace)==0
    return diag


def prearm_errors(elf):
    link=start_fixture(elf)
    fw=link.fw
    fw.put(USART1+0x1c, 1<<3)  # ORE
    link.poll()
    assert event(link)[0][0]==USART and event(link)[0][3]==8
    assert event(link)[1][0]==0 and fw.get(USART1+0x1c)==0
    link.poll()
    for _ in range(3): reply=link.send()
    assert status(reply)[:2]==(True,0)
    assert status(reply)[2][8]==USART

    damaged=start_fixture(elf)
    assert not damaged.send(damaged=True)
    assert event(damaged)[0][0]==PARSER and not event(damaged)[1][0]
    damaged.poll()
    for _ in range(3): reply=damaged.send()
    assert status(reply)[:2]==(True,0)

    duplicate=start_fixture(elf)
    duplicate.send()
    duplicate.seq=0
    reply=duplicate.send()
    assert status(reply)[2][13]==1 and not status(reply)[0]

    for dma_flag, reason in ((0x80,DMA_RX),(0x08,DMA_TX)):
        link=start_fixture(elf)
        link.fw.put(DMA1, dma_flag)
        link.poll()
        first,fatal=event(link)
        assert first[0]==fatal[0]==reason and first[4]==dma_flag
        link.fw.put(DMA1,0)  # Independent emulation of resolved bus condition.
        for _ in range(4): reply=link.send()
        assert status(reply)[:2]==(False,4)
        assert status(reply)[2][9]==reason
        assert link.fw.get(link.trace)==0

    keep=start_fixture(elf)
    keep.poll(4)  # recoverable first snapshot
    keep.fw.put(DMA1,0x80)
    keep.poll()   # later sticky first fatal, diagnostically independent
    assert event(keep)[0][0]==POLL_GAP and event(keep)[1][0]==DMA_RX
    keep.fw.put(DMA1,0)
    keep.poll(4)
    assert event(keep)[0][0]==POLL_GAP and event(keep)[1][0]==DMA_RX

    stop=start_fixture(elf)
    stop.send(0,2)
    stop.poll(4)
    reply=stop.send()
    assert reply[0][3]&4 and not reply[0][3]&1


def active_errors(elf):
    for reason in (USART, DMA_RX, DMA_TX, POLL_GAP, RX_BATCH):
        link=start_fixture(elf)
        fw=link.fw
        link.set_vbus(320)
        link.qualify_link_and_bus()
        assert link.start()
        link.emulate_running()
        if reason==USART: fw.put(USART1+0x1c,1<<3)
        if reason==DMA_RX: fw.put(DMA1,0x80)
        if reason==DMA_TX: fw.put(DMA1,0x08)
        if reason==RX_BATCH: link.inject(bytes(44))
        link.poll(4 if reason==POLL_GAP else 1)
        assert fw.get(TIM1+0x44)&0x8000==0
        assert fw.get(link.trace+20)==3 and fw.get(link.trace+4)==0
        assert event(link)[1][0]==reason
        assert fw.get(link.s[TRACE]+56)==0, 'An active error must not enter cold recovery'


def web_decode(packet):
    spec=importlib.util.spec_from_file_location('air56_uart_web_check',OUT/'web_hmi/server.py')
    server=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=server
    spec.loader.exec_module(server)
    sample=dict(mc_uart_startup_hex=packet.hex(),mc_uart_startup_age_ms=50,mc_fw_build=NEW[1])
    actual=server.decode_lso_uart_startup(sample)
    assert actual['available'] and actual['qualified'] and actual['first_causes']==['POLL_GAP']
    assert actual['first_elapsed_cycles']==680000 and actual['first_pending_bytes']==0
    assert not server.decode_lso_uart_startup(dict(sample,mc_uart_startup_age_ms=300))['available']
    assert not server.decode_lso_uart_startup(dict(sample,mc_uart_startup_hex=(packet[:-1]+bytes([packet[-1]^1])).hex()))['available']
    return actual


def main():
    name='ACIM-AIR56B2-LSO_FOC.elf'
    old=BASE/'image'/name
    new=OUT/'image'/name
    uart=web_decode(cold_gap(old,new))
    prearm_errors(new)
    active_errors(new)
    regressions,_=test_uno(new,NEW[1])
    fw=Firmware(new)
    dwt,lso=fw.off_dwt_fixture()
    remaining_ram=fw.sym['_estack']-fw.sym['_ebss']
    assert remaining_ram>=3072
    ccm_size=test_ccm_startup(new)
    aspep=test_uart(new)
    for file in ('air56_lso_capture.h','air56_st_lso_limits.h'):
        assert (OUT/'Inc'/file).read_bytes()==(BASE/'Inc'/file).read_bytes()
    for file in ('mc_tasks.c','mc_interface.c','main.c','mcp.c','stm32g4xx_mc_it.c'):
        assert (OUT/'Src'/file).read_bytes()==(BASE/'Src'/file).read_bytes()
    for file in ('uart_v3_transport.h','power_stage_parameters.h','drive_parameters.h'):
        assert (OUT/'Inc'/file).read_bytes()==(BASE/'Inc'/file).read_bytes()
    protected=release.base.read_json(OUT/'preserved_inputs_sha256.json')
    release.base.verify_inventory(protected,ROOT)
    uno_dir=OUT/'build/uno'
    manifest=release.base.read_json(uno_dir/'unoq_mcsdk_scalar.build-manifest.json')
    assert manifest['firmware_build_id']==NEW[0] and release.base.read_json(uno_dir/'llext-check.json')['pass']
    release.base.verify_inventory({item['file']:item['sha256'].lower() for item in manifest['artifacts']},uno_dir)
    shutil.copyfile(uno_dir/'UNOQ_MOTOR.ino.elf-zsk.bin',OUT/'image/UNOQ-LSO_CAPTURE.elf-zsk.bin')
    published=dict(passed=True,pair=NEW,installed=False,hardware_commands=0,
                   previous_frozen_reason_ambiguous=True,diagnostics_checked=uart,
                   cold_USART_resync=True,cold_crc_resync=True,
                   cold_DMA_remains_latched=True,first_and_first_fatal_preserved=True,
                   active_faults_force_PWM_off=['USART','DMA_RX','DMA_TX','POLL_GAP','RX_BATCH'],
                   active_regressions=regressions, ASPEP_UART2=aspep,
                   DWT_limit=4000,ADC_age_limit_us=2000,off_cases=len(dwt),
                   off_max_emulator_instructions=max(dwt),lso_max_emulator_instructions=max(lso),
                   actual_target_DWT_pending=True,ccm_bytes=ccm_size,
                   remaining_ram_before_stack=remaining_ram,preserved_files=len(protected),
                   web_hmi_sha256=release.base.sha(OUT/'web_hmi/server.py'),
                   images_sha256={p.name:release.base.sha(p) for p in (OUT/'image').iterdir() if p.is_file()})
    (OUT/'uart_startup_PC.json').write_text(json.dumps(published,indent=2)+'\n',encoding='utf8')
    print(json.dumps(published,indent=2))


if __name__=='__main__':
    main()
