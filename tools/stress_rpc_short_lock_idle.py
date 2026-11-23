"""Long GET-only idle qualification; stop at first failure, never reconnect/reset/clear."""
import json,time,urllib.request
import prepare_rpc_short_lock as p
from rpc_counter_guard import RpcCounterGuard
from run_foc_boot_capture_trial import decode_boot

def main():
    out=p.OUT/'long_idle_r4';out.mkdir(exist_ok=False)
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}));token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
    guard=RpcCounterGuard(lambda s,**kw:decode_boot(s,p.NEW,**kw))
    report=dict(passed=False,duration_required_s=1100,START=0,CLEAR=0,RESET=0,flash=0,router_reconnect=0,HTTP_methods=['GET'],
        scope='RPC idle only; native UART fault history is recorded and must remain unchanged. Motor readiness still requires zero faults.',FOC_start_ready=False)
    began=time.monotonic();progress=began;samples=0;max_latency=0;previous_tick=None;first=None;last=None
    try:
        while time.monotonic()-began<1100 or samples<20:
            start=time.monotonic()
            req=urllib.request.Request('http://127.0.0.1:18080/api/status',headers={'X-UNOQ-Control-Token':token})
            with op.open(req,timeout=8) as f:r=json.load(f)
            assert r['ok'];s=r['data'];samples+=1;max_latency=max(max_latency,time.monotonic()-start)
            with (out/'statuses.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(dict(t=time.monotonic()-began,response=r),ensure_ascii=False)+'\n')
            assert (s['fw_build'],s['mc_fw_build'])==p.NEW
            assert s['state']=='SAFE' and s['pwm']==s['hmi_hv_armed']==s['run_id']==0
            assert 0<=s['vdc']<20 and s['mc_current_zero_ready']==1
            assert s['mc_sd_live']['level']=='HIGH' and s['mc_sd_live']['break_irq_enabled']
            assert s['mc_current_zero_stable']==3
            assert 0<=s['mc_age_ms']<300 and 0<s['algorithm_fast_cycles']<=4000
            assert guard.observe(s),guard.failure
            tick=s['native_boot']['native_tick_ms']
            assert previous_tick is None or tick>=previous_tick,'Native uptime decreased'
            previous_tick=tick
            if first is None:first=s
            last=s
            assert s['mc_transport_fault']==first['mc_transport_fault'],'Native transport fault changed'
            for k in ('mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags','uno_rx_hw_errors','uno_rx_dropped'):
                assert s[k]==first[k],(k,'counter changed',first[k],s[k])
            if time.monotonic()-progress>=45:
                progress=time.monotonic()
                print(json.dumps(dict(elapsed_s=round(progress-began),samples=samples,RPC_guard_ready=guard.ready,RPC_new_error=guard.failure,
                    route_attempts=s['rpc_route_attempts'],route_failures=s['rpc_route_failures'],CPU=s['algorithm_fast_cycles'],autonull=s['mc_current_zero_ready'])),flush=True)
            time.sleep(.2)
        assert guard.ready and guard.failure is None
        history=json.loads(p.read(p.OUT/'preserved_all_hashes.json'))
        for rel,h in history.items():assert p.sha(p.ROOT/rel)==h,rel
        report.update(passed=True,preserved_files=len(history),native_tick_before=first['native_boot']['native_tick_ms'],native_tick_after=last['native_boot']['native_tick_ms'],
            good_frames_added=last['mc_good_cnt']-first['mc_good_cnt'],route_attempts=last['rpc_route_attempts'],route_failures=last['rpc_route_failures'],
            saved_native_transport_fault=last['mc_transport_fault'],
            saved_UART_history={k:last[k] for k in ('mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags','uno_rx_hw_errors','uno_rx_dropped')})
    except Exception as e:report['error']=str(e)
    finally:
        report.update(samples=samples,elapsed_s=time.monotonic()-began,max_HTTP_latency_s=max_latency,RPC_guard=guard.snapshot())
        if last:p.write(out/'final_status.json',json.dumps(last,ensure_ascii=False,indent=2)+'\n')
        p.write(out/'report.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=True),flush=True);return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
