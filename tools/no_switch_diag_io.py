"""Offline report decoder and bounded ST-LINK access for the computation image."""
import json,struct,subprocess,time
from pathlib import Path
from wifi_stop_tail_probe import parse_registers
ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'artifacts/live_bench_20261027/no_switch_diag_r1'
PROGRAMMER=Path('C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe')
SERIAL='003A002C3335510933383531'
WORDS=72
def crc32c(data):
 c=0xffffffff
 for b in data:
  c^=b
  for _ in range(8):c=(c>>1)^(0x82f63b78 if c&1 else 0)
 return c^0xffffffff
def decode(raw):
 if len(raw)!=WORDS*4:raise ValueError('Incomplete diagnostic report')
 w=struct.unpack('<72I',raw)
 if w[:4]!=(0x3147444c,1,2026102790,WORDS):raise ValueError('Unknown diagnostic identity')
 if w[4]!=w[69] or w[4]&1 or crc32c(raw[20:276])!=w[70] or w[71]!=0x4c44454e:raise ValueError('Torn/corrupt diagnostic report')
 if w[5]>4:raise ValueError('Unknown state')
 names=['reads','errors','NACK','deadline','BUSY','ARLO','BERR_clears','forced_resets','normal_parks','raw_angle','magnet_status','valid_flags','ISR','CR1','GPIOB_IDR','sample_ms','fault_slots']
 return dict(state=w[5],state_name=['IDLE','RUNNING','DONE','ABORTED','DENIED'][w[5]],reason=w[6],attempted=w[7],
  start_cycles=w[8],stop_cycles=w[9],elapsed_cycles=w[10],clock_hz=w[11],elapsed_ms=w[10]*1000/w[11] if w[11] else None,
  tim_updates=w[12],adc_calls=w[13],adc_accepted=w[14],tim_max_cycles=w[15],adc_max_cycles=w[16],
  tim_max_gap_cycles=w[17],adc_max_gap_cycles=w[18],foreground_max_gap_cycles=w[19],
  ccr_min=[w[20],w[22],w[24]],ccr_max=[w[21],w[23],w[25]],actual_bus_v=w[26],private_replay_bus_v=w[27],
  TIM1_BDTR=w[28],TIM1_CR1=w[29],TIM1_DIER=w[30],TIM1_ARR=w[31],CCR=list(w[32:36]),
  motor_fault_active=w[36],motor_fault_occurred=w[37],phase_pins_gpio_low=w[38],guard_flags=w[39],local_stop=w[40],
  encoder=dict(zip(names,w[41:58])),adc_quality_flags=w[58],adc_seen=w[59],limit_cycles=w[60],
  medium_updates=w[61],ramp_ms=w[62],field_millihz=w[63],medium_hz=w[64],field_task_hz=w[65],sequence=w[4])
def eligible(d):
 return (d['state']==0 and d['attempted']==0 and d['clock_hz']==170000000 and d['actual_bus_v']<20
  and d['phase_pins_gpio_low']==1 and not(d['TIM1_BDTR']&0x8000) and d['TIM1_BDTR']&0x1000
  and d['TIM1_CR1']&1 and d['adc_seen']>100 and d['guard_flags']==0 and d['local_stop']==0)
class Probe:
 def __init__(self,logs):self.logs=logs;self.n=0
 def call(self,args,label):
  self.n+=1
  q=subprocess.run([str(PROGRAMMER),'-c','port=SWD','mode=HOTPLUG','sn='+SERIAL,*args],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
  f=self.logs/f'{self.n:03}_{label}.log';f.write_text(q.stdout+q.stderr,encoding='utf-8')
  if q.returncode:raise RuntimeError(f'ST-LINK failed; inspect {f.name}. No automatic retry of writes.')
  return q.stdout
 def read(self,addr,size,label):
  if addr%4 or size%4 or not(0x20000000<=addr and addr+size<=0x20008000):raise ValueError('Not allowed SRAM read')
  words=parse_registers(self.call(['-r32',hex(addr),str(size)],label))
  if any(addr+i not in words for i in range(0,size,4)):raise RuntimeError('Incomplete ST-LINK memory read')
  return b''.join(struct.pack('<I',words[addr+i]) for i in range(0,size,4))
 def request(self,addr,cancel=False):
  # Only a dedicated request mailbox; no TIM/ADC/I2C/safety register writes.
  if addr%4 or not(0x20000000<=addr<=0x20007ffc):raise ValueError('Not allowed SRAM mailbox')
  return self.call(['-w32',hex(addr),hex(0x4c440000 if cancel else 0x4c443501),'-nv'],'cancel' if cancel else 'one_load_request')
def read_report(probe,address,out,label):
 last=None
 for attempt in range(4):
  raw=probe.read(address,WORDS*4,f'{label}_{attempt}')
  (out/f'{label}_{attempt}.bin').write_bytes(raw)
  try:
   d=decode(raw);(out/f'{label}.json').write_text(json.dumps(d,indent=2)+'\n',encoding='utf-8');return d
  except ValueError as e:last=e
  time.sleep(.1)
 raise RuntimeError(str(last))
