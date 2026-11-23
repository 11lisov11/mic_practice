"""Strict OFFLINE replay of the start-to-first-NIS input journal, using its ARM ELF.

Requires meta.bin, rows.bin, checkpoints.bin. No network/device imports or calls.
Every intermediate x/P is exported. Rejects GAP, wrong ELF identity, missing
checkpoints, malformed inputs, invalid hashes and any terminal byte mismatch.
"""
import argparse,hashlib,json,math,struct
from pathlib import Path
from replay_observer_pair_noise import pair_arm_step

def mix(h,v):return ((h^v)*16777619)&0xffffffff
def state_hash(post):
 h=2166136261
 for w in struct.unpack('<51I',post):h=mix(h,w)
 return h
def crc_meta(raw):
 c=0xffffffff
 for i,b in enumerate(raw):
  c^=0 if 56<=i<60 else b
  for _ in range(8):c=(c>>1)^(0x82f63b78 if c&1 else 0)
 return c^0xffffffff
def pair_counts(code):
 if code>152:raise ValueError('Invalid pair composition')
 a=0
 while code>=17-a:code-=17-a;a+=1
 return a|(code<<5)|((16-a-code)<<10)

class ArmObserver:
 """One emulator per sequence; same hard-FPU ABI as installed replay kernel."""
 def __init__(self,elf_path):
  from elftools.elf.elffile import ELFFile
  from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS
  from unicorn import arm_const as a
  self.a=a;uc=self.uc=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
  uc.ctl_set_cpu_model(a.UC_CPU_ARM_CORTEX_M4)
  uc.mem_map(0x08000000,0x20000);uc.mem_map(0x20000000,0x8000);uc.mem_map(0x20010000,0x1000)
  with Path(elf_path).open('rb') as f:
   elf=ELFFile(f);self.syms={s.name:int(s['st_value']) for s in elf.get_section_by_name('.symtab').iter_symbols()}
   for seg in elf.iter_segments():
    if seg['p_type']=='PT_LOAD' and seg['p_filesz']:uc.mem_write(int(seg['p_vaddr']),seg.data())
  for name in ('mic_observer_noise','mic_observer_step'):
   if name not in self.syms:raise ValueError('Unsupported pointer ABI')
  uc.reg_write(a.UC_ARM_REG_C1_C0_2,0xf00000);uc.reg_write(a.UC_ARM_REG_FPEXC,1<<30)
  uc.reg_write(a.UC_ARM_REG_XPSR,0x01000000)
 def call(self,name,args):
  a=self.a;uc=self.uc;uc.reg_write(a.UC_ARM_REG_SP,0x20008000);uc.reg_write(a.UC_ARM_REG_LR,0x0801fff1)
  for reg,value in zip((a.UC_ARM_REG_R0,a.UC_ARM_REG_R1,a.UC_ARM_REG_R2,a.UC_ARM_REG_R3),args):uc.reg_write(reg,value)
  uc.emu_start(self.syms[name]|1,0x0801fff0,timeout=5_000_000,count=2_000_000)
  if uc.reg_read(a.UC_ARM_REG_PC)!=0x0801fff0:raise ValueError('ARM step did not return')
  return uc.reg_read(a.UC_ARM_REG_R0)
 def step(self,prior,motor,inputs,fpscr,counts):
  a=self.a;uc=self.uc;obs,model,values,noise=0x20010000,0x20010100,0x20010200,0x20010300
  uc.mem_write(obs,bytes(prior));uc.mem_write(model,bytes(motor));uc.mem_write(values,bytes(inputs))
  uc.reg_write(a.UC_ARM_REG_FPSCR,fpscr)
  if self.call('mic_observer_noise',[counts,noise])!=1:raise ValueError('Bad pair composition')
  # Firmware records FPSCR after constructing R and immediately before the step.
  uc.reg_write(a.UC_ARM_REG_FPSCR,fpscr)
  rc=self.call('mic_observer_step',[obs,model,values,noise])
  return rc,bytes(uc.mem_read(obs,204)),bytes(uc.mem_read(noise,12))

