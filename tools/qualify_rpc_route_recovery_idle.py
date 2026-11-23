"""Stopped-board route reconnect qualification; never motor/CLEAR/reset commands."""
import json,subprocess,shlex,time
import prepare_rpc_route_recovery as p
import install_bkin_boot_armed_pair as io
from install_clear_recovery import safe

def main():
    out=p.OUT/'idle_qualification_r2';out.mkdir(exist_ok=False)
    io.URL='http://127.0.0.1:18080'
    result=dict(passed=False,START=0,CLEAR=0,ARM=0,nucleo_RESET=0,nucleo_flash=0,route_reconnect_count=0)
    statuses=[]
    def get(label):
        start=time.monotonic();s=io.live_status();safe(s,p.NEW)
        p.write(out/(label+'.json'),json.dumps(s,ensure_ascii=False,indent=2)+'\n')
        assert s['mc_current_zero_ready']==1 and s['algorithm_fast_cycles']<=4000
        assert s['mc_sd_live']['level']=='HIGH' and s['mc_sd_live']['break_irq_enabled']
        statuses.append((time.monotonic()-start,s));return s
    try:
        before=get('before_reconnect')
        # Same router serial reconnect that previously left method get unavailable.
        # No MCU reset, no registration owned by another client is removed.
        code='''import sys,json
sys.path.insert(0,'/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi')
from server import RouterClient
c=RouterClient('/var/run/arduino-router.sock')
for action in ('close','open'):
 r=c.call('$/serial/'+action,['/dev/ttyHS1'],timeout=5,retries=0)
 assert r is not None and r[2] is None and r[3] is True,r
 print(json.dumps({'action':action,'response':r}))
'''
        cmd=['adb','-s',io.UNO_SERIAL,'shell','/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python -c '+shlex.quote(code)]
        result['route_reconnect_count']=1
        r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
        p.write(out/'route_reconnect.log',r.stdout+r.stderr);r.check_returncode()
        began=time.monotonic();failures=[]
        for i in range(12):
            try:
                s=get('recovered_'+str(i))
                if s['rpc_route_renewed']>before['rpc_route_renewed']:break
            except Exception as e:failures.append(str(e))
            time.sleep(.25)
        else:raise AssertionError('No confirmed new MCU registration after reconnect')
        result['restoration_observed_s']=time.monotonic()-began
        result['transient_GET_errors']=failures
        for i in range(20):get('steady_'+str(i))
        ticks=[s['native_boot']['native_tick_ms'] for _,s in statuses]
        assert all(b>=a for a,b in zip(ticks,ticks[1:])),'Native reboot observed'
        last=statuses[-1][1]
        assert last['linux_boot_id']==before['linux_boot_id']
        assert last['rpc_route_failures']==before['rpc_route_failures']
        for key in ('rpc_response_timeouts','rpc_send_timeouts','mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags'):
            assert last[key]==before[key],key
        assert last['bp_good']>before['bp_good']
        expected=p.BASE/'release/nucleo_2026111606_expected_readback.bin'
        cmd=[str(io.PROGRAMMER),'-c','port=SWD','mode=HOTPLUG','sn='+io.STLINK_SERIAL,
            '-u','0x08000000',str(expected.stat().st_size),str(out/'native_after_readback.bin')]
        r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
        p.write(out/'native_readback.log',r.stdout+r.stderr);r.check_returncode()
        assert (out/'native_after_readback.bin').read_bytes()==expected.read_bytes()
        history=json.loads(p.read(p.OUT/'preserved_all_hashes.json'))
        for rel,h in history.items():assert p.sha(p.ROOT/rel)==h,rel
        result.update(passed=True,samples=len(statuses),max_HTTP_s=max(t for t,_ in statuses),
            native_tick_before=ticks[0],native_tick_after=ticks[-1],native_readback_identical=True,
            renewed_before=before['rpc_route_renewed'],renewed_after=last['rpc_route_renewed'],
            route_failures=last['rpc_route_failures'],fast_cycles=last['algorithm_fast_cycles'],
            preserved_files=len(history),limitations='OFF route-loss recovery only; original PWM-related outage and 5-second FOC remain unqualified.')
    except Exception as e:result['error']=str(e)
    p.write(out/'report.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=True));return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
