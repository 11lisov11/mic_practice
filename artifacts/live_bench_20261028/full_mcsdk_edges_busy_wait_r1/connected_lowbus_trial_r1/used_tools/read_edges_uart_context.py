import argparse,ctypes,json,struct,subprocess
from pathlib import Path
import prepare_no_switch_diag as p
from prepare_full_edges_busy_wait import OUT,BUILD
from full_mcsdk_edges_host import Probe
from seal_no_switch_diag import GNU
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--outdir',type=Path,required=True);a=ap.parse_args();out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False);(out/'logs').mkdir();pr=Probe(out/'logs')
 raw=subprocess.check_output([str(GNU/'arm-none-eabi-nm.exe'),'-S','-n',str(OUT/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf')],text=True)
 sy={}
 for line in raw.splitlines():
  b=line.split()
  if len(b)==4 and b[3] in ('uno_link','uno_transport','mic_uart_reject_record'):
   sy[b[3]]=(int(b[0],16),int(b[1],16))
 records={}
 for n,(addr,size) in sy.items():
  data=pr.read(addr,(size+3)&~3,n);(out/(n+'.bin')).write_bytes(data);records[n]=data[:size]
 U8=ctypes.c_uint8;U16=ctypes.c_uint16;U32=ctypes.c_uint32;S16=ctypes.c_int16;B=ctypes.c_bool
 class Link(ctypes.LittleEndianStructure):
  _fields_=[('parser_state',U8),('parser_index',U8),('frame',U8*43),('last_seq',U8),('last_mode',U8),('fault_code',U8),('good_count',U16),('bad_count',U16)]+[(n,U8) for n in ('first_reason','first_uart_errors','first_motor_state','first_tx_status','first_sequence','last_bad_reason','last_uart_errors','last_tx_status')]+[('first_current_faults',U16),('first_occurred_faults',U16),('last_valid_ms',U32),('last_speed_unit',S16),('ramp_target_speed_unit',S16),('ramp_rate_centi',U16)]+[(n,B) for n in ('coast_hold','manual_ramp_down','decel_bus_hold','link_seen','command_enabled','fault_latched','softstart_ready','softstart_tracking')]+[('softstart_stable_since_ms',U32)]
 assert ctypes.sizeof(Link)==len(records['uno_link']);o=Link.from_buffer_copy(records['uno_link']);d={n:getattr(o,n) for n,_ in Link._fields_ if n!='frame'}
 # Exact uv3_rx layout's retained last/fatal reject blocks start at offsets32/176.
 transport=records['uno_transport'];events=[]
 for off in (32,176):
  meta=list(struct.unpack('<14I',transport[off:off+56]));events.append(dict(offset=off,meta=meta,bytes=transport[off+56:off+100].hex(),marks=transport[off+100:off+144].hex()))
 result=dict(build=BUILD,link=d,raw_reject_blocks=events,hardware_writes=0)
 p.write(out/'report.json',json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