def replay(folder,elf,firmware,states=None):
 folder=Path(folder);meta=(folder/'meta.bin').read_bytes();rows=(folder/'rows.bin').read_bytes();checks=(folder/'checkpoints.bin').read_bytes()
 if len(meta)!=524:raise ValueError('Metadata length')
 h=struct.unpack_from('<16I',meta)
 if h[:3]!=(0x3148534e,1,firmware) or h[4:6]!=(22,5120) or h[14]!=crc_meta(meta):raise ValueError('Metadata identity/CRC')
 if not 1<=h[6]<=5120 or h[8]&~31 or h[8]&(4|8):raise ValueError('Incomplete/gapped/overflow record')
 if len(rows)!=h[6]*22 or len(checks)!=h[6]//16*4:raise ValueError('Missing row/checkpoint')
 if not h[8]&(1|2):raise ValueError('No terminal cause')
 if h[7] not in (0,h[6]) or bool(h[8]&1)!=bool(h[7]):raise ValueError('Event counter')
 motor=meta[64:116];prior=meta[116:320];expected=meta[320:524]
 if struct.unpack_from('<I',prior,196)[0]!=0:raise ValueError('History did not start at observer reset')
 arm=ArmObserver(elf);chain=2166136261;first=None;maximum=0.;checkpoints=0
 stream=Path(states).open('x',encoding='utf8') if states else None
 try:
  for index in range(h[6]):
   row=rows[index*22:(index+1)*22];values=struct.unpack_from('<5f',row)
   if not all(math.isfinite(x) for x in values) or not .0001<=values[4]<=.002:raise ValueError('Invalid input/dt')
   counts=pair_counts(row[20]);mode_rc=row[21];fpscr=(mode_rc>>3)<<22
   rc,post,noise=arm.step(prior,motor,row[:20],fpscr,counts)
   if rc!=(mode_rc&7):raise ValueError(f'ARM result mismatch at {index+1}')
   checksum=state_hash(post);nis=struct.unpack_from('<f',post,168)[0]
   for b in row:chain=mix(chain,b)
   chain=mix(chain,checksum)
   if index%16==15:
    if checksum!=struct.unpack_from('<I',checks,index//16*4)[0]:raise ValueError(f'x/P checkpoint mismatch at {index+1}')
    checkpoints+=1
   if not math.isfinite(nis) or nis>=25:
    if first is None:first=index+1
   if math.isfinite(nis):maximum=max(maximum,nis)
   if stream:
    floats=struct.unpack_from('<49f',post)
    stream.write(json.dumps(dict(call=index+1,inputs=values,pairs=counts,FPSCR_control=fpscr,result=rc,
     prior_x=struct.unpack_from('<6f',prior),prior_P=struct.unpack_from('<36f',prior,24),
     x=floats[:6],P=floats[6:42],NIS=nis,R=struct.unpack('<3f',noise),state_hash=checksum),allow_nan=False)+'\n')
   prior=post
 finally:
  if stream:stream.close()
 if chain!=h[13]:raise ValueError('Whole-sequence state/input chain mismatch')
 if prior!=expected:raise ValueError('Full terminal x/P/diagnostic mismatch')
 if first!= (h[7] or None):raise ValueError('First NIS event mismatch')
 return dict(passed=True,rows=h[6],checkpoints=checkpoints,all_states_reconstructed=True,
  first_NIS_ge25=first,peak_NIS=maximum,terminal_51_words_bit_exact=True,
  hardware_commands=0,target_timing_measured=False,
  elf_sha256=hashlib.sha256(Path(elf).read_bytes()).hexdigest())

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--record',type=Path,required=True)
 ap.add_argument('--bundle',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 if a.out.exists():raise ValueError('Do not overwrite evidence')
 m=json.loads((a.bundle/'replay_manifest.json').read_text());elf=a.bundle/m['elf']
 if hashlib.sha256(elf.read_bytes()).hexdigest()!=m['elf_sha256']:raise ValueError('Wrong ELF hash')
 result=replay(a.record,elf,m['firmware'],a.out.with_suffix('.states.jsonl'))
 a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
