import json,socket
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
 sock.settimeout(3)
 sock.connect('/var/run/arduino-router.sock')
 stream=sock.makefile('rb'); seq=0
 def read(n):
  data=stream.read(n)
  if len(data)!=n:raise EOFError('Short RPC response')
  return data
 def call(part,page):
  global seq
  seq+=1
  assert seq<128 and page<128
  sock.sendall(bytes((148,0,seq,167))+b'history'+bytes((146,part,page)))
  if read(4)!=bytes((148,1,seq,192)):raise ValueError('Unexpected reply envelope')
  tag=read(1)[0]
  if 160<=tag<=191:n=tag-160
  elif tag in (217,218,219):n=int.from_bytes(read({217:1,218:2,219:4}[tag]),'big')
  else:raise ValueError('Invalid RPC type')
  if n>480:raise ValueError('Unexpected reply length')
  return read(n).decode('ascii')
 answers=[]
 for part,max_bytes in enumerate((524,22*5120,4*(5120//16))):
  for page in range(16):
   ans=call(part,page);answers.append(ans)
   fields=ans.split();assert len(fields)==5 and fields[0]=='NH',ans[:75]
   total=int(fields[3]);assert 0<=total<=max_bytes
   if (page+1)*192>=total:break
  else:raise ValueError('Captured startup journal larger than bounded retrieval')
 print(json.dumps(answers))
