// Native fault injection against the ACTUAL vendor headers; no bench commands.
#include <bridge.h>
#include <deque>
#include <vector>
#include <iostream>
#include <cassert>
#include <set>
#include "rpc_route_policy.h"
static void check_arg(bool okay){if(!okay)throw std::runtime_error("bad register args");}
class FakeSerial:public HardwareSerial {
public:
 using Stream::write;
 std::deque<uint8_t>rx;
 std::vector<uint8_t>tx;
 std::vector<std::vector<uint8_t>>responses;
 uint32_t lost_id=0,last_id=0;
 int room=7,write_calls=0;
 bool suppress_reset=false,drop_register=false;std::set<std::string> routes;
 int available()override{return static_cast<int>(rx.size());}
 int availableForWrite()override{return room;}
 void feed(const MsgPack::Packer&p){for(size_t i=0;i<p.size();++i)rx.push_back(p.data()[i]);}
 void reply(uint32_t id){MsgPack::Packer p;MsgPack::object::nil_t nil;p.serialize(MsgPack::arr_size_t(4),1,id,nil,true);feed(p);}
 void request(uint32_t id,const std::string&method){MsgPack::Packer p;p.serialize(MsgPack::arr_size_t(4),0,id,method,MsgPack::arr_size_t(0));feed(p);}
 size_t write(const uint8_t*d,size_t n)override{
  ++write_calls;
  if(n&&d[0]=='M')return n; // Vendor boot banner, deliberately not a packet.
  tx.insert(tx.end(),d,d+n);MsgPack::Unpacker u;
  if(!u.feed(tx.data(),tx.size()))return n;
  size_t complete_size;int complete_type=NO_MSG;
  if(!RpcUtils::detail::unpackTypedArray(u,complete_size,complete_type))return n;
  u.clear();u.feed(tx.data(),tx.size());
  MsgPack::arr_size_t a;int type;
  if(!u.deserialize(a,type))return n;
  if(type==1){responses.push_back(tx);tx.clear();return n;}
  if(type==2){tx.clear();return n;}
  uint32_t id;std::string method;
  assert(u.deserialize(id,method));last_id=id;tx.clear();
  if(method==RESET_METHOD&&suppress_reset)return n;
  if(method==BIND_METHOD){std::string name;MsgPack::arr_size_t args;check_arg(u.deserialize(args,name));
   if(drop_register)return n;routes.insert(name);reply(id);return n;}
  if(method=="no_reply"){lost_id=id;return n;}
  if(method=="late_then_good")reply(lost_id);
  reply(id);return n;
 }
 size_t readBytes(uint8_t*d,size_t n)override{size_t k=std::min(n,rx.size());for(size_t i=0;i<k;++i){d[i]=rx.front();rx.pop_front();}return k;}
};
FakeSerial serial;
BridgeClass Bridge(serial);
static void check(bool okay,const char*what){if(!okay)throw std::runtime_error(what);}
int main(int argc,char**argv){
 try{
 check(argc==2,"scenario required");std::string scenario=argv[1];
 bool value=false;
#ifdef MIC_BOOT_RETRY
 if(scenario=="boot_retry"){
  serial.suppress_reset=true;auto start=millis();check(!Bridge.begin(),"missing reset reply accepted");
  check(millis()-start==1500,"initial handshake deadline");
  serial.suppress_reset=false;check(Bridge.begin(),"retry did not connect");
  check(fake_thread_creates==1,"retry created another updater");
  check(Bridge.begin()&&fake_thread_creates==1,"connected begin recreated updater");
  check(Bridge.call("good").result(value)&&value,"RPC failed after startup retry");
  std::cout<<"PASS boot_retry simulated_ms="<<millis()<<"\n";return 0;
 }
#endif
 check(Bridge.begin(),"begin handshake");
 if(scenario=="renew"){
  int calls=0;check(Bridge.provide("get",[&](){++calls;return true;}),"initial registration");
  check(serial.routes.count("get"),"route absent");
  serial.routes.clear(); // Same observed router-side loss; MCU is NOT reset.
  check(!serial.routes.count("get"),"loss not injected");
  check(!Bridge.provide("get",[&](){calls+=100;return false;}),"duplicate callback accepted");
  serial.routes.clear();
#ifdef MIC_ROUTE_FIXED
  for(unsigned i=0;i<300;++i){
   check(Bridge.refreshProvided("get"),"route not renewed");
   check(serial.routes.count("get"),"router route absent after renewal");
   serial.request(1000+i,"get");Bridge.update();
  }
  check(calls==300,"original callback replaced or lost");
  auto begin=millis();serial.drop_register=true;
  check(!Bridge.refreshProvided("get"),"lost registration ACK accepted");
  check(millis()-begin==1500,"renewal timeout changed");
  serial.drop_register=false;check(Bridge.refreshProvided("get"),"renewal failed after timeout");
  check(!Bridge.refreshProvided("missing"),"unbound method registered");
  check(fake_thread_creates==1,"renewal recreated MCU updater");
  RpcRoutePolicy policy{};
  check(!policy.due(4999,false,false,false,true),"early renewal");
  for(unsigned bits=1;bits<8;++bits)
   check(!policy.due(5000,bits&1,bits&2,bits&4,true),"renewal admitted with PWM");
  check(!policy.due(5000,false,false,false,false),"unready renewal");
  check(policy.due(5000,false,false,false,true),"OFF renewal omitted");
  check(!policy.due(9999,false,false,false,true),"renewal flood");
  check(policy.due(10000,false,false,false,true),"renewal interval");
  policy.finish(10001,false);policy.finish(10002,true);
  check(policy.failures==1&&policy.attempts==2&&policy.last_success==10002,"diagnostics");
  policy.last_attempt=0xfffffff0U;
  check(!policy.due(10,false,false,false,true),"wrap early");
  check(policy.due(5000,false,false,false,true),"wrap renewal absent");
#else
  check(!serial.routes.count("missing"),"unexpected state");
  // Old bridge has no refresh API; cached flags leave the route absent forever.
  for(unsigned i=0;i<300;++i)Bridge.update();
  check(calls==0&&!serial.routes.count("get"),"old missing-route failure not reproduced");
#endif
  std::cout<<"PASS renew calls="<<calls<<"\n";return 0;
 }
 else if(scenario=="baseline"){
  bool reproduced=false;try{Bridge.call("no_reply").result(value);}catch(const std::runtime_error&){reproduced=true;}
  check(reproduced,"original unbounded wait not reproduced");
 }
#ifdef MIC_PATCHED
 else if(scenario=="lost"||scenario=="late"){
  auto start=millis();check(!Bridge.call("no_reply").result(value),"lost response accepted");
  check(millis()-start==1500,"response deadline");check(mic_rpc_health.response_timeouts==1,"timeout counter");
  check(Bridge.call(scenario=="late"?"late_then_good":"good").result(value)&&value,"next call did not recover");
  check(mic_rpc_health.late_responses==(scenario=="late"?1U:0U),"late response counter");
 }
 else if(scenario=="unknown"||scenario=="tagged"){
  int got=0;auto callback=[&](){++got;return true;};
  check(scenario=="tagged"?Bridge.provide_safe("get",callback):Bridge.provide("get",callback),"register");
  if(scenario=="unknown"){
   serial.request(900,"missing");serial.request(901,"get");Bridge.update();Bridge.update();
   check(got==1&&serial.responses.size()==2,"unknown request blocked following get");
   MsgPack::Unpacker u;auto&r=serial.responses.front();check(u.feed(r.data(),r.size()),"response parse");
   MsgPack::arr_size_t a;int type;uint32_t id;RpcError error;MsgPack::object::nil_t nil;
   check(u.deserialize(a,type,id,error,nil)&&type==1&&id==900&&error.code==FUNCTION_NOT_FOUND_ERR,"unknown error response");
   check(mic_rpc_health.unknown_methods==1,"unknown counter");
  }else{
   serial.request(902,"get");Bridge.update();check(got==0&&serial.responses.empty(),"wrong tag was consumed");
   BridgeClassUpdater::safeUpdate(&Bridge);check(got==1&&serial.responses.size()==1,"safe update lost known method");
  }
 }
 else if(scenario=="generic"){
  SerialTransport t(serial);RPCClient client(t);serial.reply(77);RpcError error;
  check(!client.get_response(78,value,error),"unmatched response accepted");
  check(client.get_response(77,value,error)&&value,"generic concurrent response was discarded");
 }
 else if(scenario=="tx"){
  serial.room=0;auto start=millis();check(!Bridge.call("good").result(value),"zero TX room accepted");
  check(millis()-start==2000&&mic_rpc_health.send_timeouts==1,"TX no progress deadline");
  serial.room=7;check(Bridge.call("good").result(value)&&value,"next call after TX failure");
 }
 else if(scenario=="admission"||scenario=="mutex"){
  SerialTransport t(serial);RPCClient client(t);k_mutex read{},write{},outgoing{};
  if(scenario=="admission")outgoing.held=1;else write.held=1;
  auto start=millis();auto calls=serial.write_calls;
  check(!RpcCall<>("good",&client,&read,&write,&outgoing).result(value),"busy mutex accepted");
  check(millis()-start>=1500&&millis()-start<1520&&serial.write_calls==calls,"mutex wait unbounded or sent");
 }
#endif
 else throw std::runtime_error("unknown scenario");
 std::cout<<"PASS "<<scenario<<" simulated_ms="<<millis()<<"\n";return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}
}
