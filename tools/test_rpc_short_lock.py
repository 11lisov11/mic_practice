"""Reproduce captured lock chain using real Bridge/RPClite headers; PC only."""
import json,subprocess
from pathlib import Path
import prepare_rpc_short_lock as p

def main():
    out=p.OUT/'verification';out.mkdir(exist_ok=False)
    fixture=p.read(p.BASE/'verification_router053/route_fixture.cpp')
    fixture=fixture.replace('static void check_arg', 'static bool test_route_lock_held();\nstatic bool checking_lock=false;static unsigned blocked=0,admitted=0;\nstatic void check_arg')
    fixture=fixture.replace('if(method==BIND_METHOD){', 'if(method==BIND_METHOD){if(checking_lock){if(test_route_lock_held())++blocked;else ++admitted;}')
    fixture=fixture.replace('BridgeClass Bridge(serial);','BridgeClass Bridge(serial);\nstatic bool test_route_lock_held(){return Bridge.bridge_mutex.held!=0;}')
    fixture=fixture.replace('for(unsigned i=0;i<300;++i){','checking_lock=true;\n  for(unsigned i=0;i<300;++i){')
    fixture=fixture.replace('std::cout<<"PASS renew calls="', '''
#ifdef EXPECT_OLD_LOCK
  check(blocked>=600 && admitted==0,"old lock starvation not reproduced");
#else
  check(blocked==0 && admitted>=600,"updater blocked by registration wait");
#endif
  std::cout<<" blocked="<<blocked<<" admitted="<<admitted<<" ";
  std::cout<<"PASS renew calls="''')
    p.write(out/'fixture.cpp',fixture)
    cases=[]
    for old,folder in ((True,p.BASE),(False,p.OUT)):
        label='baseline' if old else 'candidate';inc=out/(label+'_headers');inc.mkdir()
        # Visibility only, no behavior change: inspect actual Zephyr mutex owner.
        bridge=p.read(folder/'libraries/Arduino_RouterBridge/src/bridge.h')
        p.write(inc/'bridge.h',p.once(bridge,'class BridgeClass {','class BridgeClass {\npublic: // host-fixture visibility only'))
        include=[inc,p.ROOT/'tools/rpc_coldboot_native',folder/'libraries/Arduino_RouterBridge/src',folder/'libraries/Arduino_RPClite/src',folder/'UNOQ_MOTOR']
        include += [Path.home()/'Documents/Arduino/libraries'/n for n in ('MsgPack','ArxContainer','ArxTypeTraits','DebugLog')]
        cmd=['g++','-std=c++17','-O2','-Wall','-Wextra','-DMIC_PATCHED','-DMIC_ROUTE_FIXED']
        if old:cmd+=['-DEXPECT_OLD_LOCK']
        exe=out/(label+'.exe');cmd+=['-I'+str(x) for x in include]+[str(out/'fixture.cpp'),'-o',str(exe)]
        r=subprocess.run(cmd,capture_output=True,text=True);p.write(out/(label+'_build.log'),r.stdout+r.stderr);r.check_returncode()
        for case in ('renew','lost','late','unknown','tagged','generic','tx','admission','mutex'):
            r=subprocess.run([str(exe),case],capture_output=True,text=True,timeout=15)
            p.write(out/(label+'_'+case+'.log'),r.stdout+r.stderr)
            cases.append(dict(candidate=not old,case=case,passed=r.returncode==0,output=r.stdout+r.stderr));r.check_returncode()
    # Normalize only build identities: every safety gate and control line remains identical.
    for rel in ('UNOQ_MOTOR/UNOQ_MOTOR.ino','web_hmi/server.py'):
        assert p.read(p.OUT/rel).replace('2026111609','2026111607')==p.read(p.BASE/rel),rel
    history=json.loads(p.read(p.OUT/'preserved_all_hashes.json'))
    for rel,h in history.items():assert p.sha(p.ROOT/rel)==h,rel
    report=dict(passed=True,cases=cases,actual_RPC_headers=True,kernel_UART_router_mocked=True,
        old_captured_mutex_wait_reproduced=True,registration_wait_does_not_hold_bridge_mutex=True,
        timeout_1500_unchanged=True,motor_guards_normalized_identical=True,
        preserved_files=len(history),original_serial_failure_byte_identified=False,hardware_commands=0)
    p.write(out/'report.json',json.dumps(report,indent=2)+'\n');print(json.dumps(dict(passed=True,cases=len(cases),preserved=len(history))))
if __name__=='__main__':main()
