"""PC replay of repeat sequencing; network to the bench is forbidden."""
import sys,json,copy,pathlib,socket,threading,contextlib,io
from unittest.mock import patch
import run_foc_visual_repeat as r

BASE=r.ROOT/'artifacts/live_bench_20261116/rpc_hmi_admission_r1'
INITIAL=json.loads((BASE/'visual_repeat_preflight_r1/status.json').read_text(encoding='utf8'))['data']


class Response:
    def __init__(self,obj):self.raw=json.dumps(obj).encode()
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,*args):return self.raw


class Fake:
    def __init__(self,bad=False):
        self.s=copy.deepcopy(INITIAL);self.requests=[];self.phase=0;self.bad=bad;self.lock=threading.Lock()
    def open(self,q,timeout):
        with self.lock:
            path=q.full_url.split(':8080',1)[1];body=json.loads(q.data) if q.data else None
            self.requests.append((path,body))
            if path=='/api/status':
                self.s['uno_rx_count']+=20
                if self.bad:self.s['mc_sd_live']['level']='LOW'
                if self.phase==1:
                    self.s.update(state='VF_RUN',pwm=1,run_id=2,run_elapsed_ms=1000,run_reason=0);self.phase=2
                elif self.phase==2:
                    self.s.update(state='SAFE',pwm=0,run_id=2,run_elapsed_ms=5000,run_reason=1);self.phase=3
                return Response(dict(ok=True,data=copy.deepcopy(self.s)))
            if path=='/api/cmd':assert body=={'cmd':'SET FREQ 5'};self.s['freq_cmd']=5
            elif path=='/api/hv-arm':self.s['hmi_hv_armed']=1
            elif path=='/api/start-sequence':assert body=={'manual':False,'runlimit_s':5.0};self.phase=1
            elif path=='/api/stop-sequence':self.s.update(state='SAFE',pwm=0,hmi_hv_armed=0)
            elif path!='/api/operator-heartbeat':raise AssertionError(path)
            return Response(dict(ok=True))


def main():
    out=BASE/'visual_repeat_flow_verification_r2';out.mkdir(exist_ok=False);cases=[]
    for label,bad in [('success',False),('SD_refusal',True)]:
        fake=Fake(bad);dest=out/label;log=io.StringIO()
        argv=['test','--confirm-visual-repeat','--previous',str(BASE/'FOC_trial_r1'),'--outdir',str(dest)]
        with patch.object(sys,'argv',argv),patch.object(r.urllib.request,'build_opener',return_value=fake),patch.object(socket.socket,'connect',side_effect=AssertionError('No bench networking')),contextlib.redirect_stdout(log):
            rc=r.main()
        report=json.loads((dest/'report.json').read_text(encoding='utf8'))
        starts=[x for x in fake.requests if x[0]=='/api/start-sequence']
        assert len(starts)==(0 if bad else 1)
        assert report['CLEAR']==report['RESET']==report['flash']==0
        assert report['passed']==(not bad) and rc==(1 if bad else 0),(label,report)
        assert not any(body and 'CLEAR' in str(body) for _,body in fake.requests)
        cases.append(dict(case=label,passed=True,mocked_START=len(starts),hardware_commands=0))
    (out/'report.json').write_text(json.dumps(dict(passed=True,cases=cases,network_blocked=True,hardware_commands=0),indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=cases,hardware_commands=0)))


if __name__=='__main__':main()
