"""Exercise real RouterClient with a PC-loopback MsgPack peer, never the bench."""
import importlib.util,json,socketserver,threading,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import msgpack
import prepare_rpc_hmi_admission as p


def module(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


class Peer:
    def __init__(self,delay=0.04,drop_first=False,split=False):
        self.delay=delay;self.drop_first=drop_first;self.split=split;self.messages=[];self.lock=threading.Lock()
        outer=self
        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                u=msgpack.Unpacker(raw=False)
                try:
                    while True:
                        b=self.request.recv(65536)
                        if not b:return
                        u.feed(b)
                        for r in u:
                            with outer.lock:outer.messages.append(r);number=len(outer.messages)
                            if outer.drop_first and number==1:
                                time.sleep(outer.delay);return
                            time.sleep(outer.delay)
                            body=('DATA '+str(number)+'x'*8163) if outer.split else str(number)
                            reply=msgpack.packb([1,r[1],None,body])
                            if outer.split:
                                for i in range(0,len(reply),97):self.request.sendall(reply[i:i+97])
                            else:self.request.sendall(reply)
                except (ConnectionError,OSError):return
        class Server(socketserver.ThreadingTCPServer):allow_reuse_address=True;daemon_threads=True
        self.server=Server(('127.0.0.1',0),Handler);self.endpoint='%s:%d'%self.server.server_address
        self.thread=threading.Thread(target=lambda:self.server.serve_forever(poll_interval=.01),daemon=True);self.thread.start()
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join()


def fanout(m,n=16,drop=False):
    peer=Peer(.12,drop_first=drop);c=m.RouterClient(peer.endpoint);barrier=threading.Barrier(n)
    def call(_):barrier.wait();return c.call('get',[],timeout=3,retries=0)
    try:
        t=time.monotonic()
        with ThreadPoolExecutor(n) as pool:r=list(pool.map(call,range(n)))
        return dict(wire_requests=len(peer.messages),all_replied=all(x is not None for x in r),
                    all_none=all(x is None for x in r),elapsed_s=time.monotonic()-t)
    finally:c.close();peer.close()


def admission(m):
    peer=Peer(.001);c=m.RouterClient(peer.endpoint);c._lock.acquire();out={}
    def call():
        t=time.monotonic();out['reply']=c.call('marker',[],timeout=.03,retries=0);out['elapsed_s']=time.monotonic()-t
    t=threading.Thread(target=call);t.start();time.sleep(.16);c._lock.release();t.join(2)
    try:assert not t.is_alive();out['wire_requests']=len(peer.messages);return out
    finally:c.close();peer.close()


def main():
    out=p.OUT/'verification';out.mkdir(exist_ok=False)
    old=module(p.BASE/'web_hmi/server.py','baseline_rpc');new=module(p.OUT/'web_hmi/server.py','candidate_rpc')
    cases={}
    cases['old_admission']=admission(old);cases['new_admission']=admission(new)
    assert cases['old_admission']['elapsed_s']>=.15 and cases['new_admission']['elapsed_s']<.1
    assert cases['new_admission']['reply'] is None and cases['new_admission']['wire_requests']==0
    cases['old_fanout']=fanout(old);cases['new_fanout']=fanout(new)
    assert cases['old_fanout']['wire_requests']==16 and cases['old_fanout']['all_replied']
    assert cases['new_fanout']['wire_requests']==1 and cases['new_fanout']['all_replied']
    peer=Peer(.02);c=new.RouterClient(peer.endpoint)
    try:
        a=c.call('get',[],timeout=1,retries=0);b=c.call('get',[],timeout=1,retries=0)
        assert a[3]!=b[3] and len(peer.messages)==2;cases['no_completed_reply_cache']=True
        marker=c.call('marker',[],timeout=1,retries=0);d=c.call('get',[],timeout=1,retries=0)
        assert d[3]!=b[3] and [x[2] for x in peer.messages]==['get','get','marker','get']
        cases['command_fence_fresh_read']=True
    finally:c.close();peer.close()
    peer=Peer(.12);c=new.RouterClient(peer.endpoint);leader=[]
    t=threading.Thread(target=lambda:leader.append(c.call('get',[],timeout=1,retries=0)));t.start()
    while not peer.messages:time.sleep(.001)
    start=time.monotonic();r=c.call('get',[],timeout=.02,retries=0);elapsed=time.monotonic()-start;t.join(2)
    assert r is None and elapsed<.08 and leader[0] and len(peer.messages)==1
    c.close();peer.close();cases['follower_has_own_deadline']=True
    peer=Peer(.001,drop_first=True);c=new.RouterClient(peer.endpoint)
    try:
        assert c.call('cmd',['START'],timeout=.05,retries=0) is None
        assert len(peer.messages)==1 # Mock peer only. No start retry.
        assert c.call('get',[],timeout=1,retries=0) is not None
        cases['command_never_implicitly_retried']=True
    finally:c.close();peer.close()
    dropped=fanout(new,drop=True)
    assert dropped['wire_requests']==1 and dropped['all_none']
    cases['failed_flight_fails_all_readers']=dropped
    peer=Peer(.01,drop_first=True);c=new.RouterClient(peer.endpoint)
    try:
        assert c.call('get',[],timeout=1,retries=0) is None
        assert c.call('get',[],timeout=1,retries=0) is not None
        cases['failed_flight_does_not_cache_failure']=True
    finally:c.close();peer.close()
    peer=Peer(.005,split=True);c=new.RouterClient(peer.endpoint)
    new._now_ts=lambda: (_ for _ in ()).throw(RuntimeError('Wall clock must not be a transport timer'))
    try:
        r=c.call('get',[],timeout=1,retries=0);assert r and len(r[3])>8163
        cases['large_fragmented_reply']=True;cases['transport_uses_monotonic_clock']=True
    finally:c.close();peer.close()
    original=(p.BASE/'web_hmi/server.py').read_text(encoding='utf8');candidate=(p.OUT/'web_hmi/server.py').read_text(encoding='utf8')
    assert original.split('class SerialClient:',1)[1]==candidate.split('class SerialClient:',1)[1]
    report=dict(passed=True,cases=cases,hardware_commands=0,network_scope='PC loopback fake peer only',
        motor_guards_identical=True,firmware_changes=0,old_queue_stall_reproduced=True,
        whole_idle_UART_failure_fixed=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
