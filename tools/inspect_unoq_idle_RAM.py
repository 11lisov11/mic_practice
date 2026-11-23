"""Decode saved non-atomic UNO SRAM with the exact loader/sketch ELF; offline only."""
import json,struct
from pathlib import Path
from elftools.elf.elffile import ELFFile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/live_bench_20261116/rpc_route_recovery_r1/idle_timeout_diagnosis_r1'
KERNEL=Path.home()/'AppData/Local/Arduino15/packages/arduino/hardware/zephyr/0.90.0/firmwares/zephyr-arduino_uno_q_stm32u585xx.elf'
APP=OUT.parent/'build/uno_router053/UNOQ_MOTOR.ino.elf'
RAM=(OUT/'Uno_RAM_nonatomic.bin').read_bytes()
def u(addr,n=4):
    assert 0x20000000<=addr and addr+n<=0x20000000+len(RAM),hex(addr)
    return int.from_bytes(RAM[addr-0x20000000:addr-0x20000000+n],'little')
def symbols(elf):return {s.name:s for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name}
def fields(die):
    result={}
    for child in die.iter_children():
        if child.tag=='DW_TAG_member':
            a=child.attributes;name=a.get('DW_AT_name');loc=a.get('DW_AT_data_member_location')
            if name and loc:
                result[name.value.decode()]=dict(offset=loc.value,type=child.get_DIE_from_attribute('DW_AT_type').offset)
    return result
def main():
    with KERNEL.open('rb') as f,APP.open('rb') as a:
        elf=ELFFile(f);app=ELFFile(a);sym=symbols(elf);asym=symbols(app)
        kernel_symbols={k:dict(address=hex(s['st_value']),size=s['st_size']) for k,s in sym.items() if any(x in k.lower() for x in ('kernel','thread','llext')) and (s['st_size'] or k.startswith('_kernel'))}
        print('DWARF',elf.has_dwarf_info(),'app',app.has_dwarf_info())
        dwarf=elf.get_dwarf_info();types={}
        wanted=('k_thread','z_kernel','_kernel','_thread_base','_callee_saved','k_mutex','llext','sys_dnode','_timeout','_wait_q','_cpu','_thread_arch')
        for cu in dwarf.iter_CUs():
            for die in cu.iter_DIEs():
                n=die.attributes.get('DW_AT_name')
                if n and n.value.decode(errors='replace') in wanted and die.tag in ('DW_TAG_structure_type','DW_TAG_union_type'):
                    name=n.value.decode(); fs=fields(die)
                    if fs:types[name]=dict(die=die.offset,size=die.attributes.get('DW_AT_byte_size').value,fields=fs)
        report=dict(kernel_symbols=kernel_symbols,types=types,
            app_sections=[dict(name=s.name,size=s['sh_size'],address=hex(s['sh_addr'])) for s in app.iter_sections() if s['sh_flags']&2],
            app_symbols={k:dict(offset=s['st_value'],size=s['st_size'],section=s['st_shndx']) for k,s in asym.items() if any(x in k for x in ('g_control_mutex','g_rpc_routes','mic_rpc_health','Bridge','g_timed_run'))})
        (OUT/'ELF_layout.json').write_text(json.dumps(report,indent=2)+'\n')
        threads=[];kernel=sym['_kernel']['st_value'];current=u(kernel+8);ptr=u(kernel+36);seen=set()
        while ptr and ptr not in seen:
            seen.add(ptr)
            name=RAM[ptr-0x20000000+136:ptr-0x20000000+168].split(b'\0')[0].decode(errors='replace')
            psp=u(ptr+80)
            row=dict(address=hex(ptr),name=name,current=ptr==current,state=u(ptr+13,1),
                pended_on=hex(u(ptr+8)),base=RAM[ptr-0x20000000:ptr-0x20000000+48].hex(),
                psp=hex(psp),stack_start=hex(u(ptr+168)),stack_size=u(ptr+172),
                saved_regs=[hex(u(ptr+48+4*i)) for i in range(9)])
            if 0x20000000<=psp<0x200c0000:
                row['stack_words']=[hex(u(psp+4*i)) for i in range(min(40,(0x200c0000-psp)//4))]
            threads.append(row);ptr=u(ptr+132)
        ext=u(sym['llext_list']['st_value']);exts=[]
        while ext:
            row=dict(address=hex(ext),name=RAM[ext-0x20000000+4:ext-0x20000000+20].hex(),
                mem=[hex(u(ext+20+4*i)) for i in range(12)],sizes=[u(ext+80+4*i) for i in range(12)])
            exts.append(row);ext=u(ext)
        report.update(threads=threads,extensions=exts)
        (OUT/'ELF_layout.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(dict(threads=[{k:v for k,v in t.items() if k!='stack_words'} for t in threads],extensions=exts),indent=2))
if __name__=='__main__':main()
