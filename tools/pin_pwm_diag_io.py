"""Read/write only the isolated fixture mailbox; no motor-control operations."""
import json,struct,time
from pathlib import Path
import no_switch_diag_snapshot_io as old
PACKAGE=old.PACKAGE.with_name('pin_pwm_diag_r2')
PROGRAMMER=old.PROGRAMMER;SERIAL=old.SERIAL;crc32c=old.crc32c
class Probe(old.Probe):
 def request(self,addr,cancel=False):
  if addr%4 or not 0x20000000<=addr<0x20008000:raise ValueError('Not an SRAM mailbox')
  return self.call(['-w32',hex(addr),hex(0x50494e00 if cancel else 0x50494e35),'-nv'],'cancel' if cancel else 'one_pin_request')
def decode(raw):
 if len(raw)!=256:raise ValueError('Incomplete PIN report')
 w=struct.unpack('<64I',raw)
 if w[0]!=0x314e4950 or w[1]!=1 or w[2] not in (2026102794,2026102795) or w[3]!=64:raise ValueError('PIN identity mismatch')
 if w[4]&1 or w[4]!=w[61] or crc32c(raw[20:244])!=w[62] or w[63]!=0x50494e45:raise ValueError('PIN report CRC/sequence')
 keys=('reads','errors','NACK','deadline','BUSY','ARLO','BERR_clears','forced_resets','normal_parks','raw_angle','magnet_status','valid_flags','ISR','CR1','GPIOB_IDR','sample_ms','fault_slots')
 return dict(build=w[2],sequence=w[4],state=w[5],reason=w[6],attempted=w[7],start=w[8],stop=w[9],elapsed_cycles=w[10],hz=w[11],
  elapsed_ms=w[10]*1000/w[11] if w[11] else None,updates=w[12],max_ISR_cycles=w[13],max_IRQ_gap=w[14],max_main_gap=w[15],phase=w[16],
  BDTR=w[17],CR1=w[18],ARR=w[19],CCR=list(w[20:23]),GPIOA_IDR=w[23],local_stop=w[24],RCR=w[25],RCC_AHB2ENR=w[26],PSC=w[27],
  encoder=dict(zip(keys,w[28:45])),boundaries=list(w[45:53]),CCER=w[53],AF1=w[54],GPIOA_MODER=w[55],GPIOB_MODER=w[56],
  break_SR=w[57],SMCR=w[58],DIER=w[59],SysTick_LOAD=w[60])
def read_report(pr,out,label):
 symbols=json.loads((PACKAGE/'verification/symbols.json').read_text())
 for i in range(4):
  raw=pr.read(symbols['mic_pin_report']['address'],256,label+str(i));(out/(label+str(i)+'.bin')).write_bytes(raw)
  try:d=decode(raw)
  except ValueError:
   if i==3:raise
   time.sleep(.1);continue
  (out/(label+'.json')).write_text(json.dumps(d,indent=2)+'\n');return d
def eligible(d):
 return d['build']==2026102795 and d['state']==d['reason']==d['attempted']==0 and d['hz']==170000000 and not(d['BDTR']&0x8000) and bool(d['BDTR']&0x1000) and not(d['BDTR']&0x4000) and d['CCER']==0x555 and d['local_stop']==0 and d['SysTick_LOAD']==169999 and not(d['RCC_AHB2ENR']&(1<<13))
