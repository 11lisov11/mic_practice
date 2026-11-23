"""2793 report decoder; also reads installed2792 for pre-install archival."""
import struct
from pathlib import Path
import no_switch_diag_snapshot_io as old
PACKAGE=old.PACKAGE.with_name('logic_edges_diag_r1')
Probe=old.Probe;PROGRAMMER=old.PROGRAMMER;SERIAL=old.SERIAL;crc32c=old.crc32c
BASE_DECODE=old.decode
def decode(raw):
 w=list(struct.unpack('<72I',raw))
 if w[2]!=2026102793:return BASE_DECODE(raw)
 w[2]=2026102792
 d=BASE_DECODE(struct.pack('<72I',*w));d['build']=2026102793;return d
def eligible(d):
 q=dict(d);q['build']=2026102792
 return d.get('build')==2026102793 and old.eligible(q)
def read_report(probe,address,out,label):
 previous=old.decode
 try:old.decode=decode;return old.read_report(probe,address,out,label)
 finally:old.decode=previous
def decode_edges(raw):
 if len(raw)!=48:raise ValueError('Incomplete edge report')
 w=struct.unpack('<12I',raw)
 if w[:2]!=(0x3147454c,2026102793) or crc32c(raw[:44])!=w[11]:raise ValueError('Edge identity/CRC failed')
 return dict(start_cycles=w[2],stop_cycles=w[3],reads_begin=w[4],errors_begin=w[5],reads_edges=w[6],errors_edges=w[7],
  reads_stop=w[8],errors_stop=w[9],flags=w[10],quiet_reads=(w[6]-w[4])&0xffffffff,
  quiet_errors=(w[7]-w[5])&0xffffffff,edge_reads=(w[8]-w[6])&0xffffffff,edge_errors=(w[9]-w[7])&0xffffffff,
  edge_ms=((w[3]-w[2])&0xffffffff)/170000 if w[10]&1 else None)
