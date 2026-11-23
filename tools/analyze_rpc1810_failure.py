"""Resolve the exact installed1809 sparse passive RPC failure capture, offline."""
import json, struct, sys
from pathlib import Path
from elftools.elf.elffile import ELFFile

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261118/boot_stack_integrity_r1'

def main():
    folder=Path(sys.argv[1]); parts=[]
    for name,address in [('bridge',0x20036358),('worker',0x20015b78),('control',0x20016500),
                         ('worker_stack',0x20036a30),('bridge_stack',0x2004b0d0),
                         ('decoder',0x20014ecc),('serial',0x20036854),('health',0x2003610c)]:
        parts.append((address,(folder/f'failure_{name}.bin').read_bytes()))
    def u(address):
        for start,data in parts:
            if start<=address and address+4<=start+len(data):return struct.unpack_from('<I',data,address-start)[0]
        raise ValueError(hex(address))
    kernel=Path.home()/'AppData/Local/Arduino15/packages/arduino/hardware/zephyr/0.90.0/firmwares/zephyr-arduino_uno_q_stm32u585xx.elf'
    app=BASE/'build/uno/UNOQ_MOTOR.ino.elf'; funcs=[]
    bases={'.text':0x200021e0,'.data':0x200148dc,'.rodata':0x2001491c,'.bss':0x20014eb8}
    for scope,path in [('kernel',kernel),('app',app)]:
        with path.open('rb') as f:
            elf=ELFFile(f)
            for symbol in elf.get_section_by_name('.symtab').iter_symbols():
                idx=symbol['st_shndx']
                if symbol['st_info']['type']!='STT_FUNC' or not isinstance(idx,int):continue
                section=elf.get_section(idx).name
                if scope=='app' and section not in bases:continue
                address=symbol['st_value']+(bases[section] if scope=='app' else 0)
                funcs.append((address&~1,symbol['st_size'],scope+':'+symbol.name))
    funcs.sort()
    def resolve(address):
        address&=~1
        for start,size,name in reversed(funcs):
            if start<=address<start+size:return name+'+0x%x'%(address-start)
    result={'scope':'Passive non-atomic sparse capture. Stack matches are evidence, not a complete unwind.','threads':[],'mutexes':{}}
    for name,address in [('control',0x20016500),('read',0x20036368),('write',0x2003637c),('outgoing',0x200363a4)]:
        result['mutexes'][name]={'owner':hex(u(address+8)),'count':u(address+12)}
    for name,address in [('worker',0x20015b78),('bridge',0x200363c0)]:
        psp=u(address+80);stack=u(address+168);size=u(address+172)
        row={'name':name,'thread':hex(address),'psp':hex(psp),'stack':hex(stack),'size':size,'matches':[]}
        for at in range(psp,stack+size,4):
            value=u(at);symbol=resolve(value)
            if symbol:row['matches'].append({'at':hex(at),'value':hex(value),'symbol':symbol})
        result['threads'].append(row)
    result['health']=[u(0x2003610c+4*i) for i in range(4)]
    (folder/'thread_analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
