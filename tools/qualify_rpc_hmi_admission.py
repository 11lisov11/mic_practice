"""Concurrent HTTP GETs plus sustained idle qualification. No bench mutations."""
import json,time,urllib.request,threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import prepare_rpc_hmi_admission as p
import prepare_rpc_short_lock as fw
import stress_rpc_short_lock_idle as old


def fanout():
    out=p.OUT/'HTTP_fanout_r1';out.mkdir(exist_ok=False)
    token=(p.ROOT/'.unoq_ssh/control_token').read_text().strip();barrier=threading.Barrier(16)
    def call(index):
        barrier.wait();t=time.monotonic()
        req=urllib.request.Request('http://127.0.0.1:18080/api/status',headers={'X-UNOQ-Control-Token':token})
        with urllib.request.urlopen(req,timeout=8) as f:r=json.load(f)
        assert r['ok'];s=r['data'];assert s['state']=='SAFE' and s['pwm']==0 and s['hmi_hv_armed']==0
        assert s['algorithm_fast_cycles']<=4000 and 0<=s['mc_age_ms']<300
        return dict(index=index,latency_s=time.monotonic()-t,RPC_timeouts=s['rpc_response_timeouts'],
                    native_tick=s['native_boot']['native_tick_ms'],run_id=s['run_id'])
    t=time.monotonic()
    with ThreadPoolExecutor(16) as pool:rows=list(pool.map(call,range(16)))
    assert all(x['run_id']==0 for x in rows) and len({x['RPC_timeouts'] for x in rows})==1
    assert max(x['latency_s'] for x in rows)<4
    report=dict(passed=True,HTTP_GET=16,elapsed_s=time.monotonic()-t,rows=rows,START=0,CLEAR=0,ARM=0,reset=0)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='rows'}),flush=True)


def main():
    assert json.loads((p.OUT/'install_r1/report.json').read_text())['Linux_server_readback_verified']
    fanout()
    # Reuse the existing fail-closed guards, including boot/SD/CRC/CPU/live-RSP.
    # Keep each previous failed report intact under its old directory.
    import inspect
    s=inspect.getsource(old.main).replace("p.OUT/'long_idle_r4'","p.OUT/'long_idle_r1'")
    s=s.replace("last['mc_good_cnt']-first['mc_good_cnt']","last['uno_rx_count']-first['uno_rx_count']")
    old.p=SimpleNamespace(OUT=p.OUT,ROOT=p.ROOT,NEW=fw.NEW,read=fw.read,write=fw.write,sha=fw.sha)
    (p.OUT/'preserved_all_hashes.json').write_bytes((fw.OUT/'preserved_all_hashes.json').read_bytes())
    exec(compile(s,__file__,'exec'),old.__dict__)
    return old.main()


if __name__=='__main__':raise SystemExit(main())
