"""Offline schema5 replay using the exact ARM noise constructor and EKF ABI."""
import argparse,json,struct,hashlib
from pathlib import Path


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def crc(raw):
 c=0xffffffff
 for i,b in enumerate(raw):
  c^=0 if 60<=i<64 else b
  for _ in range(8):c=(c>>1)^(0x82f63b78 if c&1 else 0)
 return c^0xffffffff


def pair_arm_step(elf_path,prior,motor,inputs,fpscr,counts):
 from elftools.elf.elffile import ELFFile
 from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS
 from unicorn import arm_const as a
 uc=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS);uc.ctl_set_cpu_model(a.UC_CPU_ARM_CORTEX_M4)
 uc.mem_map(0x08000000,0x20000);uc.mem_map(0x20000000,0x8000);uc.mem_map(0x20010000,0x1000)
 with open(elf_path,'rb') as f:
  elf=ELFFile(f);syms={s.name:int(s['st_value']) for s in elf.get_section_by_name('.symtab').iter_symbols()}
  for seg in elf.iter_segments():
   if seg['p_type']=='PT_LOAD' and seg['p_filesz']:uc.mem_write(int(seg['p_vaddr']),seg.data())
 for name in ('mic_observer_noise','mic_observer_step'):
  if name not in syms:raise ValueError('Unsupported observer pointer ABI')
 uc.reg_write(a.UC_ARM_REG_C1_C0_2,0xf00000);uc.reg_write(a.UC_ARM_REG_FPEXC,1<<30)
 uc.reg_write(a.UC_ARM_REG_FPSCR,fpscr);uc.reg_write(a.UC_ARM_REG_XPSR,0x01000000)
 obs,model,values,noise=0x20010000,0x20010100,0x20010200,0x20010300
 uc.mem_write(obs,bytes(prior));uc.mem_write(model,bytes(motor));uc.mem_write(values,bytes(inputs))
 def call(name,args):
  uc.reg_write(a.UC_ARM_REG_SP,0x20008000);uc.reg_write(a.UC_ARM_REG_LR,0x0801fff1)
  for reg,value in zip((a.UC_ARM_REG_R0,a.UC_ARM_REG_R1,a.UC_ARM_REG_R2,a.UC_ARM_REG_R3),args):uc.reg_write(reg,value)
  uc.emu_start(syms[name]|1,0x0801fff0,timeout=5_000_000,count=2_000_000)
  if uc.reg_read(a.UC_ARM_REG_PC)!=0x0801fff0:raise ValueError('ARM step did not return')
  return uc.reg_read(a.UC_ARM_REG_R0)
 if call('mic_observer_noise',[counts,noise])!=1:raise ValueError('Invalid16-pair composition')
 rc=call('mic_observer_step',[obs,model,values,noise])
 return rc,bytes(uc.mem_read(obs,204)),bytes(uc.mem_read(noise,12))


def replay_pair_record(raw,elf,firmware):
 if len(raw)!=1888:raise ValueError('Record length')
 h=struct.unpack_from('<16I',raw)
 if h[:5]!=(0x3144534f,5,firmware,152,8) or h[7]!=700 or (h[13]&5)!=5 or h[13]&~7:
  raise ValueError('Schema/firmware/flags mismatch')
 if not 1<=h[5]<=8 or not 0<=h[6]<8 or h[9]+h[10]!=h[8] or h[5]>h[8] or h[11] not in (0,1):
  raise ValueError('Record counters')
 if not h[13]&4 or crc(raw)!=h[15]:raise ValueError('Missing or corrupt replay')
 payload=raw[1432:1888];packed=struct.unpack_from('<I',payload,452)[0];rc_expected=packed&255;counts=packed>>8
 prior_steps,prior_rej=struct.unpack_from('<II',payload,168)
 if prior_steps<499 or rc_expected>7 or not struct.unpack_from('<f',payload,416)[0]>=25:
  raise ValueError('Replay counters/result/event')
 fpscr,post_rej=struct.unpack_from('<II',payload,444)
 prior=payload[:168]+bytes(28)+payload[168:176]
 rc,post,noise=pair_arm_step(elf,prior,payload[176:228],payload[228:248],fpscr,counts)
 expected=payload[248:444]+struct.pack('<II',prior_steps+(rc_expected==0),post_rej)
 diff=[i for i in range(51) if post[i*4:i*4+4]!=expected[i*4:i*4+4]]
 return dict(passed=not diff and rc==rc_expected,bit_exact=not diff,result_equal=rc==rc_expected,
  compared_words=51,different_words=diff,counts=[(counts>>(5*i))&31 for i in range(3)],
  R_ARM_A2=list(struct.unpack('<3f',noise)),NIS=struct.unpack_from('<f',post,168)[0],
  hardware_commands=0,target_timing_measured=False,emulator='Actual ARM/FMA, stable pointer ABI, exact ARM R constructor')


def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--record',type=Path,required=True)
 ap.add_argument('--bundle',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 if a.out.exists():raise ValueError('Do not overwrite a result')
 m=json.loads((a.bundle/'replay_manifest.json').read_text());elf=a.bundle/m['elf']
 if sha(elf)!=m['elf_sha256']:raise ValueError('ELF hash mismatch')
 if m['ABI']!='observer: R0=o,R1=model,R2=input,R3=noise; noise: R0=counts,R1=out':raise ValueError('Unsupported ABI')
 r=replay_pair_record(a.record.read_bytes(),elf,m['firmware']);r.update(record_sha256=sha(a.record),elf_sha256=sha(elf))
 a.out.write_text(json.dumps(r,indent=2)+'\n',encoding='utf8');print(json.dumps(r))
 if not r['passed']:raise SystemExit(1)


if __name__=='__main__':main()
