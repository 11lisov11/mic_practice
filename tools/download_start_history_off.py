"""Run on Uno Linux after STOP: bounded read-only history RPC, no motor commands.

Only `history(part,page)` is called. The MCU callback rejects reads during RUN.
Existing output directories are never overwritten. Invalid/incomplete records
are retained as evidence with exact=false and cannot be called an exact replay.
"""
import argparse,hashlib,json,socket,time
from pathlib import Path

def collect(call,out):
 out=Path(out);out.mkdir(exist_ok=False)
 epoch=None;exact=True;parts={};sizes={}
 for part,name in enumerate(('meta.bin','rows.bin','checkpoints.bin')):
  data=bytearray();page=0;size=None
  while size is None or len(data)<size:
   reply=call(part,page)
   if not isinstance(reply,str):raise ValueError('History RPC type')
   fields=reply.split()
   if len(fields)!=5 or fields[0]!='NH':raise ValueError('History RPC: '+reply[:80])
   event,flag,total=map(int,fields[1:4]);chunk=b'' if fields[4]=='-' else bytes.fromhex(fields[4])
   if epoch is None:epoch=event
   if event!=epoch or flag not in (0,1) or total<0 or total>5120*22:raise ValueError('Epoch/size changed')
   exact=exact and bool(flag)
   if size is None:size=total
   if total==0 and part in (1,2) and page==0 and not chunk:break
   if total!=size or not 1<=len(chunk)<=192 or len(data)+len(chunk)>size:raise ValueError('Page length/size')
   if len(chunk)!=min(192,size-len(data)):raise ValueError('Short page')
   data+=chunk;page+=1
  path=out/name;path.write_bytes(data);sizes[name]=len(data);parts[name]=hashlib.sha256(data).hexdigest()
 # No checkpoints for fewer than16 rows: part2 is legitimately empty. See the
 # empty-page response in the MCU; never infer success from a timeout.
 report=dict(epoch=epoch,exact=exact,sizes=sizes,sha256=parts,read_only_RPC=True,hardware_commands=0)
 (out/'download.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
 return report

class HistoryRPC:
 def __init__(self,endpoint):
  import msgpack
  self.msgpack=msgpack;self.unpack=msgpack.Unpacker(raw=False);self.number=0
  self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.settimeout(.2);self.sock.connect(endpoint)
 def __call__(self,part,page):
  self.number+=1;self.sock.sendall(self.msgpack.packb([0,self.number,'history',[part,page]],use_bin_type=False))
  end=time.monotonic()+3
  while time.monotonic()<end:
   try:data=self.sock.recv(4096)
   except socket.timeout:continue
   if not data:raise ConnectionError('Router closed')
   self.unpack.feed(data)
   for obj in self.unpack:
    if isinstance(obj,list) and len(obj)==4 and obj[0]==1 and obj[1]==self.number:
     if obj[2] is not None:raise RuntimeError(str(obj[2]))
     return obj[3]
  raise TimeoutError('Read-only history RPC timeout')
 def close(self):self.sock.close()
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--socket',default='/var/run/arduino-router.sock')
 ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();rpc=HistoryRPC(a.socket)
 try:report=collect(rpc,a.out)
 finally:rpc.close()
 print(json.dumps(report))
if __name__=='__main__':main()
