import json,re,subprocess
import prepare_combined_io_diag as prep
import prepare_no_switch_diag as p
def main():
 prep.configure();import seal_pin_pwm_diag as base;base.main()
 c=prep.OUT;v=c/'verification';m=json.loads(p.read(c/'manifest.json'))
 if prep.BUILD==2026102802:
  race=json.loads(p.read(v/'preemption_test.json'));assert race['passed'] and race['old_enable_race_reproduced'] and race['old_stop_race_reproduced'] and race['real_fault_negative_controls']==7
 raw=subprocess.check_output([str(base.GNU/'arm-none-eabi-nm.exe'),'-S','-n',str(c/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf')],text=True)
 sy=json.loads(p.read(v/'symbols.json'))
 for line in raw.splitlines():
  a=line.split()
  if len(a)==4 and a[3] in ('mic_io_report','mic_uart_tx','uno_transport'):
   addr,size=int(a[0],16),int(a[1],16);assert 0x20000000<=addr<addr+size<=0x20008000;sy[a[3]]=dict(address=addr,bytes=size)
 assert sy['mic_io_report']['bytes']==160
 p.write(v/'symbols.json',json.dumps(sy,indent=2)+'\n')
 end=int(re.search(r'0x([0-9a-f]+)\s+PROVIDE \(_end =',p.read(c/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.map'))[1],16)
 margin=0x20008000-end-0x600;assert margin>=2600,margin
 m.update(RAM_margin_above_reservation=margin,io_report_bytes=160,UART_RX_CRC_and_TX_DMA_verified=True)
 m['sealed_sha256']={f.relative_to(c).as_posix():p.sha(f) for tree in ('nucleo','build','restore','verification','preserved_records') for f in (c/tree).rglob('*') if f.is_file() and not any(x in ('Debug','Release','__pycache__') for x in f.relative_to(c).parts)}
 p.write(c/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(dict(sealed=True,build=prep.BUILD,RAM_margin=margin,installed=False,archived=len(m['archived']))))
if __name__=='__main__':main()
