import json
from analyze_uart_rx_capture import decode
from no_switch_diag_snapshot_io import crc32c
def edges(raw,badstop=False):
 t=.001;bit=1/115200;events=[];prev=1
 for n,byte in enumerate(raw):
  for v in [0]+[(byte>>i)&1 for i in range(8)]+[0 if badstop and n==0 else 1]:
   if v!=prev:events.append((round(t/125e-9)*125e-9,v));prev=v
   t+=bit
 return events,t+.001
def main():
 raw=bytearray(39);raw[:3]=b'\xaa\x55\x03';raw[5]=173;raw+=crc32c(raw).to_bytes(4,'little')
 e,end=edges(raw*3);r=decode(e,end=end);assert r['valid_frames']==3 and not r['framing_errors'] and r['frames'][0]['raw_hex']==raw.hex()
 bad=raw.copy();bad[10]^=1;e,end=edges(bad);r=decode(e,end=end);assert r['valid_frames']==0 and len(r['invalid_candidate_frames'])==1
 e,end=edges(raw,True);r=decode(e,end=end);assert r['valid_frames']==0 and r['framing_errors']
 print(json.dumps(dict(passed=True,clean_back_to_back_frames=3,CRC_corruption_rejected=True,stop_bit_error_rejected=True,sample_resolution_ns=125,hardware_calls=0)))
if __name__=='__main__':main()
