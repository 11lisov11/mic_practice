"""Host checks against actual headers and a simulated router; no hardware actions."""
import ast,json,shutil,subprocess,inspect
import prepare_rpc_route_recovery as p

def sync_unsealed():
    assert not (p.OUT/'source_hashes.json').exists()
    for rel in ('libraries/Arduino_RPClite/src/server.h','libraries/Arduino_RouterBridge/src/bridge.h','UNOQ_MOTOR/UNOQ_MOTOR.ino','web_hmi/server.py'):
        p.write(p.OUT/rel,p.read(p.BASE/rel))
    # Regenerate all modified candidate files from the single preparation source.
    tree=ast.parse(p.read(p.ROOT/'tools/prepare_rpc_route_recovery.py'))
    fun=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    nodes=fun.body
    start=next(i for i,n in enumerate(nodes) if isinstance(n,ast.Assign) and ast.unparse(n).startswith("f = OUT / 'libraries/Arduino_RPClite/src/server.h'"))
    end=next(i for i in range(start,len(nodes)) if isinstance(nodes[i],ast.Assign) and ast.unparse(nodes[i]).startswith('history ='))
    exec(compile(ast.Module(body=nodes[start:end],type_ignores=[]),'<HMI generation>','exec'),p.__dict__)

def main():
    sync_unsealed()
    out=p.OUT/'verification_router053';out.mkdir(exist_ok=True)
    assert not (out/'report.json').exists()
    for f in (p.OUT/'web_hmi').glob('*.py'):ast.parse(p.read(f))
    # Exact HMI predecessor normalization verifies no accidental gate change.
    old=p.read(p.BASE/'web_hmi/server.py').replace('2026111605','2026111607')
    new=p.read(p.OUT/'web_hmi/server.py')
    for key in ('rpc_route_attempts','rpc_route_failures','rpc_route_reply_ms','rpc_route_renewed'):
        new=new.replace(f'                "{key}": int(kv.get("{key}","0")),\n','')
    assert old==new
    src=p.ROOT/'tools/rpc_coldboot_native'
    # Extend the original fixture's REAL MsgPack framing, decoder and dispatcher.
    test=p.read(src/'test.cpp')
    test=test.replace('#include <cassert>','#include <cassert>\n#include <set>\n#include "rpc_route_policy.h"')
    test=test.replace('bool suppress_reset=false;', 'bool suppress_reset=false,drop_register=false;std::set<std::string> routes;')
    test=test.replace('if(method=="no_reply")', '''if(method==BIND_METHOD){std::string name;MsgPack::arr_size_t args;check_arg(u.deserialize(args,name));
   if(drop_register)return n;
   if(routes.count(name)){MsgPack::Packer ep;MsgPack::object::nil_t nil;
    ep.serialize(MsgPack::arr_size_t(4),1,id,RpcError(5,"route already exists: "+name),nil);feed(ep);return n;}
   routes.insert(name);reply(id);return n;}
  if(method=="no_reply")''')
    test=test.replace('class FakeSerial:public HardwareSerial {','static void check_arg(bool okay){if(!okay)throw std::runtime_error("bad register args");}\nclass FakeSerial:public HardwareSerial {')
    marker=' if(scenario=="baseline"){'
    inject=''' if(scenario=="renew"){
  int calls=0;check(Bridge.provide("get",[&](){++calls;return true;}),"initial registration");
  check(serial.routes.count("get"),"route absent");
  serial.routes.clear(); // Same observed router-side loss; MCU is NOT reset.
  check(!serial.routes.count("get"),"loss not injected");
  check(!Bridge.provide("get",[&](){calls+=100;return false;}),"duplicate callback accepted");
  serial.routes.clear();
#ifdef MIC_ROUTE_FIXED
  for(unsigned i=0;i<300;++i){
   check(Bridge.refreshProvided("get")==1,"route not renewed");
   check(serial.routes.count("get"),"router route absent after renewal");
   check(Bridge.refreshProvided("get")==2,"router0.5.3 EXISTS not distinguished");
   serial.request(1000+i,"get");Bridge.update();serial.routes.clear();
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
  policy.finish(10001,0,2);policy.finish(10002,2,2);policy.finish(10003,1,2);
  check(policy.failures==1&&policy.attempts==2&&policy.last_reply==10003&&policy.renewed==1,"diagnostics");
  policy.last_attempt=0xfffffff0U;
  check(!policy.due(10,false,false,false,true),"wrap early");
  check(policy.due(5000,false,false,false,true),"wrap renewal absent");
#else
  check(!serial.routes.count("missing"),"unexpected state");
  // Old bridge has no refresh API; cached flags leave the route absent forever.
  for(unsigned i=0;i<300;++i)Bridge.update();
  check(calls==0&&!serial.routes.count("get"),"old missing-route failure not reproduced");
#endif
  std::cout<<"PASS renew calls="<<calls<<"\\n";return 0;
 }
 else if(scenario=="baseline"){'''
    assert marker in test;test=test.replace(marker,inject)
    p.write(out/'route_fixture.cpp',test)
    results=[]
    for fixed,folder in ((False,p.BASE),(True,p.OUT)):
        exe=out/('candidate.exe' if fixed else 'baseline.exe')
        includes=[src,folder/'libraries/Arduino_RouterBridge/src',folder/'libraries/Arduino_RPClite/src',p.OUT/'UNOQ_MOTOR']
        from pathlib import Path
        includes += [Path.home()/'Documents/Arduino/libraries'/n for n in ('MsgPack','ArxContainer','ArxTypeTraits','DebugLog')]
        cmd=['g++','-std=c++17','-O2','-Wall','-Wextra','-DMIC_PATCHED']
        if fixed:cmd+=['-DMIC_ROUTE_FIXED']
        cmd+=['-I'+str(x) for x in includes]+[str(out/'route_fixture.cpp'),'-o',str(exe)]
        r=subprocess.run(cmd,capture_output=True,text=True);p.write(out/(exe.stem+'_build.log'),r.stdout+r.stderr);r.check_returncode()
        for case in ('renew','lost','late','unknown','tagged','generic','tx','admission','mutex'):
            r=subprocess.run([str(exe),case],capture_output=True,text=True,timeout=10)
            results.append(dict(candidate=fixed,case=case,passed=r.returncode==0,output=r.stdout+r.stderr))
            p.write(out/(exe.stem+'_'+case+'.log'),r.stdout+r.stderr)
            r.check_returncode()
    # FOC code, native binary, and all recorded trials remain byte-for-byte unchanged.
    history=json.loads(p.read(p.OUT/'preserved_hashes.json'))
    for rel,h in history.items():assert p.sha(p.ROOT/rel)==h,rel
    p.write(out/'report.json',json.dumps(dict(passed=True,cases=results,preserved_files=len(history),
        actual_RPC_headers=True,router_UART_kernel_mocked=True,hardware_commands=0,
        HMI_gates_normalized_identical=True,initial_RPC_outage_explained=False),indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=len(results),preserved_files=len(history))))

if __name__=='__main__':main()
