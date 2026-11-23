"""Replay exact captured Linux->MCU bytes through real decoder/server/client, PC only."""
import json,subprocess
from pathlib import Path
import prepare_rpc_short_lock as p

CODE=r'''
#include <Arduino_RPClite.h>
#include <fstream>
#include <vector>
#include <iostream>
#include <cassert>
struct Wire: ITransport {
 std::vector<uint8_t> data,tx;size_t fed=0,position=0,chunk=1;
 bool available()override{return position<fed;}
 size_t read(uint8_t*b,size_t n)override{n=std::min({n,fed-position,chunk});memcpy(b,data.data()+position,n);position+=n;return n;}
 size_t read_byte(uint8_t&b)override{return read(&b,1);}
 size_t write(const uint8_t*b,size_t n)override{tx.insert(tx.end(),b,b+n);return n;}
};
int main(int argc,char**argv){
 Wire t;std::ifstream in(argv[1],std::ios::binary);t.data.assign(std::istreambuf_iterator<char>(in),{});
 t.chunk=std::stoul(argv[2]);int order=std::stoi(argv[3]),preempt=std::stoi(argv[4]),count=0;
 RPCClient client(t);RPCServer server(t);bool value=false;RpcError error;
 auto poll=[&](){client.get_response(344,value,error,true);};
 server.bind("get",[&](){++count;if(preempt)poll();return true;});
 for(unsigned i=0;i<20000;++i){
  t.fed=std::min(t.data.size(),t.fed+t.chunk);
  RPCRequest<> req;
  if(order)poll();
  if(server.get_rpc(req)){server.process_request(req);server.send_response(req);}
  if(!order)poll();
 }
 std::cout<<count<<"\n";return 0;
}
'''
def main():
    out=p.OUT/'wire_replay_r1';out.mkdir(exist_ok=False);p.write(out/'fixture.cpp',CODE)
    includes=[p.ROOT/'tools/rpc_coldboot_native',p.OUT/'libraries/Arduino_RPClite/src']
    includes += [Path.home()/'Documents/Arduino/libraries'/n for n in ('MsgPack','ArxContainer','ArxTypeTraits','DebugLog')]
    exe=out/'fixture.exe'
    r=subprocess.run(['g++','-std=c++17','-O2','-D_GLIBCXX_ASSERTIONS']+['-I'+str(x) for x in includes]+[str(out/'fixture.cpp'),'-o',str(exe)],capture_output=True,text=True)
    p.write(out/'compile.log',r.stdout+r.stderr);r.check_returncode()
    wire=p.OUT/'wire_isolation_r1/to_MCU.bin'
    import msgpack
    u=msgpack.Unpacker(raw=False);u.feed(wire.read_bytes());objects=list(u)
    expected=sum(1 for x in objects if isinstance(x,list) and len(x)==4 and x[0]==0 and x[2]=='get')
    results=[]
    for chunk in (1,2,3,4,5,6,7,8,9,16,31,32,63,64,256,1024):
        for order in (0,1):
            for preempt in (0,1):
                r=subprocess.run([str(exe),str(wire),str(chunk),str(order),str(preempt)],capture_output=True,text=True,timeout=5)
                case=dict(chunk=chunk,order=order,preempt=preempt,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr)
                case['passed']=r.returncode==0 and r.stdout.strip()==str(expected);results.append(case)
    report=dict(passed=all(x['passed'] for x in results),expected_GET=expected,cases=results,hardware_commands=0,
        scope='Exact recorded request stream, real RPClite, two polling orders and callback preemption. Kernel/UART mocked.')
    p.write(out/'report.json',json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='cases'}));print('failed',sum(not x['passed'] for x in results))
if __name__=='__main__':main()
