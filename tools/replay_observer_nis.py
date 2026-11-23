"""Replay ONE recorded EKF step on the exact firmware ARM ELF, on a PC.

Requires unicorn==2.1.4 and pyelftools. Does not connect to hardware. The
record's model, input binary32 bits and FPSCR are restored. Actual ARM/FMA
instructions run in an emulator; no host floating-point observer substitution.
This verifies one step, not physical sensor accuracy or target execution time.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from observer_nis_replay_decode import decode_nis_replay


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def crc(raw):
    c=0xffffffff
    for i,b in enumerate(raw):
        c^=0 if 60<=i<64 else b
        for _ in range(8):c=(c>>1)^(0x82f63b78 if c&1 else 0)
    return c^0xffffffff


def record_payload(raw,firmware):
    if len(raw)!=1888:raise ValueError('record length')
    h=struct.unpack_from('<16I',raw)
    if h[:5]!=(0x3144534f,4,firmware,152,8) or h[7]!=700:
        raise ValueError('schema/firmware/layout mismatch')
    if not h[13]&1 or h[13]&~7 or not h[13]&4 or crc(raw)!=h[15]:
        raise ValueError('incomplete/missing/corrupt replay')
    if not 1<=h[5]<=8 or not 0<=h[6]<8 or h[10]+h[9]!=h[8]:
        raise ValueError('record counters')
    payload=raw[1432:1888];decode_nis_replay(payload)
    return payload


def arm_step(elf_path,prior,motor,inputs,fpscr):
    prior,motor,inputs=bytes(prior),bytes(motor),bytes(inputs)
    from elftools.elf.elffile import ELFFile
    from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS
    from unicorn import arm_const as a
    # Only the ELF's actual observer wrapper is callable here. Fail closed if
    # a future compiler changes this ABI/symbol arrangement; do not guess.
    with open(elf_path,'rb') as f:
        elf=ELFFile(f)
        symbols={s.name:int(s['st_value']) for s in elf.get_section_by_name('.symtab').iter_symbols()}
        names=[n for n in symbols if n.startswith('ma_observe.constprop.')]
        if len(names)!=1 or 'observer' not in symbols or 'model' not in symbols:
            raise ValueError('unsupported ELF observer ABI')
        uc=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
        uc.ctl_set_cpu_model(a.UC_CPU_ARM_CORTEX_M4)
        uc.mem_map(0x08000000,0x20000);uc.mem_map(0x20000000,0x8000)
        for seg in elf.iter_segments():
            if seg['p_type']=='PT_LOAD' and seg['p_filesz']:
                uc.mem_write(int(seg['p_vaddr']),seg.data())
    uc.reg_write(a.UC_ARM_REG_C1_C0_2,0xf00000)
    uc.reg_write(a.UC_ARM_REG_FPEXC,1<<30)
    uc.reg_write(a.UC_ARM_REG_FPSCR,fpscr)
    uc.reg_write(a.UC_ARM_REG_SP,0x20008000)
    uc.reg_write(a.UC_ARM_REG_XPSR,0x01000000)
    sentinel=0x0801fff0;uc.reg_write(a.UC_ARM_REG_LR,sentinel|1)
    uc.mem_write(symbols['observer'],prior);uc.mem_write(symbols['model'],motor)
    uc.reg_write(a.UC_ARM_REG_R0,symbols['observer'])
    for i,value in enumerate(struct.unpack('<5I',inputs)):
        uc.reg_write(a.UC_ARM_REG_S0+i,value)
    uc.emu_start(symbols[names[0]]|1,sentinel,timeout=5_000_000,count=2_000_000)
    if uc.reg_read(a.UC_ARM_REG_PC)!=sentinel:
        raise RuntimeError('ARM replay did not return within bounded execution')
    return uc.reg_read(a.UC_ARM_REG_R0),bytes(uc.mem_read(symbols['observer'],204))


def replay(payload,elf):
    decoded=decode_nis_replay(payload)
    # ma_observer: x/P168,nis4,predicted8,innovation8,variance8,steps4,rejected4.
    prior=payload[:168]+bytes(28)+payload[168:176]
    rc,observed=arm_step(elf,prior,payload[176:228],payload[228:248],decoded['fpscr'])
    expected=payload[248:444]+struct.pack('<II',decoded['post_steps'],decoded['post_rejected'])
    differences=[]
    for offset in range(0,204,4):
        got=struct.unpack_from('<I',observed,offset)[0];want=struct.unpack_from('<I',expected,offset)[0]
        if got!=want:differences.append(dict(observer_word=offset//4,expected_bits=f'{want:08x}',actual_bits=f'{got:08x}'))
    return dict(passed=not differences and rc==decoded['result'],bit_exact=not differences,
        result_equal=rc==decoded['result'],recorded_result=decoded['result'],replayed_result=rc,
        checked_32bit_words=51,differences=differences,prior_step=decoded['prior_steps'],
        NIS=decoded['nis'],emulator='Unicorn Cortex-M4, actual ELF including ARM FMA',
        hardware_commands=0,target_timing_measured=False,
        limitation='One EKF call only; cannot prove measured current or reconstructed voltage is physically correct')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record',type=Path,required=True);p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    if args.out.exists():raise ValueError('Refusing to overwrite an existing result')
    manifest=json.loads((args.bundle/'replay_manifest.json').read_text(encoding='utf8'))
    elf=args.bundle/manifest['elf']
    if sha(elf)!=manifest['elf_sha256']:raise ValueError('ELF SHA mismatch')
    if manifest['ABI']!='R0=observer; S0..S4=ia,ib,va,vb,dt; global=model':raise ValueError('Unsupported bundle ABI')
    payload=record_payload(args.record.read_bytes(),manifest['firmware'])
    result=replay(payload,elf);result.update(record_sha256=sha(args.record),elf_sha256=sha(elf),firmware=manifest['firmware'])
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='differences'},ensure_ascii=False))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
