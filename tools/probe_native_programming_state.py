"""Independent passive SWD proof for repairing unavailable Uno RPC.

No fake RPC status, bypass of motor START guards, reset, halt or writes. Requires
the user's separately confirmed J1-off / meter-below-20-V USB state.
"""
import json,subprocess,struct,time,hashlib
from pathlib import Path
from elftools.elf.elffile import ELFFile
from install_bkin_boot_armed_pair import PROGRAMMER,STLINK_SERIAL,board_ports
def programmed_hex_image(path,binary,start=0x08000000):
 """Validate exact HEX payload against BIN, with erased FF only in HEX gaps."""
 image=bytearray(b'\xff'*len(binary));seen=bytearray(len(binary));upper=0;ended=False
 for line in path.read_text(encoding='ascii').splitlines():
  assert line.startswith(':') and not ended,'invalid HEX record/order'
  r=bytes.fromhex(line[1:]);assert len(r)>=5 and len(r)==r[0]+5 and sum(r)%256==0,'invalid HEX checksum/length'
  n=r[0];addr=int.from_bytes(r[1:3],'big');kind=r[3];data=r[4:4+n]
  if kind==0:
   pos=upper+addr-start;assert 0<=pos<=len(binary)-n,'HEX outside expected Flash image'
   assert data==binary[pos:pos+n],'HEX data differs from sealed BIN'
   for i,b in enumerate(data,pos):
    assert not seen[i] or image[i]==b,'conflicting HEX overlap'
    seen[i]=1;image[i]=b
  elif kind==1:assert n==0 and addr==0;ended=True
  elif kind==4:assert n==2 and addr==0;upper=int.from_bytes(data,'big')<<16
  elif kind==5:assert n==4 and addr==0
  else:raise AssertionError('unsupported HEX record type')
 assert ended and seen[0] and seen[-1],'incomplete HEX image'
 holes=[i for i,v in enumerate(seen) if not v]
 assert all(binary[i]==0 for i in holes),'nonzero BIN data omitted by HEX'
 return bytes(image),holes

def inspect_layout(elf):
 with elf.open('rb') as stream:
  e=ELFFile(stream);syms={s.name:int(s['st_value']) for s in e.get_section_by_name('.symtab').iter_symbols()}
  layouts=[]
  for cu in e.get_dwarf_info().iter_CUs():
   for die in cu.iter_DIEs():
    a=die.attributes.get('DW_AT_name')
    if die.tag=='DW_TAG_typedef' and a and a.value==b'BusVoltageSensor_Handle_t':
     t=die.get_DIE_from_attribute('DW_AT_type')
     row={m.attributes['DW_AT_name'].value.decode():int(m.attributes['DW_AT_data_member_location'].value) for m in t.iter_children() if m.tag=='DW_TAG_member'}
     layouts.append(row)
  assert layouts and all(v==layouts[0] for v in layouts)
  return syms,layouts[0]
def probe(package,out,confirmation_description='user below 20 V / J1 off'):
 out.mkdir(parents=True,exist_ok=False);ports=board_ports()
 base=package/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL'
 expected=base.with_suffix('.bin');symbols,layout=inspect_layout(base.with_suffix('.elf'))
 def read(addr,size,path,label):
  r=subprocess.run([str(PROGRAMMER),'-c','port=SWD','mode=HotPlug','sn='+STLINK_SERIAL,
   '-u',hex(addr),str(size),str(path)],capture_output=True,text=True,timeout=20)
  (out/(label+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode()
  raw=path.read_bytes();assert len(raw)==size
  return raw
 actual=read(0x08000000,expected.stat().st_size,out/'installed_native.bin','read_native_flash')
 binary=expected.read_bytes();image_kind='exact BIN';holes=[]
 if actual!=binary:
  hex_image,holes=programmed_hex_image(base.with_suffix('.hex'),binary)
  assert actual==hex_image,'installed native image differs from both sealed BIN and exact programmed HEX'
  image_kind='exact HEX with erased FF padding'
 rows=[]
 for i in range(2):
  data=read(symbols['BusVoltageSensor_M1'],12,out/f'bus_{i}.bin',f'bus_{i}')
  factor=struct.unpack_from('<H',data,layout['ConversionFactor'])[0]
  digital=struct.unpack_from('<H',data,layout['AvBusVoltage_d'])[0]
  tick=struct.unpack('<I',read(symbols['uwTick'],4,out/f'tick_{i}.bin',f'tick_{i}'))[0]
  bdtr=struct.unpack('<I',read(0x40012c44,4,out/f'bdtr_{i}.bin',f'bdtr_{i}'))[0]
  volts=digital*factor/65536
  assert factor==416 and digital>0 and 0<volts<=20,'no positive independently corroborated low bus'
  assert not(bdtr&0x8000),'native PWM main output is enabled'
  rows.append(dict(tick_ms=tick,bus_volts=volts,conversion_factor=factor,digital_bus=digital,bdtr=bdtr,moe=False))
  time.sleep(.25)
 delta=(rows[1]['tick_ms']-rows[0]['tick_ms'])&0xffffffff
 assert 100<delta<5000,'native core/tick is not progressing'
 report=dict(passed=True,source='passive ST-Link HotPlug reads',ports=ports,physical_authorization_context=confirmation_description,
  native_image_sha256=hashlib.sha256(actual).hexdigest(),image_comparison=image_kind,
  hex_erased_padding_offsets=holes,sealed_binary_sha256=hashlib.sha256(binary).hexdigest(),
  layout_from_actual_dwarf=layout,rows=rows,tick_delta_ms=delta,
  flash_writes=0,reset_commands=0,halt_commands=0,motor_commands=0)
 (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 return report
