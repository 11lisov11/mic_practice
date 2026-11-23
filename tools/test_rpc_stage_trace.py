"""Exact recorded request streams through real instrumented RPClite, PC only."""
from pathlib import Path
import subprocess,json,sys
import test_rpc_wire_interleavings as fixture
import prepare_rpc_stage_trace as p

def main():
    out=p.OUT/'verification';out.mkdir()
    code=fixture.CODE.replace(' std::cout<<count<<"\\n";',r'''
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
 std::cout<<count<<"\n";''')
    assert code!=fixture.CODE
    (out/'fixture.cpp').write_text(code)
    includes=[p.ROOT/'tools/rpc_coldboot_native',p.OUT/'libraries/Arduino_RPClite/src']
    includes += [Path.home()/'Documents/Arduino/libraries'/n for n in ('MsgPack','ArxContainer','ArxTypeTraits','DebugLog')]
    exe=out/'fixture.exe'
    r=subprocess.run(['g++','-std=c++17','-O2','-D_GLIBCXX_ASSERTIONS']+['-I'+str(x) for x in includes]+[str(out/'fixture.cpp'),'-o',str(exe)],capture_output=True,text=True)
    (out/'compile.log').write_text(r.stdout+r.stderr);r.check_returncode()
    import msgpack
    results=[]
    for case in ('stock_router_stress_r1','stock_router_stress_r2','stock_router_stress_r4'):
        wire=p.BASE/'FOC_5Hz_20261120_r1/post_STOP_RPC_diagnosis_r1'/case/'to_MCU.bin'
        decoder=msgpack.Unpacker(raw=False);decoder.feed(wire.read_bytes())
        expected=sum(x[0]==0 and x[2]=='get' for x in decoder)
        for chunk in (1,2,3,4,7,8,16,31,32,63,64,256,1024):
            for order in (0,1):
                for preempt in (0,1):
                    r=subprocess.run([str(exe),str(wire),str(chunk),str(order),str(preempt)],capture_output=True,text=True,timeout=4)
                    results.append(dict(case=case,chunk=chunk,order=order,preempt=preempt,
                        expected=expected,got=r.stdout.strip(),passed=r.returncode==0 and r.stdout.strip()==str(expected),stderr=r.stderr))
    report=dict(passed=all(x['passed'] for x in results),cases=results,START=0,CLEAR=0,RESET=0,
        scope='Real decoder/dispatch with RX, pop, header, callback and send tracing; journal consistency/wrap. Kernel/IRQ mocked, no claim of hardware fix.')
    (out/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='cases'}));print('cases',len(results))
    return 0 if report['passed'] else 1

if __name__=='__main__':sys.exit(main())
