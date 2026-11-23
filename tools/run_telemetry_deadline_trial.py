"""Future authorized1603/1604 bounded trial; import does not access devices."""
import prepare_telemetry_deadline as p
import run_observer_input_epoch_trial as driver
from release_observer_decoder import load_decoder
from rpc_counter_guard import RpcCounterGuard
import argparse
import json
import time
import urllib.request
from pathlib import Path

driver.package=p
driver.trial.PAIR=p.NEW
driver.boot.package=p
driver.boot.trial=driver.trial
driver.capture.package=p
driver.capture.base=driver.boot
driver.capture.decode_observer_trace_hex=load_decoder(p.OUT)


def prepare_rpc_guard(fetch, directory, *, clock=time.monotonic, sleep=time.sleep):
    """GET-only quiet preflight. A failure is archived and cannot be retried here."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    guard=RpcCounterGuard(lambda s,**kw:driver.boot.decode_boot(s,p.NEW,**kw),clock=clock)
    try:
        for _ in range(30):
            response=fetch()
            with (directory/'status.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps(dict(monotonic=clock(),response=response),ensure_ascii=False)+'\n')
            if response.get('ok') is not True:raise RuntimeError('RPC status request rejected')
            s=response['data']
            if not driver.trial.off(s):raise RuntimeError('Outputs not OFF during RPC baseline')
            driver.boot.decode_boot(s,p.NEW)  # Fresh OFF boot pages for the entire quiet preflight.
            if not guard.observe(s):raise RuntimeError(guard.failure)
            if guard.ready:return guard
            sleep(.2)
        raise RuntimeError('RPC baseline did not qualify within bounded quiet observation')
    except Exception as error:
        guard.fail('RPC preflight failed: '+str(error))
        raise
    finally:
        p.write(directory/'report.json',json.dumps(guard.snapshot(),ensure_ascii=False,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-autonomous-powered',action='store_true',required=True)
    parser.add_argument('--clear-once',action='store_true')
    parser.add_argument('--outdir',type=Path,required=True)
    args=parser.parse_args()
    out=args.outdir.resolve()
    assert not out.exists(),'Never replace a previous trial'
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
    def fetch():
        request=urllib.request.Request('http://192.168.1.138:8080/api/status',
            headers={'X-UNOQ-Control-Token':token},method='GET')
        with op.open(request,timeout=8) as response:return json.load(response)
    guard=prepare_rpc_guard(fetch,out.with_name(out.name+'_RPC_preflight'))
    driver.trial.RPC_GUARD=guard
    try:
        return driver.main()
    finally:
        # Includes failures before driver creates its trial directory.
        p.write(out.with_name(out.name+'_RPC_preflight')/'final_guard.json',
            json.dumps(guard.snapshot(),ensure_ascii=False,indent=2)+'\n')
        driver.trial.RPC_GUARD=None


if __name__=='__main__':raise SystemExit(main())
