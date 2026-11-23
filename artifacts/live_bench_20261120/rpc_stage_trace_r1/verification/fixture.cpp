
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

 const uint32_t end=mic_rpc_trace.next;
 for(uint32_t seq=end>128?end-127:1;seq<=end;++seq){
  const auto&r=mic_rpc_trace.rows[(seq-1)&127];
  assert(r.sequence==seq);
  assert(r.guard==(seq^r.ms^r.event^r.a^r.b^r.c^r.d^0x91e6b72dU));
 }
 // Wrap the diagnostic journal without affecting decoder/callback state.
 for(unsigned i=0;i<300;++i)mic_rpc_note(99,i);
 assert(mic_rpc_trace.next==end+300);
 for(uint32_t seq=end+173;seq<=end+300;++seq){
  const auto&r=mic_rpc_trace.rows[(seq-1)&127];assert(r.sequence==seq&&r.event==99);
 }
 std::cout<<count<<"\n";return 0;
}
